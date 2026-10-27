from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import wraps
from typing import Literal

from .utils import log_command_event


@dataclass(frozen=True)
class HandlerSpec:
    kind: Literal["command", "callback_query"]
    commands: tuple[str, ...] = ()
    pattern: str | None = None


def command_handler(*commands: str):
    def decorator(func):
        command = commands[0]
        logger = logging.getLogger(func.__module__)

        @wraps(func)
        async def wrapped(*args, **kwargs):
            update = args[1] if len(args) > 1 else kwargs["update"]
            log_command_event(update, command, "started", logger=logger)
            try:
                result = await func(*args, **kwargs)
            except Exception:
                log_command_event(update, command, "failed", logger=logger, exc_info=True)
                raise
            log_command_event(update, command, "finished", logger=logger)
            return result

        wrapped._handler_spec = HandlerSpec(kind="command", commands=commands)
        return wrapped

    return decorator


def callback_query_handler(pattern: str):
    def decorator(func):
        func._handler_spec = HandlerSpec(kind="callback_query", pattern=pattern)
        return func

    return decorator
