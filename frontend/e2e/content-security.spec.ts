import { test, expect } from "@playwright/test";

test("redacts sensitive upload content and exposes the outcome to reviewers", async ({ page, request }) => {
  const projectKey = `content-security-${Date.now()}`;
  const project = await request.post("/api/v1/projects", {
    data: { project_key: projectKey, display_name: "Content boundary audit" },
  });
  expect(project.ok()).toBeTruthy();
  const secret = "synthetic-browser-credential";
  const run = await request.post("/api/v1/analyses", {
    multipart: {
      project_key: projectKey,
      files: {
        name: "playbook.yaml",
        mimeType: "application/x-yaml",
        buffer: Buffer.from(`hosts: all\ntasks:\n  - name: Configure password=${secret}\n    debug:\n      msg: safe\n`),
      },
    },
  });
  expect(run.ok()).toBeTruthy();
  const data = (await run.json()).data;
  expect(JSON.stringify(data)).not.toContain(secret);
  const reportId = data.persisted_report.id;
  const detail = await request.get(`/api/v1/analyses/${reportId}`);
  expect(detail.ok()).toBeTruthy();
  const report = (await detail.json()).data;
  expect(JSON.stringify(report)).not.toContain(secret);
  expect(report.audit.redaction_status).toBe("redacted");
  expect(report.evidence_items[0].redaction_status).toBe("redacted");
  expect(report.submission_manifest.items[0].redaction_status).toBe("redacted");
  await page.goto(`/reports/${reportId}?private=1&tab=audit`);
  await expect(page.getByText("Content redaction", { exact: true })).toBeVisible();
  await expect(page.getByText("redacted", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(secret);
  await page.screenshot({ path: "/private/tmp/story-12-1-content-redaction.png", fullPage: true });
});

test("protects a credential from a failed artifact when a sibling echoes it", async ({ page, request }) => {
  const projectKey = `failed-content-security-${Date.now()}`;
  const project = await request.post("/api/v1/projects", {
    data: { project_key: projectKey, display_name: "Failed input boundary audit" },
  });
  expect(project.ok()).toBeTruthy();
  const secret = "synthetic-failed-upload-credential";
  const boundary = `----boundary-${Date.now()}`;
  const payload = [
    `--${boundary}\r\nContent-Disposition: form-data; name="project_key"\r\n\r\n${projectKey}\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="broken.tf"\r\nContent-Type: text/plain\r\n\r\npassword="${secret}"\nresource "aws_instance" "broken" {\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="playbook.yaml"\r\nContent-Type: application/x-yaml\r\n\r\nhosts: all\ntasks:\n  - name: Review ${secret}\n    debug:\n      msg: safe\n\r\n`,
    `--${boundary}--\r\n`,
  ].join("");
  const run = await request.post("/api/v1/analyses", {
    headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` },
    data: Buffer.from(payload),
  });
  expect(run.ok()).toBeTruthy();
  const data = (await run.json()).data;
  expect(JSON.stringify(data)).not.toContain(secret);
  const reportId = data.persisted_report.id;
  const detail = await request.get(`/api/v1/analyses/${reportId}`);
  expect(detail.ok()).toBeTruthy();
  const report = (await detail.json()).data;
  expect(JSON.stringify(report)).not.toContain(secret);
  expect(report.submission_manifest.items.find((item: { name: string }) => item.name === "broken.tf")).toMatchObject({
    status: "failed", redaction_status: "redacted",
  });
  await page.goto(`/reports/${reportId}?private=1&tab=audit`);
  await expect(page.getByText("Content redaction", { exact: true })).toBeVisible();
  await expect(page.getByText("redacted", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(secret);
});

test("screens public intake and audit metadata for excluded credentials", async ({ page, request }) => {
  const projectKey = `intake-security-${Date.now()}`;
  const project = await request.post("/api/v1/projects", {
    data: { project_key: projectKey, display_name: "Public intake boundary audit" },
  });
  expect(project.ok()).toBeTruthy();
  const actorSecret = "synthetic-excluded-actor-value";
  const filenameSecret = "synthetic-intake-filename-value";
  const boundary = `----intake-boundary-${Date.now()}`;
  const parts = [
    `--${boundary}\r\nContent-Disposition: form-data; name="project_key"\r\n\r\n${projectKey}\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename=".env"\r\nContent-Type: text/plain\r\n\r\nPASSWORD=${actorSecret}\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="password=${filenameSecret}.tf"\r\nContent-Type: text/plain\r\n\r\nresource "aws_instance" "web" {}\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="playbook.yaml"\r\nContent-Type: application/x-yaml\r\n\r\nhosts: all\ntasks:\n  - name: Review deployment\n    debug:\n      msg: safe\n\r\n`,
    `--${boundary}--\r\n`,
  ];
  const run = await request.post("/api/v1/analyses", {
    headers: { "Content-Type": `multipart/form-data; boundary=${boundary}`, "X-DeployWhisper-Actor": actorSecret },
    data: Buffer.from(parts.join("")),
  });
  expect(run.ok()).toBeTruthy();
  const data = (await run.json()).data;
  expect(JSON.stringify(data)).not.toContain(actorSecret);
  expect(JSON.stringify(data)).not.toContain(filenameSecret);
  expect(data.intake.items[1].status).toBe("sensitive");
  const reportId = data.persisted_report.id;
  const detail = await request.get(`/api/v1/analyses/${reportId}`);
  expect(detail.ok()).toBeTruthy();
  const report = (await detail.json()).data;
  expect(JSON.stringify(report)).not.toContain(actorSecret);
  expect(JSON.stringify(report)).not.toContain(filenameSecret);
  await page.goto(`/reports/${reportId}?private=1&tab=audit`);
  await expect(page.getByText("Content redaction", { exact: true })).toBeVisible();
  await expect(page.getByText("sensitive_blocked", { exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(actorSecret);
  await expect(page.locator("body")).not.toContainText(filenameSecret);
});

test("retains accepted artifact identity when its extension is a detected value", async ({ page, request }) => {
  const projectKey = `alias-security-${Date.now()}`;
  const project = await request.post("/api/v1/projects", {
    data: { project_key: projectKey, display_name: "Artifact alias boundary audit" },
  });
  expect(project.ok()).toBeTruthy();
  const boundary = `----alias-boundary-${Date.now()}`;
  const body = [
    `--${boundary}\r\nContent-Disposition: form-data; name="project_key"\r\n\r\n${projectKey}\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename=".env"\r\nContent-Type: text/plain\r\n\r\nPASSWORD=yaml\r\n`,
    `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="playbook.yaml"\r\nContent-Type: application/x-yaml\r\n\r\nhosts: all\ntasks:\n  - name: Review deployment\n    debug:\n      msg: safe\n\r\n`,
    `--${boundary}--\r\n`,
  ].join("");
  const run = await request.post("/api/v1/analyses", {
    headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` },
    data: Buffer.from(body),
  });
  expect(run.ok()).toBeTruthy();
  const data = (await run.json()).data;
  const accepted = data.persisted_report.submission_manifest.items[1];
  expect(accepted.status).toBe("accepted");
  expect(accepted.parse_status).toBe("parsed");
  expect(data.intake.items[1]).toMatchObject({ name: accepted.name, status: "ready", tool: "ansible" });
  expect(data.parse_batch.files[0].file_name).toBe(accepted.name);
  expect(accepted.name).not.toContain("[REDACTED]");
  const reportId = data.persisted_report.id;
  const detail = await request.get(`/api/v1/analyses/${reportId}`);
  expect(detail.ok()).toBeTruthy();
  expect((await detail.json()).data.submission_manifest.items[1].name).toBe(accepted.name);
  await page.goto(`/reports/${reportId}?private=1&tab=audit`);
  await expect(page.getByText("Content redaction", { exact: true })).toBeVisible();
  await expect(page.getByText("sensitive_blocked", { exact: true })).toBeVisible();
});
