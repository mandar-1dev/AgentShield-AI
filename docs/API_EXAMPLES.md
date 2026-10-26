# API examples
Interactive docs: `http://127.0.0.1:8000/docs`. Admin endpoints need header `X-Admin-Token`.

## Run a scenario
```bash
curl -X POST http://127.0.0.1:8000/api/agent/run -H "Content-Type: application/json" -d '{"scenario":3}'
```
```json
{"request_id":"9f2c...","mode":"demo","source":"demo_engine","status":"COMPLETED",
 "final_message":"[Demo engine - not a real AI model] delete_all_files: BLOCKED/NOT_EXECUTED - Unknown tool - not in registry allowlist",
 "tool_calls":[{"proposed_tool":"delete_all_files","proposed_arguments":{"path":"/"},
   "outcome":{"decision":"BLOCKED","execution_status":"NOT_EXECUTED","reason":"Unknown tool - not in registry allowlist","result":null,"approval_id":null}}]}
```

## Sensitive report → pending approval
```bash
curl -X POST http://127.0.0.1:8000/api/agent/run -H "Content-Type: application/json" -d '{"scenario":5}'
# outcome.decision = "PENDING_APPROVAL", outcome.approval_id = "<id>"
curl http://127.0.0.1:8000/api/approvals -H "X-Admin-Token: $TOKEN"
curl -X POST http://127.0.0.1:8000/api/approvals/<id>/approve -H "X-Admin-Token: $TOKEN"
```
```json
{"decision":"APPROVED","execution_status":"EXECUTED","tool_name":"request_sensitive_report",
 "result":{"ticket_id":"TKT-1A2B3C4D","report_id":"RPT-001","status":"access_request_filed","note":"Simulated request only; no report content is returned."}}
```
Second approve → `409 {"error":"approval_error","message":"Approval request already processed (EXECUTED)"}`.
Expired → `410`. Unknown → `404`. Missing/wrong token → `401`.

## Audit / metrics / tools
```bash
curl "http://127.0.0.1:8000/api/audit?decision=BLOCKED&tool=search_demo_records&limit=20&offset=0"
curl http://127.0.0.1:8000/api/metrics
curl http://127.0.0.1:8000/api/tools
curl http://127.0.0.1:8000/health/ollama
```

## Error shape
```json
{"error":"validation_error","message":"scenario: Input should be less than or equal to 7","request_id":"..."}
```
Model down in real mode → `503 {"status":"ERROR","error_code":"MODEL_UNAVAILABLE",...}`.
