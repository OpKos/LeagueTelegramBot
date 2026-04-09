#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from .config.app_config import load_app_config, load_locales
from .config.logging_setup import configure_logging
from .handlers import BotHandlers
from .handlers.jobs import startup_job_callback


def load_token(token_path: Path) -> str:
    with open(token_path, encoding="utf-8") as file:
        return file.read().strip()


def build_application(token: str, handlers: BotHandlers) -> Application:
    application = (
        Application.builder()
        .token(token)
        .write_timeout(30)
        .read_timeout(30)
        .connect_timeout(300)
        .build()
    )

    register_handlers(application, handlers)

    return application


def register_handlers(application: Application, handlers: BotHandlers) -> None:
    for name, spec in handlers.iter_handler_specs():
        callback = getattr(handlers, name)
        if spec.kind == "command":
            if not spec.commands:
                raise ValueError(f"Missing commands for handler {name}")
            commands = list(spec.commands)
            application.add_handler(
                CommandHandler(commands if len(commands) > 1 else commands[0], callback)
            )
            continue
        if spec.kind == "callback_query":
            if spec.pattern is None:
                raise ValueError(f"Missing pattern for callback handler {name}")
            application.add_handler(CallbackQueryHandler(callback, pattern=spec.pattern))
            continue
        raise ValueError(f"Unknown handler spec kind: {spec.kind}")


def main() -> None:
    config = load_app_config()
    configure_logging(config.logging_config_path)
    locales = load_locales(config.locales_path)
    handlers = BotHandlers(config, locales)

    token = load_token(config.token_path)
    application = build_application(token, handlers)
    application.job_queue.run_once(startup_job_callback, when=0, data={"handlers": handlers})
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
