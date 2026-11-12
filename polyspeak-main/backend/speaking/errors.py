"""English UI errors with credential-redacted server diagnostics."""
import logging
import re


logger = logging.getLogger(__name__)


def public_error_message(error, fallback, settings=None):
    detail = str(error)
    for attribute in ("api_key", "azure_key"):
        secret = getattr(settings, attribute, "")
        if isinstance(secret, str) and secret:
            detail = detail.replace(secret, "[redacted]")
    detail = re.sub(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[redacted]", detail)
    detail = re.sub(
        r'''(?i)(authorization["']?\s*[:=]\s*["']?)(?:(?:Bearer|Basic)\s+)?[^\s,"'&]+''',
        r"\1[redacted]", detail,
    )
    detail = re.sub(
        r'''(?i)((?:api[_-]?key|subscription[_-]?key|token|password|secret)["']?\s*[:=]\s*["']?)[^\s,"'&]+''',
        r"\1[redacted]", detail,
    )
    # Avoid traceback logging: exception chains may contain unredacted headers.
    logger.warning("%s: %s", type(error).__name__, detail[:2000])
    if re.search(r"[\u3400-\u9fff\uf900-\ufaff]", detail):
        return fallback
    return detail[:400] or fallback
