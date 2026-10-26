"""Configuration read from environment variables (and an optional .env file)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _json_dict(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: float = 30.0
    demo_mode: bool = True
    db_path: str = "agentshield.db"
    # repr=False keeps the token out of logs / tracebacks
    admin_token: str = field(default="", repr=False)
    approval_ttl_seconds: int = 900
    max_agent_iterations: int = 5
    max_tool_calls_per_iteration: int = 3
    policy_overrides: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        return cls(
            ollama_base_url=e("OLLAMA_BASE_URL", "http://localhost:11434"),
            ollama_model=e("OLLAMA_MODEL", "llama3.1:8b"),
            ollama_timeout=_float(e("OLLAMA_TIMEOUT_SECONDS"), 30.0),
            demo_mode=_bool(e("AGENTSHIELD_DEMO_MODE"), True),
            db_path=e("AGENTSHIELD_DB_PATH", "agentshield.db"),
            admin_token=e("AGENTSHIELD_ADMIN_TOKEN", ""),
            approval_ttl_seconds=_int(e("AGENTSHIELD_APPROVAL_TTL_SECONDS"), 900),
            max_agent_iterations=min(_int(e("AGENTSHIELD_MAX_AGENT_ITERATIONS"), 5), 5),
            policy_overrides=_json_dict(e("AGENTSHIELD_POLICY_OVERRIDES")),
        )
