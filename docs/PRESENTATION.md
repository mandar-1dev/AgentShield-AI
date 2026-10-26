# Hacktoberfest demo script (~4 min)
1. **Hook (20s):** "AI agents can call tools. What if the model is tricked? We treat model output like untrusted user input."
2. **Show architecture** (README Mermaid): model → *AgentShield gateway* → tools.
3. **Dashboard → Security Demos:** run 1 (ALLOWED), 3 (unknown tool BLOCKED), 4 (bad/extra args BLOCKED), 6 (restricted BLOCKED).
4. **Approval:** run 5 → PENDING_APPROVAL → Approval Queue → Approve → executed once. Click Approve again/API replay → `409`.
5. **Audit Explorer:** filter BLOCKED; point out redacted args.
6. **Real mode (optional):** set `AGENTSHIELD_DEMO_MODE=false`, ask "what is the status?" - badge shows `ollama:llama3.1:8b`.
7. **Tests:** `python -m pytest -q` → 60 pass, no model required.
8. **Close:** limitations slide (shared token, no sandbox) - honesty = credibility.

# 60-second explanation for judges
"The LLM only *proposes* actions. Our gateway runs a fixed pipeline: allowlist, strict schema validation, policy, optional human approval, then execution, and logs everything to SQLite. Security lives in backend code, not in prompts, so it's deterministic and unit-testable without a model. Approvals are single-use and atomic, so they can't be replayed, and the approver approves an ID - never new arguments."

# Likely judge questions
- *Why not just prompt the model to be safe?* Prompts aren't a security boundary; injection can override them.
- *What if the model lies about arguments?* Schemas validate type/range/extras; unknown fields are rejected.
- *Is it production-ready?* No - see SECURITY.md limitations.

# GitHub checklist
- [ ] `.env` is NOT committed (`git status`); only `.env.example`
- [ ] No `*.db` files committed; no model files
- [ ] `python -m pytest -q` passes
- [ ] README renders Mermaid; add 2-3 dashboard screenshots to `docs/img/`
- [ ] Add LICENSE (MIT) and topics: `hacktoberfest`, `ai-security`, `llm`, `ollama`, `fastapi`
- [ ] `git init && git add . && git commit -m "feat: AgentShield AI"`; push; add CONTRIBUTING + good-first-issues
