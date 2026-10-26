"""FastAPI application."""
from __future__ import annotations

import hmac
import logging
import uuid
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.agent.service import scenarios_public
from app.config import Settings
from app.container import build_container
from app.schemas import AgentRunRequest, AgentRunResponse, GatewayResult, UserContext
from app.services.approvals import ApprovalError

log = logging.getLogger("agentshield")

DESCRIPTION = """Security gateway for local AI agents.

* **BLOCKED** - policy/validation rejected the request; nothing ran.
* **PENDING_APPROVAL** - allowed in principle, waiting for a human; nothing ran yet.
* **ALLOWED/APPROVED + FAILED** - authorized, but the tool raised an error while executing.
"""


def _err(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "error": code, "message": message,
        "request_id": getattr(request.state, "request_id", "unknown")})


def create_app(settings: Optional[Settings] = None, ollama_client: Any = None) -> FastAPI:
    settings = settings or Settings.from_env()
    c = build_container(settings, ollama_client)
    app = FastAPI(title="AgentShield AI", version=__version__, description=DESCRIPTION)
    app.state.container = c

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApprovalError)
    async def _approval_err(request: Request, exc: ApprovalError):
        return _err(request, exc.status_code, "approval_error", exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_err(request: Request, exc: StarletteHTTPException):
        return _err(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _val_err(request: Request, exc: RequestValidationError):
        details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        return _err(request, 422, "validation_error", details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error")  # details stay in server logs only
        return _err(request, 500, "internal_error", "Internal server error")

    def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> str:
        expected = c.settings.admin_token
        if (not expected or not x_admin_token or
                not hmac.compare_digest(x_admin_token.encode(), expected.encode())):
            raise HTTPException(status_code=401, detail="Administrator authentication required")
        return "local-admin"

    # ---------- health ----------
    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "database": "up" if c.db.healthy() else "down",
                "mode": "demo" if c.settings.demo_mode else "ollama",
                "model": c.settings.ollama_model, "version": __version__,
                "admin_configured": bool(c.settings.admin_token),
                "request_id": request.state.request_id}

    @app.get("/health/ollama")
    def health_ollama(request: Request):
        return {**c.ollama.health(), "mode": "demo" if c.settings.demo_mode else "ollama",
                "request_id": request.state.request_id}

    # ---------- agent ----------
    @app.get("/api/scenarios")
    def scenarios():
        return scenarios_public()

    @app.post("/api/agent/run", response_model=AgentRunResponse)
    def run_agent(body: AgentRunRequest, request: Request):
        resp = c.agent.run(body.message, body.scenario, UserContext(), request.state.request_id)
        code = {"MODEL_UNAVAILABLE": 503, "MODEL_BAD_RESPONSE": 502}.get(resp.error_code or "", 200)
        return JSONResponse(status_code=code, content=resp.model_dump(mode="json"))

    # ---------- tools / audit / metrics ----------
    @app.get("/api/tools")
    def tools():
        out = []
        for t in c.registry.list():
            perm = c.policy.effective_permission(t)
            availability = {"public": "available", "approval_required": "requires_approval",
                            "restricted": "blocked"}.get(perm.value if perm else "", "blocked")
            out.append({"name": t.name, "description": t.description,
                        "permission": perm.value if perm else "unclassified",
                        "availability": availability,
                        "arguments_schema": t.args_model.model_json_schema(),
                        "result_schema": t.result_model.model_json_schema()})
        return out

    @app.get("/api/audit")
    def audit(decision: Optional[str] = Query(None, max_length=32),
              tool: Optional[str] = Query(None, max_length=64),
              limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        return {"events": c.audit.list(decision, tool, limit, offset), "limit": limit, "offset": offset}

    @app.get("/api/metrics")
    def metrics():
        return {**c.audit.metrics(), "pending_approvals": c.approvals.pending_count(),
                "mode": "demo" if c.settings.demo_mode else "ollama"}

    # ---------- approvals (admin only) ----------
    @app.get("/api/approvals")
    def approvals(status: Optional[str] = Query(None, max_length=16), _: str = Depends(require_admin)):
        return {"approvals": c.approvals.list(status)}

    @app.post("/api/approvals/{approval_id}/approve", response_model=GatewayResult)
    def approve(approval_id: str, request: Request, admin: str = Depends(require_admin)):
        return c.gateway.decide_approval(approval_id[:64], True, admin, request.state.request_id)

    @app.post("/api/approvals/{approval_id}/reject", response_model=GatewayResult)
    def reject(approval_id: str, request: Request, admin: str = Depends(require_admin)):
        return c.gateway.decide_approval(approval_id[:64], False, admin, request.state.request_id)

    return app


app = create_app()
