from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HandlerSpec:
    kind: Literal["command", "callback_query"]
    commands: tuple[str, ...] = ()
    pattern: str | None = None


def command_handler(*commands: str):
    def decorator(func):
        func._handler_spec = HandlerSpec(kind="command", commands=commands)
        return func

    return decorator


def callback_query_handler(pattern: str):
    def decorator(func):
        func._handler_spec = HandlerSpec(kind="callback_query", pattern=pattern)
        return func

    return decorator
