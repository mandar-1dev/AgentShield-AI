"""Input validation and log sanitising."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from app.tools.registry import TOOL_NAME_RE, ToolSpec


class ValidationFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


SENSITIVE_KEYS = ("token", "password", "passwd", "secret", "api_key", "apikey",
                  "authorization", "credential", "cookie", "private_key")


def validate_tool_name(name: Any) -> str:
    if not isinstance(name, str) or not TOOL_NAME_RE.match(name):
        raise ValidationFailure("Tool name is missing or has an invalid format")
    return name


def validate_arguments(spec: ToolSpec, arguments: Any) -> BaseModel:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValidationFailure("Arguments must be a JSON object")
    try:
        return spec.args_model.model_validate(arguments)
    except ValidationError as exc:
        # Only location + message: never echo the offending input value.
        parts = [f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
                 for e in exc.errors()[:5]]
        raise ValidationFailure("Invalid arguments - " + "; ".join(parts))


def safe_tool_label(name: Any) -> str | None:
    """A tool name that is safe to store/display (model output is untrusted)."""
    if name is None:
        return None
    if isinstance(name, str) and TOOL_NAME_RE.match(name):
        return name
    return "<invalid_tool_name>"


def sanitize_arguments(args: Any, max_len: int = 80, _depth: int = 0) -> Any:
    """Redact secret-looking keys and truncate long values for audit logs/UI."""
    if _depth > 3:
        return "<nested>"
    if isinstance(args, dict):
        out = {}
        for i, (k, v) in enumerate(args.items()):
            if i >= 20:
                out["..."] = "truncated"
                break
            key = str(k)[:40]
            if any(s in key.lower() for s in SENSITIVE_KEYS):
                out[key] = "[REDACTED]"
            else:
                out[key] = sanitize_arguments(v, max_len, _depth + 1)
        return out
    if isinstance(args, (list, tuple)):
        return [sanitize_arguments(v, max_len, _depth + 1) for v in list(args)[:10]]
    if isinstance(args, str):
        return args if len(args) <= max_len else args[:max_len] + "...[truncated]"
    if isinstance(args, (int, float, bool)) or args is None:
        return args
    return f"<{type(args).__name__}>"
