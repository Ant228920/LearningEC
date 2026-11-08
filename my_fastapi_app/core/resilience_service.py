import time
import logging
from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, NamedTuple

import httpx

logger = logging.getLogger("resilience")
logging.basicConfig(level=logging.INFO)

# Immutable Data: таблиця fallback-курсів доступна лише для читання.
# Будь-яка спроба FALLBACK_RATES["EUR"] = ... дає TypeError замість мовчазної порчі
# спільного стану для всіх запитів і потоків.
FALLBACK_RATES: Mapping[str, float] = MappingProxyType({
    "USD": 1.0,
    "EUR": 0.92,
    "UAH": 41.50,
    "GBP": 0.79,
})


class RetriesExhausted(Exception):
    """Усі спроби звернення до провайдера вичерпано."""


class RateResult(NamedTuple):
    """Незмінний результат: розпаковується як кортеж (rate, used_fallback)."""
    rate: float
    used_fallback: bool


@dataclass(frozen=True, slots=True)
class RateRequest:
    """Value Object: що саме запитуємо і в кого. Нормалізація коду і перевірки -- тут."""
    code: str
    provider_url: str

    def __post_init__(self):
        if not self.code.strip() or not self.provider_url.strip():
            raise ValueError("RateRequest: code and provider_url must not be empty")

    @property
    def symbol(self) -> str:
        return self.code.upper()

    def describe(self) -> str:
        return f"курсу {self.symbol} до {self.provider_url}"

    def fetch(self, client: httpx.Client) -> float:
        response = client.get(self.provider_url, params={"code": self.symbol})
        response.raise_for_status()
        return float(response.json()["rate"])

    def fallback_rate(self) -> float:
        return FALLBACK_RATES.get(self.symbol, 1.0)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Value Object: політика повторів. Backoff обчислюється, а не накопичується
    у змінній, що перезаписується (замість `delay *= 2`)."""
    max_retries: int = 3
    base_delay: float = 0.1
    request_timeout: float = 0.4
    connect_timeout: float = 0.2

    def __post_init__(self):
        if self.max_retries < 0 or self.base_delay < 0:
            raise ValueError("RetryPolicy: max_retries and base_delay must be >= 0")

    @property
    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.request_timeout, connect=self.connect_timeout)

    @property
    def pauses(self) -> tuple[float, ...]:
        """Пауза після кожної невдалої спроби: 0.1, 0.2, ...; після останньої -- 0."""
        waits = tuple(self.base_delay * 2 ** n for n in range(self.max_retries - 1))
        return (*waits, 0.0)[: self.max_retries]

    def call(self, operation: Callable[[httpx.Client], float], label: str = "запиту") -> float:
        with httpx.Client(timeout=self.timeout) as client:
            for attempt, pause in enumerate(self.pauses, start=1):
                try:
                    logger.info(f"[Resilience] Спроба {attempt}/{self.max_retries} запиту {label}")
                    return operation(client)
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    logger.warning(f"[Resilience] Спроба {attempt} невдала: {exc}")
                    time.sleep(pause)
        raise RetriesExhausted(self.max_retries)


DEFAULT_RETRY_POLICY = RetryPolicy()


def get_external_rate_with_fallback(
    request: RateRequest,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> RateResult:
    try:
        return RateResult(policy.call(request.fetch, label=request.describe()), used_fallback=False)
    except RetriesExhausted:
        logger.error(
            f"[Resilience Alert] Усі {policy.max_retries} спроби до {request.provider_url} вичерпано. "
            f"Застосовуємо Fallback-значення для {request.symbol}."
        )
        return RateResult(request.fallback_rate(), used_fallback=True)