import json

import httpx

from app.config import settings


class LLMError(RuntimeError):
    pass


def _dummy_scripts(target_count: int) -> dict:
    n = max(1, int(target_count or 1))
    variants = []
    for i in range(1, n + 1):
        hook = "これ、歌えるようになる？"
        body = "Before → After を一瞬で見せる"
        cta = "使ってみて：singkana.com"
        full_script = f"{hook}\n{body}\n{cta}"
        variants.append(
            {
                "variant_index": i,
                "hook": hook,
                "body": body,
                "cta": cta,
                "full_script": full_script,
                "captions": [
                    {"t": 0.0, "text": hook},
                    {"t": 2.5, "text": body},
                    {"t": 6.0, "text": cta},
                ],
                "shot": {
                    "scene": "indoors",
                    "camera": "selfie",
                    "tone": "casual",
                    "gesture": ["smile", "show product", "nod"],
                },
                "compliance": {
                    "no_medical_claim": True,
                    "no_before_after": True,
                },
            }
        )
    return {"variants": variants}


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no_json_object_found")
    return text[start : end + 1]


async def generate_scripts(prompt: str, target_count: int) -> dict:
    if settings.llm_provider == "dummy":
        return _dummy_scripts(target_count)
    if settings.llm_provider != "openai":
        raise LLMError("Only openai/dummy providers are implemented in v0.1")

    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY is missing")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": "Return ONLY a valid JSON object. No prose, no markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.9,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise LLMError(f"OpenAI error: {r.status_code} {r.text}")
        data = r.json()

    text = data["choices"][0]["message"]["content"]
    try:
        return json.loads(text)
    except Exception:
        sliced = _extract_json_object(text)
        try:
            return json.loads(sliced)
        except Exception as e2:
            raise LLMError(f"LLM returned invalid JSON: {e2}; head={text[:300]}")

