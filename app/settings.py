import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = (BASE_DIR / "smart_search.db").resolve()


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.storage_backend = os.getenv("STORAGE_BACKEND", "memory").strip().lower()
        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}")
        self.seed_demo_data = _as_bool(os.getenv("SEED_DEMO_DATA", "true"), default=True)


settings = Settings()