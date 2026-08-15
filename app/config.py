from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    environment: str
    host: str
    port: int
    public_port: int
    public_address: str
    server_name: str
    country_code: str
    data_dir: Path
    log_dir: Path
    hostd_url: str
    secret_key: str
    admin_password: str
    admin_password_hash: str


def load_config() -> AppConfig:
    return AppConfig(
        environment=os.getenv("SG_GATEWAY_ENV", "development"),
        host=os.getenv("SG_GATEWAY_HOST", "127.0.0.1"),
        port=int(os.getenv("SG_GATEWAY_PORT", "8080")),
        public_port=int(os.getenv("SG_GATEWAY_PUBLIC_PORT", os.getenv("SG_GATEWAY_PORT", "8080"))),
        public_address=os.getenv("SG_GATEWAY_PUBLIC_ADDRESS", "").strip(),
        server_name=os.getenv("SG_GATEWAY_SERVER_NAME", "SG-Gateway").strip() or "SG-Gateway",
        country_code=os.getenv("SG_GATEWAY_COUNTRY_CODE", "unknown").strip().lower() or "unknown",
        data_dir=Path(os.getenv("SG_GATEWAY_DATA_DIR", "data")),
        log_dir=Path(os.getenv("SG_GATEWAY_LOG_DIR", "logs")),
        hostd_url=os.getenv("SG_GATEWAY_HOSTD_URL", "http://127.0.0.1:8090"),
        secret_key=os.getenv("SG_GATEWAY_SECRET_KEY", secrets.token_urlsafe(32)),
        admin_password=os.getenv("SG_GATEWAY_ADMIN_PASSWORD", "admin"),
        admin_password_hash=os.getenv("SG_GATEWAY_ADMIN_PASSWORD_HASH", "").strip(),
    )