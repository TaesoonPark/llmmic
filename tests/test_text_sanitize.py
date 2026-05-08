from app.text_sanitize import sanitize_for_tts


def test_sanitize_for_tts_removes_emoji_but_keeps_text() -> None:
    text = "\uc548\ub155\ud558\uc138\uc694 \U0001f44b \ubc18\uac11\uc2b5\ub2c8\ub2e4! \u2728"

    assert sanitize_for_tts(text) == "\uc548\ub155\ud558\uc138\uc694 \ubc18\uac11\uc2b5\ub2c8\ub2e4!"


def test_sanitize_for_tts_normalizes_korean_jamo_slang() -> None:
    text = (
        "\uc548\ub155! \u314b\u314b\u314b\u314b \ub098 \uc9c4\uc9dc "
        "\uc874\ub9db\ud0f1 \uae30\ubd84\uc774\uc57c! \u3139\u3147 \ud3fc "
        "\ubbf8\ucce4\uc9c0? \u3160\u3160"
    )

    assert sanitize_for_tts(text) == (
        "\uc548\ub155! \ud558\ud558 \ub098 \uc9c4\uc9dc "
        "\uc874\ub9db\ud0f1 \uae30\ubd84\uc774\uc57c! \uc815\ub9d0 \ud3fc "
        "\ubbf8\ucce4\uc9c0? \ud751\ud751"
    )


def test_sanitize_for_tts_removes_leftover_compat_jamo() -> None:
    text = "\u3134\u3134 \ub300\ubc15 \u314b \uc624\ub298 \u314e"

    assert sanitize_for_tts(text) == "\ub300\ubc15 \uc624\ub298"
