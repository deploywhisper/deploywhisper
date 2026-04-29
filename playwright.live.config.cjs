const { devices } = require("@playwright/test");

module.exports = {
  testDir: "./tests/e2e",
  timeout: 5 * 60 * 1000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8080",
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], headless: true },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"], headless: true },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"], headless: true },
    },
  ],
};
