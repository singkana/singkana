import redis

from app.config import settings


r = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def key_for(job_id: str, step: str, variant_index: int | None = None) -> str:
    suffix = f":v{variant_index}" if variant_index is not None else ""
    return f"idemp:{job_id}:{step}{suffix}"


def try_acquire(key: str) -> bool:
    return bool(r.set(name=key, value="1", nx=True, ex=settings.idempotency_ttl_sec))


def release(key: str) -> None:
    try:
        r.delete(key)
    except Exception:
        pass

