from __future__ import annotations


def business_service(cls):
    """Marks services as managed business components."""
    return cls


class BaseService:
    pass


class CompanyLogger:
    def __init__(self, name: str) -> None:
        self.name = name

    def info(self, message: str) -> None:
        # Intentionally minimal sample logger.
        _ = message
