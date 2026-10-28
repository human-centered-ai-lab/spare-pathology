import path from "node:path";
import { defineConfig } from "@playwright/test";

const root = path.resolve(__dirname, "../..");
const xopatDir = process.env.XOPAT_DIR ?? path.join(root, "vendor/xopat");

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5099",
    headless: true,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "python tests/e2e/run_e2e_server.py",
      port: 5099,
      reuseExistingServer: false,
      cwd: root,
      env: { XOPAT_DIR: xopatDir },
      timeout: 30_000,
    },
    {
      command: "node index.js",
      url: "http://127.0.0.1:9010",
      reuseExistingServer: !process.env.CI,
      cwd: xopatDir,
      env: {
        XOPAT_ENV: path.join(root, "config/xopat-env.json"),
        XOPAT_NODE_PORT: "9010",
        XOPAT_NODE_HOST: "127.0.0.1",
      },
      timeout: 30_000,
    },
  ],
});
