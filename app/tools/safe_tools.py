"""Safe, simulated tools. None touch the shell, filesystem, network or real data."""
from __future__ import annotations

import random
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import Permission
from app.tools.registry import ToolRegistry, ToolSpec

DEMO_RECORDS = [  # entirely fictional
    {"id": "REC-001", "name": "Alice Example", "department": "Research", "status": "active"},
    {"id": "REC-002", "name": "Bob Sample", "department": "Engineering", "status": "active"},
    {"id": "REC-003", "name": "Carol Placeholder", "department": "Research", "status": "inactive"},
    {"id": "REC-004", "name": "Dave Fictional", "department": "Operations", "status": "active"},
    {"id": "REC-005", "name": "Eve Imaginary", "department": "Engineering", "status": "inactive"},
    {"id": "REC-006", "name": "Frank Demo", "department": "Support", "status": "active"},
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unexpected arguments are rejected


# ---- argument schemas ----
class NoArgs(_Strict):
    pass


class SearchArgs(_Strict):
    query: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9 _\-]+$")
    limit: int = Field(default=5, ge=1, le=10)


class ReportArgs(_Strict):
    report_id: str = Field(pattern=r"^RPT-\d{3}$")
    reason: str = Field(min_length=5, max_length=200)


class RestrictedArgs(_Strict):
    action: str = Field(min_length=1, max_length=100)


# ---- result schemas ----
class PublicStatusResult(BaseModel):
    app_name: str
    version: str
    status: str
    note: str


class SearchResult(BaseModel):
    count: int
    records: list[dict]


class HealthResult(BaseModel):
    cpu_percent: float
    services: dict[str, str]
    request_count: int
    simulated: bool = True


class ReportRequestResult(BaseModel):
    ticket_id: str
    report_id: str
    status: str
    note: str


class RestrictedResult(BaseModel):
    performed: bool
    note: str


# ---- implementations ----
def get_public_status(_: NoArgs) -> PublicStatusResult:
    return PublicStatusResult(
        app_name="AgentShield Demo App", version="1.0.0", status="operational",
        note="Simulated, non-sensitive status.",
    )


def search_demo_records(args: SearchArgs) -> SearchResult:
    q = args.query.lower()
    hits = [r for r in DEMO_RECORDS if q in " ".join(r.values()).lower()][: args.limit]
    return SearchResult(count=len(hits), records=hits)


def get_system_health(_: NoArgs) -> HealthResult:
    rng = random.Random()
    return HealthResult(
        cpu_percent=round(rng.uniform(5, 40), 1),
        services={"api": "up", "database": "up", "worker": "up"},
        request_count=rng.randint(100, 900),
    )


def request_sensitive_report(args: ReportArgs) -> ReportRequestResult:
    # Never returns report content: it only files a (simulated) access ticket.
    return ReportRequestResult(
        ticket_id=f"TKT-{uuid.uuid4().hex[:8].upper()}", report_id=args.report_id,
        status="access_request_filed",
        note="Simulated request only; no report content is returned.",
    )


def simulate_restricted_action(args: RestrictedArgs) -> RestrictedResult:
    return RestrictedResult(performed=False, note="Blocked by default policy; no side effects.")


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec("get_public_status", "Get simulated public application status.",
                          NoArgs, PublicStatusResult, Permission.PUBLIC, get_public_status))
    reg.register(ToolSpec("search_demo_records", "Search fictional demo records by keyword.",
                          SearchArgs, SearchResult, Permission.PUBLIC, search_demo_records))
    reg.register(ToolSpec("get_system_health", "Get simulated system health metrics.",
                          NoArgs, HealthResult, Permission.PUBLIC, get_system_health))
    reg.register(ToolSpec("request_sensitive_report",
                          "Request access to a fictional sensitive report (needs human approval).",
                          ReportArgs, ReportRequestResult, Permission.APPROVAL_REQUIRED,
                          request_sensitive_report))
    reg.register(ToolSpec("simulate_restricted_action",
                          "Fictional restricted action used for security demos (always blocked).",
                          RestrictedArgs, RestrictedResult, Permission.RESTRICTED,
                          simulate_restricted_action))
    return reg
