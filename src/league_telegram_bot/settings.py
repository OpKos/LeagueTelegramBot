from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class DatabaseSettings:
    name: str
    user: str
    password: str
    host: str = "db"


def load_database_settings() -> DatabaseSettings:
    """Load database settings from environment variables."""
    return DatabaseSettings(
        name=getenv("DB_NAME", "bot"),
        user=getenv("DB_USER", "bot"),
        password=getenv("DB_PASSWORD", "bot"),
    )


def build_database_url(settings: DatabaseSettings) -> str:
    return (
        f"postgresql+psycopg2://{settings.user}:{settings.password}@{settings.host}/{settings.name}"
    )
