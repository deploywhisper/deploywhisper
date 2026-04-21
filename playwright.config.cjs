const { devices } = require("@playwright/test");
const { screenReaderConfig } = require("@guidepup/playwright");

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
    baseURL: "http://127.0.0.1:8080",
    headless: false,
    trace: "retain-on-failure",
  },
  webServer: {
    command: "./.venv/bin/python tests/e2e/seeded_server.py",
    url: "http://127.0.0.1:8080/",
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
