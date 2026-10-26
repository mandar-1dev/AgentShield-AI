# Security

## Threat model
**Asset:** the tools/data an agent can reach. **Attacker:** a malicious or injected prompt, a hallucinating model, a malicious tool-result, or a local user poking the API.
**Core assumption:** *model output is untrusted input*, exactly like a web form.

## Trust boundaries
```
[User text] -> [LLM: UNTRUSTED] -> | GATEWAY (trusted code) | -> [Registered tools]
                                      ^ admin token ^
```

## Attack scenarios and mitigations
| Attack | Mitigation | Test |
|---|---|---|
| Model calls a tool that doesn't exist (`delete_all_files`) | Registry allowlist, default deny | `test_unknown_tool_blocked` |
| Prompt injection asks for admin/extra params | `extra="forbid"` schemas | `test_extra_arguments_rejected` |
| Out-of-range / wrong-type args | Pydantic constraints | `test_invalid_arguments_rejected` |
| Calling a restricted tool | Policy → BLOCKED | `test_restricted_action_blocked` |
| Sensitive tool run without a human | PENDING_APPROVAL, no execution | `test_sensitive_request_creates_pending_approval` |
| Replaying / double-clicking approval | Atomic status transition | `test_replay_cannot_execute_twice` |
| Approving a stale request | Expiry check (410) | `test_expired_approval_cannot_execute` |
| Non-admin approves | `X-Admin-Token` constant-time compare | `test_approval_endpoints_require_admin` |
| Secrets in logs/responses | Key-based redaction, truncation, no tokens in responses | `test_secrets_not_in_audit` |
| SQL injection via filters | Parameterised queries | `test_sql_injection_in_filter_is_harmless` |
| Infinite agent loop | Max 5 iterations, max 3 calls/iteration | `test_loop_stops_at_maximum` |
| Model outage / junk output | Typed errors, 503/502, nothing executed | `test_agent.py` |
| Stack-trace leaks | Generic 500 handler | `test_error_responses_do_not_leak` |

## Not allowed by design
No shell, `eval`/`exec`, dynamic imports, filesystem writes or real credentials. All tools are simulated.

## Limitations (be honest with judges)
- Shared dev token only: no users, roles, MFA, rotation or per-admin audit identity.
- No rate limiting, TLS, CSRF/CORS hardening - bind to `127.0.0.1` only.
- Audit log is plain SQLite: not tamper-evident, no retention policy.
- Tools have no execution timeout/sandbox; real tools would need OS-level sandboxing.
- Sanitising is key-name based: a secret pasted into a free-text field could be stored (truncated). Real systems need DLP-style scanning.
- Indirect prompt injection in tool *results* is only mitigated by the architecture (results can't grant permissions), not detected.
- Policy is static per tool; no per-argument, per-user or contextual rules.

## Production would need
Real authN/authZ (OIDC + RBAC), signed/append-only audit storage, rate limits, sandboxed tool workers with timeouts, secrets manager, monitoring/alerting, TLS, and a security review.
