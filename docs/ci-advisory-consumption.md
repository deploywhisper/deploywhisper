# CI Advisory Consumption

DeployWhisper remains advisory in automation contexts.

- `data.advisory.should_block` is always `false`
- `data.advisory.requires_attention` tells the pipeline or PR bot whether humans should take a closer look
- `data.share_summary` provides a ready-to-render PR / approval-thread summary in both `markdown` and `plain_text`
- `data.share_summary.markdown` is capped at 1,500 characters for GitHub PR comment fit
- `data.share_summary.json_payload` provides the machine-friendly summary variant, including `report_schema_version`, top findings, evidence count, context completeness, and report / rollback links
- Share-summary report links always resolve to an absolute `/reports/{id}` URL; set `APP_BASE_URL` when you need those links to point at a public/reverse-proxied DeployWhisper instance instead of the local app host/port
- Sensitive shared reports can opt into password protection and file-name redaction through `POST /api/v1/analyses/{id}/share`
- The share-configuration API is disabled unless `DEPLOYWHISPER_SHARE_TOKEN` is set; callers must send that value in `X-DeployWhisper-Share-Token`
- CLI and API responses preserve `severity`, `recommendation`, `partial_context`, and `narrative_degraded` for machine-readable uncertainty handling
- High-risk or degraded analyses still return success payloads; non-zero CLI exit codes are reserved for operational failures such as unreadable files, missing project scope, or shared-analysis crashes

## CLI Example

```bash
deploywhisper analyze --project payments plan.json > advisory.json
python - <<'PY'
import json
payload = json.load(open("advisory.json", encoding="utf-8"))
print(payload["data"]["share_summary"]["plain_text"])
PY
```

## API Example

```bash
curl -sS -X POST http://localhost:8080/api/v1/analyses \
  -F "project_key=payments" \
  -F "files=@plan.json" \
  > advisory.json
python - <<'PY'
import json
payload = json.load(open("advisory.json", encoding="utf-8"))
advisory = payload["data"]["advisory"]
summary = payload["data"]["share_summary"]
print(summary["markdown"])
print(summary["json_payload"]["report_schema_version"])
print(summary["json_payload"]["rollback_link"])
print("DeployWhisper blocking decision:", advisory["should_block"])
PY
```

## CI Guidance

- Do not use DeployWhisper to fail a pipeline based only on risk score or recommendation in v1
- Use `requires_attention` and `uncertainty_flags` to decide when to notify reviewers, enrich PR comments, or request additional manual checks
- Treat non-zero CLI exit codes as operational failures, not advisory outcomes
