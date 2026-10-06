import { test, expect } from "@playwright/test";

test("connector imports redact scanner API context and matched incident report context", async ({ page, request }, testInfo) => {
  test.skip(process.env.CONNECTOR_SECURITY_TEST_DISPOSABLE !== "1", "Requires an explicitly disposable Compose database; creates persistent project/import/report fixtures.");
  const key = `connector-security-${Date.now()}`;
  const name = `Connector audit ${Date.now()}`;
  const secret = "synthetic-connector-browser/credential!";
  const filenameSecret = "synthetic-filename-only/credential!";
  const numericSecret = 739241;
  const encodings = [secret];
  for (let round = 0; round < 5; round++) encodings.push(encodeURIComponent(encodings[encodings.length - 1]));
  const encodedSecret = encodings[5];
  const assertScreened = (value: unknown) => {
    const text = typeof value === "string" ? value : JSON.stringify(value);
    for (const variant of [...encodings, filenameSecret, encodeURIComponent(filenameSecret), String(numericSecret)]) expect(text).not.toContain(variant);
  };
  const created = await request.post("/api/v1/projects", { data: { project_key: key, display_name: name } });
  expect(created.ok()).toBeTruthy();
  const project = (await created.json()).data;
  const topology = await request.put("/api/v1/settings/topology", { data: {
    project_id: project.id,
    topology: { connector: { password: secret }, services: [{ id: "api", label: encodedSecret, owner: encodedSecret, owners: [encodedSecret], resource_keys: ["Deployment/api", encodedSecret], downstream: [] }] },
  } });
  expect(topology.ok()).toBeTruthy();
  assertScreened(await topology.json());
  const incident = await request.post("/api/v1/incidents/reindex", { data: { project_id: project.id, files: [{ source_file: "audit.json", content: JSON.stringify({
    title: `Connector ${secret}`, severity: "high", incident_date: "2026-10-01", root_cause: `Deployment failure ${encodedSecret}`, trigger_change: "Deployment rollout",
    affected_services: ["api"], rollback_path: "Restore config", prevention_notes: ["Review connector scope"],
    source: { system: "manual", reference: "AUDIT-12-3" }, redaction: { status: "redacted", contains_sensitive_data: false }, connector: { api_key: secret },
  }) }, {
    source_file: `password='${filenameSecret}'.json`, content: JSON.stringify({
      title: `Filename ${filenameSecret}`, severity: "high", incident_date: "2026-10-01", root_cause: filenameSecret,
      trigger_change: "Deployment rollout", affected_services: ["api"], rollback_path: "Restore config", prevention_notes: [filenameSecret],
      source: { system: "manual", reference: "FILENAME-12-3" }, redaction: { status: "none", contains_sensitive_data: false },
    }),
  }, {
    source_file: "filename-sibling.json", content: JSON.stringify({
      title: `Sibling ${filenameSecret}`, severity: "high", incident_date: "2026-10-01", root_cause: filenameSecret,
      trigger_change: "Deployment rollout", affected_services: ["api"], rollback_path: "Restore config", prevention_notes: [filenameSecret],
      source: { system: "manual", reference: "SIBLING-12-3" }, redaction: { status: "none", contains_sensitive_data: false },
    }),
  }, {
    source_file: "numeric.json", content: JSON.stringify({
      title: numericSecret, severity: "high", incident_date: "2026-10-01", root_cause: numericSecret,
      trigger_change: "Numeric configuration rotation", affected_services: ["numeric-only"], rollback_path: "Restore config", prevention_notes: ["Review credentials"],
      source: { system: "manual", reference: "NUMERIC-12-3" }, redaction: { status: "none", contains_sensitive_data: false }, connector: { password: numericSecret },
    }),
  }] } });
  expect(incident.ok()).toBeTruthy();
  const imported = (await incident.json()).data;
  assertScreened(imported);
  expect(imported.indexed_count).toBe(4);
  expect(imported.status.sources.find((source: { import_source: string }) => source.import_source === "numeric.json")).toMatchObject({ title: "[REDACTED]", redaction_status: "redacted" });
  expect(imported.status.sources.find((source: { title: string }) => source.title === "Filename [REDACTED]").import_source).toMatch(/^\[REDACTED\]-[a-f0-9]+\.json$/);
  expect(imported.status.sources.find((source: { import_source: string }) => source.import_source === "filename-sibling.json").title).toBe("Sibling [REDACTED]");
  const oauthState = "synthetic oauth state";
  const scopeError = await request.post("/api/v1/incidents/reindex", { data: {
    project_id: project.id, project_key: "synthetic-oauth-state", files: [{ source_file: "scope.json", content: JSON.stringify({
      reference: "https://example.invalid/callback?state=synthetic+oauth+state", title: oauthState,
    }) }],
  } });
  expect(scopeError.status()).toBe(404);
  const scopeBody = await scopeError.json();
  expect(scopeBody.error.code).toBe("project_not_found");
  expect(JSON.stringify(scopeBody)).not.toContain("synthetic-oauth-state");
  const scanner = await request.post("/api/v1/scanner-imports/sarif", { data: {
    project_id: project.id, source_file: "audit.sarif", content: JSON.stringify({ version: "2.1.0", runs: [{ tool: { driver: { name: "Synthetic" } }, results: [{
      ruleId: "AUDIT", message: { text: `Connector ${secret}` }, level: "warning", properties: { api_key: secret },
      locations: [{ physicalLocation: { artifactLocation: { uri: "deployment.yaml" }, region: { startLine: 1, snippet: { text: `raw ${secret}` }, credential: secret } } }],
    }] }] }),
  } });
  expect(scanner.ok()).toBeTruthy();
  const evidence = (await scanner.json()).data.evidence;
  assertScreened(evidence);
  expect(evidence).toHaveLength(1);
  expect(evidence[0]).toMatchObject({ tool_name: "Synthetic", rule_id: "AUDIT", artifact_uri: "deployment.yaml" });
  expect(evidence[0].message).toContain("REDACTED");
  expect(evidence[0].region).toEqual({ startLine: 1 });
  const encodedScanner = await request.post("/api/v1/scanner-imports/sarif", { data: {
    project_id: project.id, source_file: "encoded.sarif", content: JSON.stringify({ password: secret, version: "2.1.0", runs: [{
      tool: { driver: { name: encodedSecret, rules: [{ id: encodedSecret, shortDescription: { text: encodedSecret } }] } },
      results: [{ ruleId: encodedSecret, message: { text: encodedSecret }, level: "warning",
        locations: [{ physicalLocation: { artifactLocation: { uri: "deployment.yaml" }, region: { startLine: 1 } } }],
      }],
    }] }),
  } });
  expect(encodedScanner.ok()).toBeTruthy();
  const encodedEvidence = (await encodedScanner.json()).data;
  assertScreened(encodedEvidence);
  expect(encodedEvidence.tool_names).toEqual(["[REDACTED]"]);
  expect(encodedEvidence.evidence[0]).toMatchObject({ tool_name: "[REDACTED]", rule_id: "[REDACTED]", rule_name: "[REDACTED]", message: "[REDACTED]" });

  await page.goto("/incidents", { waitUntil: "networkidle" });
  await page.locator(".dw-project-trigger").click();
  await page.getByPlaceholder("Search projects...").fill(name);
  await page.getByRole("option", { name: new RegExp(name) }).click();
  await expect(page.locator("body")).toContainText("REDACTED");
  await expect(page.locator("body")).not.toContainText(secret);
  assertScreened(await page.locator("body").innerText());
  await page.screenshot({ path: testInfo.outputPath("connector-incidents.png"), fullPage: true });

  const run = await request.post("/api/v1/analyses", { multipart: { project_id: String(project.id), files: { name: "deployment.yaml", mimeType: "application/x-yaml", buffer: Buffer.from("apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\nspec:\n  replicas: 2\n  selector:\n    matchLabels:\n      app: api\n  template:\n    metadata:\n      labels:\n        app: api\n    spec:\n      containers:\n        - name: api\n          image: example.invalid/api:v2\n") } } });
  expect(run.ok()).toBeTruthy();
  const data = (await run.json()).data;
  assertScreened(data);
  const id = data.persisted_report.id;
  const report = await request.get(`/api/v1/analyses/${id}`);
  expect(report.ok()).toBeTruthy();
  const savedReport = (await report.json()).data;
  assertScreened(savedReport);
  const importedMatch = savedReport.incident_matches.find((match: { source_file: string }) => match.source_file === "audit.json");
  expect(importedMatch).toBeDefined();
  expect(importedMatch).toMatchObject({ match_type: "organization_incident", source_file: "audit.json" });
  expect(importedMatch.title).toContain("Connector");
  expect(importedMatch.title).toContain("REDACTED");
  expect(importedMatch.affected_services).toContain("api");
  // Imported scanner findings are currently standalone API context; analysis
  // does not attach them to reports. Verify their identity above, rather than
  // treating an unrelated report audit panel as scanner propagation coverage.
  await page.goto(`/reports/${id}?private=1`);
  await expect(page.getByText(importedMatch.title, { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(secret);
  assertScreened(await page.locator("body").innerText());
  await page.screenshot({ path: testInfo.outputPath("connector-report-context.png"), fullPage: true });
  await page.goto(`/reports/${id}?private=1&tab=audit`);
  await expect(page.getByText("Content redaction", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(secret);
  assertScreened(await page.locator("body").innerText());
  await page.screenshot({ path: testInfo.outputPath("connector-report.png"), fullPage: true });
});
