from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings


class VideoProviderError(RuntimeError):
    pass


def _pick(d: dict, *keys: str):
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


async def _heygen_generate(audio_url: str, style_preset: str | None) -> bytes:
    if not settings.heygen_api_key:
        raise VideoProviderError("HEYGEN_API_KEY is missing")
    if not settings.heygen_avatar_id:
        raise VideoProviderError("HEYGEN_AVATAR_ID is missing")

    payload = {
        "video_inputs": [
            {
                "character": {"type": "avatar", "avatar_id": settings.heygen_avatar_id},
                "voice": {"type": "audio", "audio_url": audio_url},
            }
        ],
        "dimension": {"width": 1080, "height": 1920},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.heygen.com/v2/video/generate",
            headers={"x-api-key": settings.heygen_api_key},
            json=payload,
        )
        if r.status_code >= 400:
            raise VideoProviderError(f"heygen_generate_failed: {r.status_code} {r.text}")
        data = r.json()
        video_id = (
            _pick(data, "data", "video_id")
            or _pick(data, "data", "id")
            or data.get("video_id")
            or data.get("id")
        )
        if not video_id:
            raise VideoProviderError("video_id_missing")

        status_url = "https://api.heygen.com/v1/video_status.get"
        delay = 2.0
        elapsed = 0.0
        timeout = settings.heygen_poll_timeout_sec

        while elapsed < timeout:
            s = await client.get(
                status_url,
                headers={"x-api-key": settings.heygen_api_key},
                params={"video_id": video_id},
            )
            if s.status_code >= 400:
                raise VideoProviderError(f"status_failed: {s.status_code} {s.text}")
            status_data = s.json()
            status = _pick(status_data, "data", "status") or status_data.get("status")
            if status == "completed":
                video_url = (
                    _pick(status_data, "data", "video_url")
                    or _pick(status_data, "data", "url")
                    or status_data.get("video_url")
                    or status_data.get("url")
                )
                if isinstance(video_url, dict):
                    video_url = video_url.get("url")
                if not video_url:
                    raise VideoProviderError("video_url_missing")
                vr = await client.get(str(video_url))
                if vr.status_code >= 400:
                    raise VideoProviderError(f"download_failed: {vr.status_code}")
                return vr.content
            if status in ("failed", "error"):
                raise VideoProviderError(f"video_failed: {status}")

            await asyncio.sleep(delay)
            elapsed += delay
            delay = min(delay * 1.6, 10.0)

        raise VideoProviderError("video_timeout")


async def video_generate(image_url: str | None, audio_url: str, style_preset: str | None) -> bytes:
    if settings.video_provider == "dummy":
        return f"dummy video: {audio_url[-16:]}".encode("utf-8")

    if settings.video_provider != "heygen":
        raise VideoProviderError(f"unsupported_video_provider: {settings.video_provider}")

    return await _heygen_generate(audio_url, style_preset)
