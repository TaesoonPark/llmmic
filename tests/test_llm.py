from app.llm import parse_sse_content_lines


def test_parse_sse_ignores_reasoning_and_returns_content() -> None:
    lines = [
        'data: {"choices":[{"delta":{"reasoning":"hidden"}}]}',
        'data: {"choices":[{"delta":{"content":"\\uc548\\ub155"}}]}',
        'data: {"choices":[{"delta":{"content":"\\ud558\\uc138\\uc694"}}]}',
        "data: [DONE]",
    ]

    assert parse_sse_content_lines(lines) == [
        "\uc548\ub155",
        "\ud558\uc138\uc694",
    ]
