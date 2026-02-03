from __future__ import annotations

import json

import redis

from app.config import settings


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def enqueue_finalize(job_id: str, variant_index: int) -> None:
    payload = {"job_id": job_id, "variant_index": variant_index}
    _redis().rpush(settings.redis_queue_key, json.dumps(payload))
