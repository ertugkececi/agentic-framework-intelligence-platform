from __future__ import annotations


def managed_component(cls):
    return cls


class FrameworkComponent:
    pass


class EnterpriseLog:
    def __init__(self, name: str) -> None:
        self.name = name

    def audit(self, message: str) -> None:
        _ = message
