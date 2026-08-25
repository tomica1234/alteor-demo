from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    uploads_dir: Path
    allow_external_connectors: bool
    offline_mode: bool
    seed_demo_data: bool
    access_password: str
    session_secret: str
    session_ttl_seconds: int
    secure_cookies: bool


def load_settings() -> Settings:
    default_data = Path(__file__).resolve().parents[1] / "data"
    data_dir = Path(os.getenv("ALTEOR_DATA_DIR", str(default_data))).expanduser().resolve()
    uploads_dir = data_dir / "uploads"
    data_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    offline_mode = os.getenv("ALTEOR_OFFLINE_MODE", "true").lower() in {"1", "true", "yes", "on"}
    access_password = os.getenv("ALTEOR_ACCESS_PASSWORD", "")
    session_secret = os.getenv("ALTEOR_SESSION_SECRET", access_password or "alteor-local-session")
    try:
        session_ttl_seconds = max(300, int(os.getenv("ALTEOR_SESSION_TTL_SECONDS", "43200")))
    except ValueError:
        session_ttl_seconds = 43200
    return Settings(
        data_dir=data_dir,
        database_path=data_dir / "alteor.sqlite3",
        uploads_dir=uploads_dir,
        allow_external_connectors=False,
        offline_mode=offline_mode,
        seed_demo_data=os.getenv("ALTEOR_SEED_DEMO_DATA", "false").lower()
        in {"1", "true", "yes", "on"},
        access_password=access_password,
        session_secret=session_secret,
        session_ttl_seconds=session_ttl_seconds,
        secure_cookies=os.getenv("ALTEOR_SECURE_COOKIES", "false").lower() in {"1", "true", "yes", "on"},
    )


settings = load_settings()
