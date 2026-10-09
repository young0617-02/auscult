/** M4.1 E2E（D3/D4/D5 出口）：登录 → 用户菜单（Radix 真实输入管线）→ 告警看板 alarm:new 实时插入 */

import { test, expect } from "@playwright/test";
import { execSync } from "node:child_process";

const PY = "d:\\DSHproject\\auscult\\.venv\\Scripts\\python.exe";
const INSERT_SCRIPT = "d:\\DSHproject\\auscult\\scripts\\insert_test_alarm.py";

async function login(page: import("@playwright/test").Page, username = "eng_dev") {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill("Auscult#Dev2026");
  await page.getByRole("button", { name: /登录/ }).click();
  await page.waitForURL("**/alarms", { timeout: 15_000 });
}

test("D3：登录成功跳转 /alarms，用户菜单可打开并可退出", async ({ page }) => {
  await login(page);

  // Radix DropdownMenu（真实 pointerdown 管线）
  const trigger = page.getByTestId("user-menu");
  await expect(trigger).toBeVisible();
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true", { timeout: 3000 });
  await expect(page.getByRole("menuitem", { name: /退出登录/ })).toBeVisible();

  // 退出登录 → 回 /login（AuthGate 会带 next 参数，断言放宽到路径级）
  await page.getByRole("menuitem", { name: /退出登录/ }).click();
  await page.waitForURL(/\/login/, { timeout: 5000 });
});

test("D5：登录后 Socket 连接建立（无断线横幅）", async ({ page }) => {
  await login(page);
  await page.waitForTimeout(1500);
  await expect(page.getByRole("status")).toHaveCount(0); // ConnectionBanner 不渲染 = connected
});

test("D5：PG 插入告警 → alarm:new 实时插入看板 + 铃铛未读徽标", async ({ page }) => {
  await login(page);

  // 等待看板初始数据加载完成（Skeleton 消失）
  await page.waitForTimeout(1200);

  // 真实链路：后端 2s 轮询桥接 PG → socket 广播 alarm:new → 前端定向插入
  const out = execSync(`"${PY}" "${INSERT_SCRIPT}" --severity critical`, {
    encoding: "utf-8",
    timeout: 15_000,
    cwd: "d:\\DSHproject\\auscult", // sys.path 需项目根才能 import app.api.db
  });
  const metric = out.match(/metric=(\S+)/)?.[1] ?? "";
  expect(metric).toContain("e2e_test_");

  // 新告警应 ≤5s 内出现在看板第一页（含轮询桥接 2s 余量）
  await expect(page.getByText(metric).first()).toBeVisible({ timeout: 8000 });

  // 铃铛未读徽标出现
  await expect(page.getByTestId("unread-badge")).toBeVisible();
});
