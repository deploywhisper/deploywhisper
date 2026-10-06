import { test, expect } from "@playwright/test";

test("connector imports redact credentials before API and rendered context", async ({ page, request }, testInfo) => {
  const key = `connector-security-${Date.now()}`;
  const name = `Connector audit ${Date.now()}`;
  const secret = "synthetic-connector-browser-credential";
  const created = await request.post("/api/v1/projects", { data: { project_key: key, display_name: name } });
  expect(created.ok()).toBeTruthy();
  const project = (await created.json()).data;
  const topology = await request.put("/api/v1/settings/topology", { data: {
    project_id: project.id,
    topology: { services: [{ id: "api", label: `token=${secret}`, resource_keys: ["Deployment/api"], downstream: [] }] },
  } });
  expect(topology.ok()).toBeTruthy();
  expect(JSON.stringify(await topology.json())).not.toContain(secret);
  const incident = await request.post("/api/v1/incidents/reindex", { data: { project_id: project.id, files: [{ source_file: "audit.json", content: JSON.stringify({
    title: `Connector ${secret}`, severity: "high", incident_date: "2026-10-01", root_cause: "Deployment failure", trigger_change: "Deployment rollout",
    affected_services: ["api"], rollback_path: "Restore config", prevention_notes: ["Review connector scope"],
    source: { system: "manual", reference: "AUDIT-12-3" }, redaction: { status: "redacted", contains_sensitive_data: false }, connector: { api_key: secret },
  }) }] } });
  expect(incident.ok()).toBeTruthy();
  expect(JSON.stringify(await incident.json())).not.toContain(secret);
  const scanner = await request.post("/api/v1/scanner-imports/sarif", { data: {
    project_id: project.id, source_file: "audit.sarif", content: JSON.stringify({ version: "2.1.0", runs: [{ tool: { driver: { name: "Synthetic" } }, results: [{
      ruleId: "AUDIT", message: { text: `Connector ${secret}` }, level: "warning", properties: { api_key: secret },
      locations: [{ physicalLocation: { artifactLocation: { uri: "playbook.yaml" }, region: { startLine: 1, snippet: { text: `raw ${secret}` }, credential: secret } } }],
    }] }] }),
  } });
  expect(scanner.ok()).toBeTruthy();
  const evidence = (await scanner.json()).data.evidence;
  expect(JSON.stringify(evidence)).not.toContain(secret);
  expect(evidence[0].region).toEqual({ startLine: 1 });

  await page.goto("/incidents", { waitUntil: "networkidle" });
  await page.locator(".dw-project-trigger").click();
  await page.getByPlaceholder("Search projects...").fill(name);
  await page.getByRole("option", { name: new RegExp(name) }).click();
  await expect(page.locator("body")).toContainText("REDACTED");
  await expect(page.locator("body")).not.toContainText(secret);
  await page.screenshot({ path: testInfo.outputPath("connector-incidents.png"), fullPage: true });

  const run = await request.post("/api/v1/analyses", { multipart: { project_id: String(project.id), files: { name: "playbook.yaml", mimeType: "application/x-yaml", buffer: Buffer.from("hosts: all\ntasks:\n  - name: Review rollout\n    debug:\n      msg: safe\n") } } });
  expect(run.ok()).toBeTruthy();
  const data = (await run.json()).data;
  expect(JSON.stringify(data)).not.toContain(secret);
  const id = data.persisted_report.id;
  const report = await request.get(`/api/v1/analyses/${id}`);
  expect(report.ok()).toBeTruthy();
  expect(JSON.stringify(await report.json())).not.toContain(secret);
  await page.goto(`/reports/${id}?private=1&tab=audit`);
  await expect(page.getByText("Content redaction", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(secret);
  await page.screenshot({ path: testInfo.outputPath("connector-report.png"), fullPage: true });
});
