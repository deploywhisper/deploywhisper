const { devices } = require("@playwright/test");
const { screenReaderConfig } = require("@guidepup/playwright");

const serverPort = process.env.APP_PORT || "8080";
const serverUrl = `http://127.0.0.1:${serverPort}`;

module.exports = {
  ...screenReaderConfig,
  testDir: "./tests/e2e",
  timeout: 5 * 60 * 1000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: serverUrl,
    headless: false,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "./.venv/bin/python tests/e2e/seeded_server.py",
    url: `${serverUrl}/`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"], headless: false },
    },
  ],
};
