# Architecture

## Components
| Component | File | Job |
|---|---|---|
| API | `app/main.py` | HTTP endpoints, request IDs, admin auth, safe errors |
| Agent service | `app/agent/service.py` | Runs the (bounded, max 5) plan loop; demo engine; only *proposes* calls |
| Ollama client | `app/agent/ollama_client.py` | Talks to Ollama; maps failures to typed errors |
| Gateway | `app/security/gateway.py` | The single path to execution |
| Validators | `app/security/validators.py` | Tool-name check, Pydantic arg validation, log sanitising |
| Policy engine | `app/security/policies.py` | permission class → decision, default deny |
| Tool registry | `app/tools/*` | Allowlist of tools with arg/result schemas |
| Audit / Approvals | `app/services/*` | SQLite persistence |
| Dashboard | `dashboard/app.py` | Streamlit UI; calls API only |

## Data flow
1. `POST /api/agent/run` → agent service.
2. Model (or demo engine) proposes `(tool_name, arguments)` - **untrusted**.
3. Gateway: name format → registry allowlist → Pydantic validation (extra fields rejected) → policy.
4. `BLOCKED` → audit, return. `PENDING_APPROVAL` → store *validated* args + expiry, audit, return.
   `ALLOWED` → run the registered Python callable, validate result schema, audit.
5. Admin approves → `claim()` atomically flips `PENDING→APPROVED` (SQL `UPDATE ... WHERE status='PENDING'`), then the **stored** args are re-validated, policy re-checked, executed once.

## Design decisions
- **Gateway is independent of Ollama** → security tests need no model.
- **Decision vs execution are separate fields** so "authorized but failed" is representable.
- **Atomic single-use approvals** via conditional SQL update → replay and double-click safe.
- **Approve takes only an ID**, never arguments → the approver can't be tricked into running something different.
- **Errors never echo input** (validation messages contain field + message only).
- **Per-operation SQLite connections** → simple and thread-safe for a demo.
- **Result schemas** make tool output predictable before it returns to the model/UI.
