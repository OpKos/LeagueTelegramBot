from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)


class SessionProvider(Protocol):
    session: Session


class SessionManager:
    def __init__(self, database_url: str | None = None):
        if database_url is None:
            database_url = settings.build_database_url(settings.load_database_settings())
        logger.info(database_url)
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()

    def __del__(self):
        """Clean up the session when the manager is destroyed."""
        if hasattr(self, "session"):
            self.session.close()

    def reload_session(self) -> bool:
        """Close and reopen a fresh session."""
        self.session.close()
        self.session = self.Session()
        return True
