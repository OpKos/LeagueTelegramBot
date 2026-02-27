from __future__ import annotations

from .admin import AdminHandlers
from .chat import ChatHandlers
from .core import BaseHandlers
from .info import InfoHandlers
from .registration import RegistrationHandlers
from .tables import TableHandlers


class BotHandlers(
    BaseHandlers,
    RegistrationHandlers,
    TableHandlers,
    AdminHandlers,
    InfoHandlers,
    ChatHandlers,
):
    pass
