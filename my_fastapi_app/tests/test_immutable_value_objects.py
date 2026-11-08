"""ЛР7, завдання 2: контракти імутабельності та Value Objects."""
import dataclasses
from unittest.mock import patch

import httpx
import pytest

from core.resilience_service import (
    FALLBACK_RATES, RateRequest, RateResult, RetryPolicy, get_external_rate_with_fallback,
)


def test_fallback_table_is_read_only():
    with pytest.raises(TypeError):
        FALLBACK_RATES["EUR"] = 0.0


def test_value_objects_are_frozen():
    request = RateRequest("eur", "http://upstream-service/rate")
    policy = RetryPolicy()
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.code = "USD"
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.max_retries = 99
    with pytest.raises(AttributeError):
        RateResult(1.0, False).rate = 2.0


def test_value_objects_validate_their_own_invariants():
    with pytest.raises(ValueError):
        RateRequest("  ", "http://upstream-service/rate")
    with pytest.raises(ValueError):
        RetryPolicy(max_retries=-1)


def test_backoff_is_computed_not_accumulated():
    assert RetryPolicy(max_retries=3, base_delay=0.1).pauses == (0.1, 0.2, 0.0)
    assert RetryPolicy(max_retries=1).pauses == (0.0,)
    assert RetryPolicy(max_retries=0).pauses == ()


def test_backoff_sleeps_match_legacy_behavior():
    with patch("httpx.Client.get", side_effect=httpx.ConnectTimeout("down")), \
         patch("time.sleep", return_value=None) as sleep:
        get_external_rate_with_fallback(RateRequest("GBP", "http://upstream-service/rate"))
    assert [c.args[0] for c in sleep.call_args_list] == [0.1, 0.2, 0.0]