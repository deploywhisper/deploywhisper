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
