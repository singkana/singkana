import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Asset, Job, RunLog
from app.services import finalize_queue, storage
from app.services.idempotency import key_for, release, try_acquire
from app.services.llm import LLMError, generate_scripts
from app.services.prompts import render_prompt
from app.services.safety import validate_script
from app.services.tts import TTSProviderError, tts_generate
from app.services.video import VideoProviderError, video_generate

router = APIRouter(prefix="/v1", tags=["jobs"])


def require_api_key(req: Request):
    key = req.headers.get("x-api-key")
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="unauthorized")


class JobCreate(BaseModel):
    product_meta: dict = Field(default_factory=dict)
    target_count: int = 1
    image_url: str | None = None
    image_base64: str | None = None


class JobCreateResp(BaseModel):
    job_id: uuid.UUID


class ScriptStepResp(BaseModel):
    scripts: list[dict]


class TtsStepReq(BaseModel):
    variant_index: int = 1
    voice_id: str | None = None
    text: str | None = None


class TtsStepResp(BaseModel):
    audio_url: str
    duration_ms: int


class VideoStepReq(BaseModel):
    variant_index: int = 1
    image_url: str | None = None
    audio_url: str | None = None
    style_preset: str | None = None


class VideoStepResp(BaseModel):
    video_url_raw: str


class FinalizeStepReq(BaseModel):
    variant_index: int = 1
    video_url_raw: str | None = None
    captions: list[dict] | None = None


class FinalizeStepResp(BaseModel):
    queued: bool = False
    final_url: str | None = None


class InternalFinalizeReq(BaseModel):
    job_id: uuid.UUID
    variant_index: int = 1
    final_url: str
    s3_key: str


class RunJobResp(BaseModel):
    results: list[dict]
    status: str


@router.post("/jobs", response_model=JobCreateResp)
def create_job(body: JobCreate, req: Request, db: Session = Depends(get_db)):
    require_api_key(req)

    job = Job(
        status="queued",
        input_image_url=body.image_url,
        product_meta=body.product_meta,
        target_count=body.target_count,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return JobCreateResp(job_id=job.id)


@router.post("/jobs/{job_id}/steps/script", response_model=ScriptStepResp)
async def step_script(job_id: uuid.UUID, req: Request, db: Session = Depends(get_db)):
    require_api_key(req)

    job: Job | None = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    # idempotency: job_id + step
    idk = key_for(str(job_id), "script_gen")
    if not try_acquire(idk):
        variants = [a.meta for a in job.assets if a.kind == "script"]
        if variants:
            return ScriptStepResp(scripts=variants)
        # ロックだけ残って assets が無い = 途中で失敗した残骸の可能性が高いので、1回だけ自己回復する
        release(idk)
        if not try_acquire(idk):
            raise HTTPException(409, detail="idempotency_conflict_no_assets")

    prompt = render_prompt(job.product_meta, job.target_count)

    try:
        out = await generate_scripts(prompt, job.target_count)
        variants = out.get("variants") or []
        if not isinstance(variants, list) or not variants:
            raise ValueError("variants missing")

        for v in variants:
            validate_script((v.get("full_script") or ""))

        for i, v in enumerate(variants):
            idx = int(v.get("variant_index") or (i + 1))
            meta = dict(v)
            meta["variant_index"] = idx
            db.add(
                Asset(
                    job_id=job.id,
                    kind="script",
                    variant_index=idx,
                    url=None,
                    meta=meta,
                )
            )

        db.add(
            RunLog(
                job_id=job.id,
                step="script_gen",
                provider=settings.llm_provider,
                status="ok",
                request={"prompt": prompt[:2000]},
                response={"variants_count": len(variants)},
                error=None,
            )
        )

        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()

        return ScriptStepResp(scripts=variants)

    except (LLMError, ValueError) as e:
        # 失敗した場合はロックを解除して、次の再試行を可能にする
        release(idk)
        db.add(
            RunLog(
                job_id=job.id,
                step="script_gen",
                provider=settings.llm_provider,
                status="error",
                request={"prompt": prompt[:2000]},
                response={},
                error=str(e),
            )
        )
        job.status = "failed"
        job.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, detail=f"script_gen_failed: {e}")


@router.post("/jobs/{job_id}/steps/tts", response_model=TtsStepResp)
async def step_tts(
    job_id: uuid.UUID, body: TtsStepReq, req: Request, db: Session = Depends(get_db)
):
    require_api_key(req)

    job: Job | None = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    text = (body.text or "").strip()
    if not text:
        script_asset = (
            db.query(Asset)
            .filter_by(job_id=job.id, kind="script", variant_index=int(body.variant_index or 1))
            .first()
        )
        if not script_asset:
            script_asset = (
                db.query(Asset)
                .filter_by(job_id=job.id, kind="script")
                .order_by(Asset.variant_index.asc())
                .first()
            )
        if script_asset:
            meta = script_asset.meta or {}
            text = (meta.get("full_script") or "").strip()
            if not text:
                hook = (meta.get("hook") or "").strip()
                body_text = (meta.get("body") or "").strip()
                cta = (meta.get("cta") or "").strip()
                text = " ".join([p for p in [hook, body_text, cta] if p]).strip()
    if not text:
        raise HTTPException(400, "empty_text")

    idx = int(body.variant_index or 1)
    idk = key_for(str(job_id), "tts", idx)
    if not try_acquire(idk):
        exists = db.query(Asset).filter_by(job_id=job.id, kind="audio", variant_index=idx).first()
        if exists and exists.url:
            return TtsStepResp(
                audio_url=exists.url,
                duration_ms=int(exists.meta.get("duration_ms") or 0),
            )
        release(idk)
        if not try_acquire(idk):
            raise HTTPException(409, detail="idempotency_conflict_no_assets")

    try:
        audio_bytes, content_type = await tts_generate(text, body.voice_id)
        duration_ms = max(1000, min(15000, len(text) * 40))
        audio_key = f"jobs/{job_id}/{idx}/audio.mp3"
        storage.put_bytes(audio_key, audio_bytes, content_type=content_type)
        audio_url = storage.presign_get_url(audio_key)

        db.add(
            Asset(
                job_id=job.id,
                kind="audio",
                variant_index=idx,
                url=audio_url,
                meta={
                    "provider": settings.tts_provider,
                    "voice_id": body.voice_id,
                    "duration_ms": duration_ms,
                    "s3_key": audio_key,
                },
            )
        )
        db.add(
            RunLog(
                job_id=job.id,
                step="tts",
                provider=settings.tts_provider,
                status="ok",
                request={"variant_index": idx},
                response={"audio_url": audio_url, "duration_ms": duration_ms},
                error=None,
            )
        )
        job.updated_at = datetime.utcnow()
        db.commit()

        return TtsStepResp(audio_url=audio_url, duration_ms=duration_ms)

    except (TTSProviderError, ValueError) as e:
        release(idk)
        db.add(
            RunLog(
                job_id=job.id,
                step="tts",
                provider=settings.tts_provider,
                status="error",
                request={"variant_index": idx},
                response={},
                error=str(e),
            )
        )
        job.status = "failed"
        job.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, detail=f"tts_failed: {e}")


@router.post("/jobs/{job_id}/steps/video", response_model=VideoStepResp)
async def step_video(
    job_id: uuid.UUID, body: VideoStepReq, req: Request, db: Session = Depends(get_db)
):
    require_api_key(req)

    job: Job | None = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    audio_url = (body.audio_url or "").strip()
    if not audio_url:
        audio_asset = (
            db.query(Asset)
            .filter_by(job_id=job.id, kind="audio", variant_index=int(body.variant_index or 1))
            .first()
        )
        if audio_asset and audio_asset.url:
            audio_url = audio_asset.url
    if not audio_url:
        raise HTTPException(400, "audio_url_required")

    idx = int(body.variant_index or 1)
    idk = key_for(str(job_id), "video", idx)
    if not try_acquire(idk):
        exists = db.query(Asset).filter_by(job_id=job.id, kind="video", variant_index=idx).first()
        if exists and exists.url:
            return VideoStepResp(video_url_raw=exists.url)
        release(idk)
        if not try_acquire(idk):
            raise HTTPException(409, detail="idempotency_conflict_no_assets")

    image_url = body.image_url or job.input_image_url
    try:
        video_bytes = await video_generate(image_url, audio_url, body.style_preset)
        video_key = f"jobs/{job_id}/{idx}/video_raw.mp4"
        storage.put_bytes(video_key, video_bytes, content_type="video/mp4")
        video_url_raw = storage.presign_get_url(video_key)

        db.add(
            Asset(
                job_id=job.id,
                kind="video",
                variant_index=idx,
                url=video_url_raw,
                meta={
                    "provider": settings.video_provider,
                    "image_url": image_url,
                    "audio_url": audio_url,
                    "style_preset": body.style_preset,
                    "s3_key": video_key,
                },
            )
        )
        db.add(
            RunLog(
                job_id=job.id,
                step="video_gen",
                provider=settings.video_provider,
                status="ok",
                request={"variant_index": idx},
                response={"video_url_raw": video_url_raw},
                error=None,
            )
        )
        job.updated_at = datetime.utcnow()
        db.commit()

        return VideoStepResp(video_url_raw=video_url_raw)

    except (VideoProviderError, ValueError) as e:
        release(idk)
        db.add(
            RunLog(
                job_id=job.id,
                step="video_gen",
                provider=settings.video_provider,
                status="error",
                request={"variant_index": idx},
                response={},
                error=str(e),
            )
        )
        job.status = "failed"
        job.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, detail=f"video_gen_failed: {e}")


@router.post("/jobs/{job_id}/steps/finalize", response_model=FinalizeStepResp)
def step_finalize(
    job_id: uuid.UUID, body: FinalizeStepReq, req: Request, db: Session = Depends(get_db)
):
    require_api_key(req)

    job: Job | None = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    video_url_raw = (body.video_url_raw or "").strip()
    if not video_url_raw:
        video_asset = (
            db.query(Asset)
            .filter_by(job_id=job.id, kind="video", variant_index=int(body.variant_index or 1))
            .first()
        )
        if video_asset and video_asset.url:
            video_url_raw = video_asset.url
    if not video_url_raw:
        raise HTTPException(400, "video_url_raw_required")

    idx = int(body.variant_index or 1)
    idk = key_for(str(job_id), "finalize", idx)
    if not try_acquire(idk):
        exists = db.query(Asset).filter_by(job_id=job.id, kind="final", variant_index=idx).first()
        if exists and exists.url:
            return FinalizeStepResp(final_url=exists.url, queued=False)
        release(idk)
        if not try_acquire(idk):
            return FinalizeStepResp(queued=True)

    finalize_queue.enqueue_finalize(str(job_id), idx)
    db.add(
        RunLog(
            job_id=job.id,
            step="finalize",
            provider="worker",
            status="queued",
            request={"variant_index": idx},
            response={"queue": settings.redis_queue_key},
            error=None,
        )
    )
    job.status = "finalizing"
    job.updated_at = datetime.utcnow()
    db.commit()

    return FinalizeStepResp(queued=True)


@router.post("/internal/finalize")
def internal_finalize(body: InternalFinalizeReq, req: Request, db: Session = Depends(get_db)):
    token = settings.finalize_internal_token
    if token and req.headers.get("x-internal-token") != token:
        raise HTTPException(status_code=401, detail="unauthorized")

    job: Job | None = db.get(Job, body.job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    idx = int(body.variant_index or 1)
    existing = db.query(Asset).filter_by(job_id=job.id, kind="final", variant_index=idx).first()
    if existing:
        existing.url = body.final_url
        existing.meta = {"s3_key": body.s3_key}
    else:
        db.add(
            Asset(
                job_id=job.id,
                kind="final",
                variant_index=idx,
                url=body.final_url,
                meta={"s3_key": body.s3_key},
            )
        )

    db.add(
        RunLog(
            job_id=job.id,
            step="finalize",
            provider="worker",
            status="ok",
            request={"variant_index": idx},
            response={"final_url": body.final_url},
            error=None,
        )
    )

    release(key_for(str(job.id), "finalize", idx))

    final_count = (
        db.query(Asset).filter_by(job_id=job.id, kind="final").count()
    )
    job.status = "succeeded" if final_count >= int(job.target_count or 1) else "finalizing"
    job.updated_at = datetime.utcnow()
    db.commit()

    return {"ok": True, "status": job.status}


@router.post("/jobs/{job_id}/run", response_model=RunJobResp)
async def run_job(job_id: uuid.UUID, req: Request, db: Session = Depends(get_db)):
    require_api_key(req)

    job: Job | None = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    script_assets = [a for a in job.assets if a.kind == "script"]
    if not script_assets:
        script_resp = await step_script(job_id, req, db)
        script_variants = list(script_resp.scripts)
    else:
        script_variants = [a.meta or {} for a in script_assets]

    script_by_idx: dict[int, dict] = {}
    for i, meta in enumerate(script_variants):
        idx = int(meta.get("variant_index") or (i + 1))
        meta = dict(meta)
        meta["variant_index"] = idx
        script_by_idx[idx] = meta

    results: list[dict] = []
    any_failed = False
    any_queued = False

    for idx in range(1, int(job.target_count or 1) + 1):
        meta = script_by_idx.get(idx) or script_by_idx.get(1) or {}
        text = (meta.get("full_script") or "").strip()
        if not text:
            hook = (meta.get("hook") or "").strip()
            body_text = (meta.get("body") or "").strip()
            cta = (meta.get("cta") or "").strip()
            text = " ".join([p for p in [hook, body_text, cta] if p]).strip()

        try:
            tts_resp = await step_tts(
                job_id, TtsStepReq(variant_index=idx, text=text), req, db
            )
            video_resp = await step_video(
                job_id,
                VideoStepReq(
                    variant_index=idx,
                    image_url=job.input_image_url,
                    audio_url=tts_resp.audio_url,
                    style_preset="default",
                ),
                req,
                db,
            )
            final_resp = step_finalize(
                job_id,
                FinalizeStepReq(
                    variant_index=idx,
                    video_url_raw=video_resp.video_url_raw,
                    captions=meta.get("captions"),
                ),
                req,
                db,
            )
            if final_resp.final_url:
                results.append(
                    {
                        "variant_index": idx,
                        "status": "ok",
                        "final_url": final_resp.final_url,
                    }
                )
            else:
                any_queued = True
                results.append(
                    {
                        "variant_index": idx,
                        "status": "queued",
                    }
                )
        except HTTPException as e:
            any_failed = True
            db.add(
                RunLog(
                    job_id=job.id,
                    step="run",
                    provider="api",
                    status="error",
                    request={"variant_index": idx},
                    response={},
                    error=str(e.detail),
                )
            )
            db.commit()
            results.append(
                {
                    "variant_index": idx,
                    "status": "error",
                    "error": str(e.detail),
                }
            )

    if any_failed:
        job.status = "partial_failed"
    elif any_queued:
        job.status = "finalizing"
    else:
        job.status = "succeeded"
    job.updated_at = datetime.utcnow()
    db.commit()

    return RunJobResp(results=results, status=job.status)


@router.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, req: Request, db: Session = Depends(get_db)):
    require_api_key(req)

    job: Job | None = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job_not_found")

    assets = [
        {
            "id": str(a.id),
            "kind": a.kind,
            "variant_index": a.variant_index,
            "url": a.url,
            "meta": a.meta,
            "created_at": a.created_at.isoformat(),
        }
        for a in job.assets
    ]

    return {
        "job_id": str(job.id),
        "status": job.status,
        "target_count": job.target_count,
        "assets": assets,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }

