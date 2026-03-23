from __future__ import annotations

import logging


_DEFAULT_FIELDS = {
    "user_id": "-",
    "provider": "-",
    "action": "-",
    "job_id": "-",
    "status": "-",
}


class ContextDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in _DEFAULT_FIELDS.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.addFilter(ContextDefaultsFilter())
    handler.setFormatter(
        logging.Formatter(
            fmt=(
                "%(asctime)s level=%(levelname)s logger=%(name)s "
                "user_id=%(user_id)s provider=%(provider)s action=%(action)s "
                "job_id=%(job_id)s status=%(status)s msg=%(message)s"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)


def log_extra(
    *,
    user_id: int | str | None = None,
    provider: str | None = None,
    action: str | None = None,
    job_id: str | None = None,
    status: str | None = None,
) -> dict[str, str]:
    return {
        "user_id": str(user_id) if user_id is not None else "-",
        "provider": provider or "-",
        "action": action or "-",
        "job_id": job_id or "-",
        "status": status or "-",
    }
