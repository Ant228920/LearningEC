import time
import logging
import httpx

logger = logging.getLogger("resilience")
logging.basicConfig(level=logging.INFO)

FALLBACK_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "UAH": 41.50,
    "GBP": 0.79
}

def get_external_rate_with_fallback(code: str, provider_url: str, max_retries: int = 3) -> tuple[float, bool]:
    code_upper = code.upper()
    delay = 0.1

    timeout_cfg = httpx.Timeout(0.4, connect=0.2)

    with httpx.Client(timeout=timeout_cfg) as client:
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[Resilience] Спроба {attempt}/{max_retries} запиту курсу {code_upper} до {provider_url}")
                resp = client.get(provider_url, params={"code": code_upper})
                resp.raise_for_status()
                data = resp.json()
                return float(data["rate"]), False
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning(f"[Resilience] Спроба {attempt} невдала: {exc}")
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2

    logger.error(
        f"[Resilience Alert] Усі {max_retries} спроби до {provider_url} вичерпано. "
        f"Застосовуємо Fallback-значення для {code_upper}."
    )
    fallback_rate = FALLBACK_RATES.get(code_upper, 1.0)
    return fallback_rate, True