from app.chunker import KoreanTextChunker


def test_chunker_flushes_on_hard_punctuation() -> None:
    chunker = KoreanTextChunker(min_chars=5, max_chars=80)

    chunks = chunker.push("\uc548\ub155\ud558\uc138\uc694. \ub2e4\uc74c \ubb38\uc7a5")

    assert chunks == ["\uc548\ub155\ud558\uc138\uc694."]
    assert chunker.flush() == "\ub2e4\uc74c \ubb38\uc7a5"


def test_chunker_splits_long_text() -> None:
    chunker = KoreanTextChunker(min_chars=10, max_chars=30)
    text = (
        "\uc774 \ubb38\uc7a5\uc740 \ubb38\uc7a5\ubd80\ud638\uac00 \uc5c6\uc9c0\ub9cc "
        "\ub108\ubb34 \uae38\uc5b4\uc11c \uc911\uac04\uc5d0 \ub04a\uc5b4\uc57c \ud569\ub2c8\ub2e4"
    )

    chunks = chunker.push(text)

    assert chunks
    assert all(len(chunk) <= 30 for chunk in chunks)


def test_chunker_respects_max_before_late_punctuation() -> None:
    chunker = KoreanTextChunker(min_chars=10, max_chars=25)
    text = (
        "\uc774 \ubb38\uc7a5\uc740 \ub05d\uc5d0 \ubb38\uc7a5\ubd80\ud638\uac00 "
        "\uc788\uc9c0\ub9cc \uc124\uc815\ud55c \uae38\uc774\ub97c \uba3c\uc800 \uc9c0\ucf1c\uc57c \ud569\ub2c8\ub2e4."
    )

    chunks = chunker.push(text)
    final_chunk = chunker.flush()
    if final_chunk:
        chunks.append(final_chunk)

    assert chunks
    assert all(len(chunk) <= 25 for chunk in chunks)
