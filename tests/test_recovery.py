"""Unit tests for failure classification and retry logic."""
from src.agent.recovery import classify_failure, should_retry


def test_classify_retryable_exceptions():
    assert classify_failure(TimeoutError("Operation timed out")) == "retryable"
    assert classify_failure(ConnectionError("Connection refused")) == "retryable"
    assert classify_failure(OSError("Network down")) == "retryable"
    assert classify_failure(RuntimeError("Process terminated")) == "retryable"


def test_classify_retryable_messages():
    assert classify_failure(Exception("HTTP 429: rate limit exceeded")) == "retryable"
    assert classify_failure(Exception("Service temporarily unavailable")) == "retryable"
    assert classify_failure(Exception("connection reset by peer")) == "retryable"


def test_classify_non_retryable():
    assert classify_failure(ValueError("Invalid argument")) == "non_retryable"
    assert classify_failure(KeyError("missing_key")) == "non_retryable"
    assert classify_failure(TypeError("unsupported operand")) == "non_retryable"


def test_should_retry():
    # Retry count < max_retries with retryable error
    assert should_retry(TimeoutError(), retry_count=0, max_retries=2)
    assert should_retry(TimeoutError(), retry_count=1, max_retries=2)

    # Retry count >= max_retries
    assert not should_retry(TimeoutError(), retry_count=2, max_retries=2)

    # Non-retryable error never retries even if count < max_retries
    assert not should_retry(ValueError("bad format"), retry_count=0, max_retries=3)
