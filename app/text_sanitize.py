from __future__ import annotations

import re


LAUGHTER_RE = re.compile(r"(?<![\w\uac00-\ud7a3])[\u314b\u314e]{2,}(?![\w\uac00-\ud7a3])")
TEARS_RE = re.compile(r"(?<![\w\uac00-\ud7a3])[\u315c\u3160]{2,}(?![\w\uac00-\ud7a3])")
COMPAT_JAMO_RE = re.compile(r"[\u3130-\u318f]+")
EMOJI_RE = re.compile(
    "["
    "\U0001f1e6-\U0001f1ff"
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\u2600-\u27bf"
    "\ufe0f"
    "\u200d"
    "]+"
)


def sanitize_for_tts(text: str) -> str:
    sanitized = EMOJI_RE.sub("", text)
    sanitized = LAUGHTER_RE.sub("\ud558\ud558", sanitized)
    sanitized = TEARS_RE.sub("\ud751\ud751", sanitized)
    sanitized = re.sub(
        r"(?<![\w\uac00-\ud7a3])\u3139\u3147(?![\w\uac00-\ud7a3])",
        "\uc815\ub9d0",
        sanitized,
    )
    sanitized = re.sub(
        r"(?<![\w\uac00-\ud7a3])\u3147\u3147(?![\w\uac00-\ud7a3])",
        "\uc751",
        sanitized,
    )
    sanitized = re.sub(
        r"(?<![\w\uac00-\ud7a3])\u3131\u3131(?![\w\uac00-\ud7a3])",
        "\uac00\uc790",
        sanitized,
    )
    sanitized = re.sub(
        r"(?<![\w\uac00-\ud7a3])\u3142\u3142(?![\w\uac00-\ud7a3])",
        "\ubc14\uc774\ubc14\uc774",
        sanitized,
    )
    sanitized = COMPAT_JAMO_RE.sub("", sanitized)
    return re.sub(r"\s{2,}", " ", sanitized).strip()
