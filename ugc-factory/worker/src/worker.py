from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import boto3
import httpx
import redis
from botocore.config import Config


REDIS_URL = os.environ["REDIS_URL"]
REDIS_QUEUE_KEY = os.getenv("REDIS_QUEUE_KEY", "ugc:finalize")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8080")
API_INTERNAL_URL = os.getenv("API_INTERNAL_URL", "http://api:8080/v1/internal/finalize")
API_KEY = os.getenv("API_KEY", "")
INTERNAL_TOKEN = os.getenv("FINALIZE_INTERNAL_TOKEN", "")

S3_ENDPOINT = os.environ["S3_ENDPOINT"]
S3_BUCKET = os.environ["S3_BUCKET"]
S3_ACCESS_KEY = os.environ["S3_ACCESS_KEY"]
S3_SECRET_KEY = os.environ["S3_SECRET_KEY"]
S3_REGION = os.getenv("S3_REGION", "us-east-1")

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _s3():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _presign(key: str, expires_sec: int = 600) -> str:
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires_sec,
    )


def _fetch_job(job_id: str) -> dict:
    headers = {"x-api-key": API_KEY} if API_KEY else {}
    with httpx.Client(timeout=30) as client:
        rj = client.get(f"{API_BASE_URL}/v1/jobs/{job_id}", headers=headers)
        rj.raise_for_status()
        return rj.json()


def _pick_asset(assets: list[dict], kind: str, variant_index: int) -> dict | None:
    for a in assets:
        if a.get("kind") == kind and int(a.get("variant_index") or 0) == int(variant_index):
            return a
    return None


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds) % 60
    m = int(seconds // 60) % 60
    h = int(seconds // 3600)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _captions_to_srt(captions: list[dict]) -> str:
    if not captions:
        return ""
    caps = []
    for c in captions:
        if "t" in c and "text" in c:
            caps.append({"t": float(c["t"]), "text": str(c["text"])})
    caps.sort(key=lambda x: x["t"])
    lines = []
    for i, c in enumerate(caps):
        start = c["t"]
        end = caps[i + 1]["t"] - 0.1 if i + 1 < len(caps) else start + 2.5
        if end <= start:
            end = start + 0.5
        lines.append(str(i + 1))
        lines.append(f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}")
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _run_ffmpeg(input_path: Path, output_path: Path, captions: list[dict] | None) -> None:
    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
    ]
    if captions:
        srt_text = _captions_to_srt(captions)
        if srt_text:
            srt_path = output_path.with_suffix(".srt")
            srt_path.write_text(srt_text, encoding="utf-8")
            srt_escaped = str(srt_path).replace("'", "\\'")
            filters.append(f"subtitles='{srt_escaped}'")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        ",".join(filters),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_path),
    ]
    subprocess.check_call(cmd)


def _upload_final(job_id: str, variant_index: int, output_path: Path) -> tuple[str, str]:
    key = f"jobs/{job_id}/{variant_index}/final.mp4"
    _s3().upload_file(
        Filename=str(output_path),
        Bucket=S3_BUCKET,
        Key=key,
        ExtraArgs={"ContentType": "video/mp4"},
    )
    return key, _presign(key)


def _notify_api(job_id: str, variant_index: int, final_url: str, s3_key: str) -> None:
    headers = {}
    if INTERNAL_TOKEN:
        headers["x-internal-token"] = INTERNAL_TOKEN
    with httpx.Client(timeout=30) as client:
        rj = client.post(
            API_INTERNAL_URL,
            headers=headers,
            json={
                "job_id": job_id,
                "variant_index": variant_index,
                "final_url": final_url,
                "s3_key": s3_key,
            },
        )
        rj.raise_for_status()


def main():
    print("worker: started. waiting queue:", REDIS_QUEUE_KEY, flush=True)
    while True:
        item = r.blpop(REDIS_QUEUE_KEY, timeout=5)
        if not item:
            continue
        _, payload = item
        try:
            msg = json.loads(payload)
            job_id = str(msg["job_id"])
            variant_index = int(msg["variant_index"])

            job = _fetch_job(job_id)
            assets = job.get("assets") or []
            video = _pick_asset(assets, "video", variant_index)
            script = _pick_asset(assets, "script", variant_index)
            if not video or not video.get("url"):
                raise RuntimeError("video_url_missing")

            video_url = video["url"]
            captions = (script or {}).get("meta", {}).get("captions") or []

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                input_path = tmp_path / "raw.mp4"
                output_path = tmp_path / "final.mp4"

                with httpx.Client(timeout=60) as client:
                    vr = client.get(video_url)
                    vr.raise_for_status()
                    input_path.write_bytes(vr.content)

                _run_ffmpeg(input_path, output_path, captions)
                s3_key, final_url = _upload_final(job_id, variant_index, output_path)
                _notify_api(job_id, variant_index, final_url, s3_key)
        except Exception as e:
            print("worker: finalize failed:", e, flush=True)
            r.rpush(f"{REDIS_QUEUE_KEY}:dead", payload)
        time.sleep(0.2)


if __name__ == "__main__":
    main()

