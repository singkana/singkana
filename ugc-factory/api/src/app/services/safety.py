import re


BANNED_PATTERNS = [
    r"治る", r"完治", r"医師", r"薬", r"処方", r"副作用",
    r"100%.*効く", r"必ず", r"絶対",
]


def validate_script(text: str) -> None:
    for pat in BANNED_PATTERNS:
        if re.search(pat, text):
            raise ValueError(f"Compliance violation: banned pattern matched: {pat}")

