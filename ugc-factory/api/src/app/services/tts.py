from __future__ import annotations

import httpx

from app.config import settings


class TTSProviderError(RuntimeError):
    pass


async def tts_generate(text: str, voice_id: str | None) -> tuple[bytes, str]:
    if settings.tts_provider == "dummy":
        return f"dummy tts: {text[:64]}".encode("utf-8"), "audio/mpeg"

    if settings.tts_provider != "openai":
        raise TTSProviderError(f"unsupported_tts_provider: {settings.tts_provider}")

    if not settings.openai_api_key:
        raise TTSProviderError("OPENAI_API_KEY is missing")

    if len(text) > settings.tts_max_chars:
        raise TTSProviderError(f"text_too_long: {len(text)} > {settings.tts_max_chars}")

    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    payload = {
        "model": settings.openai_tts_model,
        "voice": voice_id or "alloy",
        "input": text,
        "response_format": "mp3",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise TTSProviderError(f"openai_tts_error: {r.status_code} {r.text}")
        content_type = r.headers.get("content-type") or "audio/mpeg"
        return r.content, content_type
