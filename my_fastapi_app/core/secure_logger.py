import logging
import re
from typing import Any

EMAIL_REGEX = re.compile(r'([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
PHONE_REGEX = re.compile(r'(\+?\d{2,3})\d{3,6}(\d{4})')
SECRET_REGEX = re.compile(
    r'(?i)(password|token|secret|api_key|access_token|authorization)(["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)',
)


def mask_email(match: re.Match) -> str:
    first_char = match.group(1)
    domain = match.group(2)
    return f"{first_char}***@{domain}"


def mask_phone(match: re.Match) -> str:
    prefix = match.group(1)
    last_four = match.group(2)
    return f"{prefix}***{last_four}"


def mask_secret(match: re.Match) -> str:
    field_name = match.group(1)
    delimiter = match.group(2)
    return f"{field_name}{delimiter}[REDACTED]"


def sanitize_message(message: str) -> str:
    if not isinstance(message, str):
        message = str(message)
    sanitized = SECRET_REGEX.sub(mask_secret, message)
    sanitized = PHONE_REGEX.sub(mask_phone, sanitized)
    sanitized = EMAIL_REGEX.sub(mask_email, sanitized)
    return sanitized


class PIISanitizingFilter(logging.Filter):
    """
    Централізований фільтр logging.Filter, який автоматично
    санітизує текст повідомлення та аргументи перед записом у будь-який Handler.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_message(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: sanitize_message(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(sanitize_message(arg) if isinstance(arg, str) else arg for arg in record.args)
        return True


def setup_secure_logging():
    """Підключає фільтр до root-логера для охоплення всіх модулів системи."""
    root_logger = logging.getLogger()
    pii_filter = PIISanitizingFilter()
    root_logger.addFilter(pii_filter)
    for handler in root_logger.handlers:
        handler.addFilter(pii_filter)