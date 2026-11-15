"""ЛР7, завдання 2: симуляція неконтрольованої мутації спільного стану.

Сценарій (FAIL на мутабельному коді): сторонній хелпер «накручує» націнку
прямо у спільній таблиці fallback-курсів. Оскільки таблиця -- звичайний dict,
перезапис проходить мовчки, і КОЖЕН наступний клієнт під час аварії провайдера
отримує спотворений курс (фінансовий збій).

На незмінних даних (MappingProxyType) той самий перезапис відхиляється
з TypeError, і курс лишається базовим (PASS).
"""
from unittest.mock import patch

import httpx
import pytest

from core import resilience_service
from core.resilience_service import get_external_rate_with_fallback, RateRequest, RetryPolicy

PROVIDER_URL = "http://upstream-service/rate"
BASE_EUR_RATE = 0.92
AMOUNT_USD = 1000


def apply_partner_markup(rates):
    """Імітація «корисного» хелпера з іншого модуля: додає +5 % до EUR
    прямо в переданій таблиці (in-place), не підозрюючи, що це спільний стан."""
    rates["EUR"] = rates["EUR"] * 1.05


def fetch_eur_fallback_rate():
    """Провайдер лежить -> метод віддає fallback-курс EUR."""
    with patch("httpx.Client.get", side_effect=httpx.ConnectTimeout("provider down")), \
         patch("time.sleep", return_value=None):
        rate, is_fallback = get_external_rate_with_fallback(
            RateRequest(code="EUR", provider_url=PROVIDER_URL),
            RetryPolicy(max_retries=3),
        )
    assert is_fallback is True
    return rate


@pytest.fixture(autouse=True)
def restore_fallback_table():
    """Ізоляція: повертаємо таблицю до початкового стану, щоб FAIL-сценарій
    не отруїв інші тести (на незмінних даних це no-op)."""
    snapshot = dict(resilience_service.FALLBACK_RATES)
    yield
    if isinstance(resilience_service.FALLBACK_RATES, dict):
        resilience_service.FALLBACK_RATES.update(snapshot)


def test_fallback_rate_survives_accidental_mutation():
    # Базовий стан: до інциденту курс правильний
    assert fetch_eur_fallback_rate() == BASE_EUR_RATE

    # Інцидент: три запити поспіль викликають хелпер, що мутує спільну таблицю
    for _ in range(3):
        try:
            apply_partner_markup(resilience_service.FALLBACK_RATES)
        except TypeError:
            pass  # незмінні дані відхиляють перезапис -- це і є захист

    # Після інциденту клієнт має отримати той самий базовий курс
    rate_after = fetch_eur_fallback_rate()
    expected_eur = round(AMOUNT_USD * BASE_EUR_RATE, 2)
    actual_eur = round(AMOUNT_USD * rate_after, 2)

    assert actual_eur == expected_eur, (
        f"ФІНАНСОВИЙ ЗБІЙ: {AMOUNT_USD} USD -> {actual_eur} EUR замість {expected_eur} EUR "
        f"(переплата {round(actual_eur - expected_eur, 2)} EUR); "
        f"fallback-курс EUR спотворено з {BASE_EUR_RATE} до {rate_after:.4f}"
    )