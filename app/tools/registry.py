"""Tool registry = the allowlist. Only tools registered here can ever run."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional, Type

from pydantic import BaseModel

from app.schemas import Permission

TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: Type[BaseModel]
    result_model: Type[BaseModel]
    permission: Permission
    func: Callable[[BaseModel], BaseModel]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not TOOL_NAME_RE.match(spec.name):
            raise ValueError(f"Invalid tool name: {spec.name!r}")
        if spec.name in self._tools:
            raise ValueError(f"Duplicate tool: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def ollama_tool_specs(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.args_model.model_json_schema(),
                },
            }
            for t in self._tools.values()
        ]
