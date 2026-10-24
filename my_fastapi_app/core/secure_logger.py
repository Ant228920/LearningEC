import logging
import re
from typing import Any

EMAIL_REGEX = re.compile(r'([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')
PHONE_REGEX = re.compile(r'(\+?\d{2,3})\d{3,6}(\d{4})')
SECRET_REGEX = re.compile(
    r'(?i)(password|token|secret|api_key|access_token|authorization)(["\']?\s*[:=]\s*["\']?)([^"\'\s,}{]+)',
)


def mask_email(match: re.Match) -> str:
    return f"{match.group(1)}***@{match.group(2)}"


def mask_phone(match: re.Match) -> str:
    return f"{match.group(1)}***{match.group(2)}"


def mask_secret(match: re.Match) -> str:
    return f"{match.group(1)}{match.group(2)}[REDACTED]"


def sanitize_message(message: Any) -> Any:
    if isinstance(message, str):
        sanitized = SECRET_REGEX.sub(mask_secret, message)
        sanitized = PHONE_REGEX.sub(mask_phone, sanitized)
        return EMAIL_REGEX.sub(mask_email, sanitized)

    if isinstance(message, dict):
        return {k: sanitize_message(v) for k, v in message.items()}
    if isinstance(message, (list, tuple)):
        sanitized_seq = [sanitize_message(item) for item in message]
        return tuple(sanitized_seq) if isinstance(message, tuple) else sanitized_seq

    if hasattr(message, "__dict__"):
        return sanitize_message(str(message))

    return message


class PIISanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_message(record.msg)
        else:
            record.msg = sanitize_message(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_message(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(sanitize_message(arg) for arg in record.args)

        if record.exc_info and not record.exc_text:
            formatter = logging.Formatter()
            record.exc_text = formatter.formatException(record.exc_info)
            record.exc_info = None

        if record.exc_text:
            record.exc_text = sanitize_message(record.exc_text)

        return True


def setup_secure_logging():
    root_logger = logging.getLogger()
    pii_filter = PIISanitizingFilter()
    root_logger.addFilter(pii_filter)
    for handler in root_logger.handlers:
        handler.addFilter(pii_filter)