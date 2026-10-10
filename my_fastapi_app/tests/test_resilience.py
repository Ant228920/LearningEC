import pytest
import httpx
from unittest.mock import patch, MagicMock
from core.resilience_service import get_external_rate_with_fallback, FALLBACK_RATES
from scripts.sync_nbu import parse_currency_item


def test_upstream_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"rate": 0.85}

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        rate, is_fallback = get_external_rate_with_fallback(
            code="GBP",
            provider_url="http://upstream-service/rate",
            max_retries=3
        )

        assert rate == 0.85
        assert is_fallback is False
        assert mock_get.call_count == 1


def test_resilience_on_http_500_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    http_error = httpx.HTTPStatusError("500 Internal Server Error", request=MagicMock(), response=mock_resp)
    mock_resp.raise_for_status.side_effect = http_error

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get, \
         patch("time.sleep", return_value=None):

        rate, is_fallback = get_external_rate_with_fallback(
            code="GBP",
            provider_url="http://upstream-service/rate",
            max_retries=3
        )

        assert mock_get.call_count == 3
        assert is_fallback is True
        assert rate == FALLBACK_RATES["GBP"]


def test_resilience_on_timeout():
    timeout_error = httpx.ConnectTimeout("Connection timed out")

    with patch("httpx.Client.get", side_effect=timeout_error) as mock_get, \
         patch("time.sleep", return_value=None):

        rate, is_fallback = get_external_rate_with_fallback(
            code="EUR",
            provider_url="http://upstream-service/rate",
            max_retries=3
        )

        assert mock_get.call_count == 3
        assert is_fallback is True
        assert rate == FALLBACK_RATES["EUR"]

