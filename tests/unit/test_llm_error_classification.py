"""Tests for LLM error classification helpers in agent.core.agent_loop.

Covers two regressions on 2026-04-25:

1. Non-Anthropic context overflow (Kimi 365k > 262k) was not classified as
   ``_is_context_overflow_error``, so the recovery path didn't fire and
   session 62ccfdcb died with 68 wasted compaction events.

2. Bedrock TPM rate limit (`Too many tokens, please wait before trying
   again.`) needs the longer rate-limit retry schedule. The old schedule
   ([5, 15, 30] = 50s) burned through 6 sessions costing >$2,400 combined
   on the same day.
"""

from agent.core.agent_loop import (
    LocalLLMConnectionError,
    _MAX_LLM_RETRIES,
    _LLM_RATE_LIMIT_RETRY_DELAYS,
    _LLM_RETRY_DELAYS,
    _context_window_from_error,
    _friendly_error_message,
    _is_context_overflow_error,
    _local_llm_error_from_completion_error,
    _is_rate_limit_error,
    _is_transient_error,
    _retry_delay_for,
)


# ── context overflow ────────────────────────────────────────────────────


def test_kimi_prompt_too_long_is_context_overflow():
    # Verbatim error text from session 62ccfdcb (2026-04-25, Kimi K2.6).
    err = Exception(
        "litellm.BadRequestError: OpenAIException - The prompt is too long: "
        "365407, model maximum context length: 262143"
    )
    assert _is_context_overflow_error(err)


def test_openai_context_length_exceeded_is_context_overflow():
    err = Exception("Error: This model's maximum context length is 8192 tokens.")
    assert _is_context_overflow_error(err)


def test_provider_context_window_is_extracted_from_openai_error():
    err = Exception(
        "This model's maximum context length is 65536 tokens. "
        "However, you requested 20000 output tokens."
    )

    assert _context_window_from_error(err) == 65536


def test_provider_context_window_is_extracted_from_kimi_error():
    err = Exception(
        "The prompt is too long: 365407, model maximum context length: 262143"
    )

    assert _context_window_from_error(err) == 262143


def test_random_error_is_not_context_overflow():
    err = Exception("connection reset by peer")
    assert not _is_context_overflow_error(err)


# ── rate limit ──────────────────────────────────────────────────────────


def test_bedrock_too_many_tokens_is_rate_limit():
    # Verbatim from sessions b37a3823, c4d7a831, b63c4933 (2026-04-25).
    err = Exception(
        'litellm.RateLimitError: BedrockException - {"message":"Too many '
        'tokens, please wait before trying again."}'
    )
    assert _is_rate_limit_error(err)
    # Rate-limit errors are also classified as transient.
    assert _is_transient_error(err)


def test_429_is_rate_limit():
    err = Exception("HTTP 429 Too Many Requests")
    assert _is_rate_limit_error(err)


def test_timeout_is_transient_but_not_rate_limit():
    err = Exception("Request timed out after 600s")
    assert _is_transient_error(err)
    assert not _is_rate_limit_error(err)


def test_local_llm_connection_error_is_not_retried(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:30000")
    err = LocalLLMConnectionError(
        model_name="vllm/qwen3.6-35b-a3b",
        api_base="http://127.0.0.1:30000/v1",
        detail="Connect call failed ('127.0.0.1', 30000)",
    )

    assert not _is_transient_error(err)
    assert _retry_delay_for(err, 0) is None

    message = _friendly_error_message(err)
    assert message is not None
    assert "Local LLM is not reachable." in message
    assert "Model: vllm/qwen3.6-35b-a3b" in message
    assert "Endpoint: http://127.0.0.1:30000/v1" in message
    assert "curl http://127.0.0.1:30000/v1/models" in message
    assert "Traceback" not in message
    assert "litellm.InternalServerError" not in message


def test_litellm_wrapped_local_connection_error_is_upcast(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://127.0.0.1:30000")
    err = Exception(
        "litellm.InternalServerError: InternalServerError: OpenAIException - "
        "Connection error. Cannot connect to host 127.0.0.1:30000 "
        "[Connect call failed ('127.0.0.1', 30000)]"
    )

    local_err = _local_llm_error_from_completion_error(
        "vllm/qwen3.6-35b-a3b",
        {"api_base": "http://127.0.0.1:30000/v1"},
        err,
    )

    assert isinstance(local_err, LocalLLMConnectionError)
    assert local_err.api_base == "http://127.0.0.1:30000/v1"
    assert _retry_delay_for(local_err, 0) is None
    assert (
        _local_llm_error_from_completion_error(
            "siliconflow/deepseek-ai/DeepSeek-V4-Flash",
            {"api_base": "https://api.siliconflow.cn/v1"},
            err,
        )
        is None
    )


# ── retry schedule selection ────────────────────────────────────────────


def test_rate_limit_uses_longer_schedule():
    err = Exception("Too many tokens, please wait before trying again.")
    delays = [
        _retry_delay_for(err, i) for i in range(len(_LLM_RATE_LIMIT_RETRY_DELAYS))
    ]
    assert delays == _LLM_RATE_LIMIT_RETRY_DELAYS
    # Just past the schedule → None (stop retrying).
    assert _retry_delay_for(err, len(_LLM_RATE_LIMIT_RETRY_DELAYS)) is None


def test_other_transient_uses_short_schedule():
    err = Exception("503 service unavailable")
    delays = [_retry_delay_for(err, i) for i in range(len(_LLM_RETRY_DELAYS))]
    assert delays == _LLM_RETRY_DELAYS
    assert _retry_delay_for(err, len(_LLM_RETRY_DELAYS)) is None


def test_non_transient_returns_none():
    err = Exception("invalid request: bad parameter")
    assert _retry_delay_for(err, 0) is None


def test_rate_limit_total_budget_covers_bedrock_bucket_recovery():
    """The whole point of the rate-limit schedule: total wait time should
    exceed the ~60s Bedrock TPM bucket recovery window."""
    assert len(_LLM_RATE_LIMIT_RETRY_DELAYS) == _MAX_LLM_RETRIES - 1
    assert sum(_LLM_RATE_LIMIT_RETRY_DELAYS) > 60
