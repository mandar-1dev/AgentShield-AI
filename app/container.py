"""Wires all components together (simple dependency container)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.agent.ollama_client import OllamaClient
from app.agent.service import AgentService
from app.config import Settings
from app.database import Database
from app.security.gateway import SecurityGateway
from app.security.policies import PolicyEngine
from app.services.approvals import ApprovalService
from app.services.audit import AuditService
from app.tools.registry import ToolRegistry
from app.tools.safe_tools import build_default_registry


@dataclass
class Container:
    settings: Settings
    db: Database
    registry: ToolRegistry
    policy: PolicyEngine
    audit: AuditService
    approvals: ApprovalService
    gateway: SecurityGateway
    ollama: Any
    agent: AgentService


def build_container(settings: Settings, ollama_client: Optional[Any] = None,
                    registry: Optional[ToolRegistry] = None) -> Container:
    db = Database(settings.db_path)
    db.init()
    registry = registry or build_default_registry()
    policy = PolicyEngine(settings.policy_overrides)
    audit = AuditService(db)
    approvals = ApprovalService(db, settings.approval_ttl_seconds)
    gateway = SecurityGateway(registry, policy, audit, approvals)
    ollama = ollama_client or OllamaClient(settings.ollama_base_url, settings.ollama_model,
                                           settings.ollama_timeout)
    agent = AgentService(gateway, ollama, settings)
    return Container(settings, db, registry, policy, audit, approvals, gateway, ollama, agent)
