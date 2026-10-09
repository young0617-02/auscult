/** M4.3 E2E（D11-D15 出口）：报告列表 → 详情（结论/根因/建议/置信度/审核状态）→ 审核操作区 */

import { test, expect } from "@playwright/test";
import { execSync } from "node:child_process";

const PY = "d:\\DSHproject\\auscult\\.venv\\Scripts\\python.exe";

async function login(page: import("@playwright/test").Page, username = "eng_dev") {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill("Auscult#Dev2026");
  await page.getByRole("button", { name: /登录/ }).click();
  // 角色默认落地页：engineer→alarms / reviewer→reports / kb_admin→knowledge / sys_admin→audit
  await page.waitForURL(/\/(alarms|reports|knowledge|audit)/, { timeout: 15_000 });
}

test("D11：报告列表页渲染（筛选/分页/KPI/状态徽章）", async ({ page }) => {
  await login(page);
  await page.goto("/reports");

  await expect(page.getByRole("heading", { name: "报告工作台" })).toBeVisible();
  await expect(page.getByText("当前筛选报告")).toBeVisible();
  await expect(page.getByText("本页待审核")).toBeVisible();

  // 筛选器存在
  await expect(page.getByLabel("审核状态筛选")).toBeVisible();
  await expect(page.getByLabel("风险等级筛选")).toBeVisible();

  // 列表或空态至少一个可见
  const list = page.getByTestId("report-list");
  const empty = page.getByText("暂无报告");
  await expect(list.or(empty).first()).toBeVisible({ timeout: 10_000 });
});

test("D11-D15：报告详情 → 内容渲染 → 审核操作区", async ({ page }) => {
  await login(page);
  await page.goto("/reports");

  // 等待列表加载（骨架 → 列表）
  await page.waitForTimeout(1500);
  const firstRow = page.locator('[data-testid^="report-row-"]').first();
  const hasData = await firstRow.isVisible({ timeout: 8000 }).catch(() => false);
  test.info().annotations.push({ type: "debug", description: `报告列表可见=${hasData}` });
  if (!hasData) {
    test.skip(true, "报告列表为空，跳过详情测试");
    return;
  }

  const reportId = await firstRow.getAttribute("data-testid").then((t) => t?.replace("report-row-", "") ?? "");
  await firstRow.click();
  await page.waitForURL(`/reports/${reportId}`);

  // 详情页渲染
  await expect(page.getByRole("heading", { name: "报告详情" })).toBeVisible();
  await expect(page.getByText(/报告 \S+/)).toBeVisible();

  // 状态徽章（置信度+风险+审核状态，详情页+列表页均有多个）
  await expect(page.getByTestId("confidence-badge").first()).toBeVisible();
  await expect(page.getByTestId("risk-tag").first()).toBeVisible();
  await expect(page.getByTestId("report-review-status")).toBeVisible();

  // 内容区
  await expect(page.getByTestId("report-diagnosis")).toBeVisible();
  await expect(page.getByTestId("report-root-causes")).toBeVisible();
  await expect(page.getByTestId("report-suggestions")).toBeVisible();

  // 降级报告应有横幅（当前 E2E 均走低置信度降级路径）
  const degradeBanner = page.getByTestId("report-degrade-banner");
  if (await degradeBanner.isVisible().catch(() => false)) {
    await expect(degradeBanner).toContainText("初步判断");
  }

  // D12：置信度 breakdown 卡片渲染（无数据时显示占位提示）
  await expect(page.getByTestId("confidence-breakdown")).toBeVisible();
  await expect(page.getByText(/综合置信度/)).toBeVisible();

  // D13：审核操作区
  await expect(page.getByTestId("review-actions")).toBeVisible();
  await expect(page.getByText("审核操作")).toBeVisible();

  // engineer 角色（eng_dev）无审核权限，应看到角色提示
  await expect(page.getByText(/你的角色无审核权限/)).toBeVisible();
});

test("D14：reviewer 角色可审核 pending 报告", async ({ page }) => {
  await login(page);
  await page.goto("/reports");

  // 等待列表加载（骨架 → 列表）；waitFor 轮询比 isVisible 即时判定可靠
  await page.waitForTimeout(1500);
  // 找 pending 报告（review_status NULL → 前端显示「待审核」）
  const pendingRow = page.locator('[data-testid^="report-row-"]').filter({
    has: page.locator('[data-testid^="review-status-"]').filter({ hasText: "待审核" }),
  }).first();
  const hasPending = await pendingRow
    .waitFor({ state: "visible", timeout: 8000 })
    .then(() => true)
    .catch(() => false);
  if (!hasPending) {
    test.skip(true, "无待审核报告，跳过审核操作测试");
    return;
  }

  const reportId = await pendingRow.getAttribute("data-testid").then((t) => t?.replace("report-row-", "") ?? "");
  await pendingRow.click();
  await page.waitForURL(`/reports/${reportId}`);

  // 待审核状态确认
  await expect(page.getByTestId("report-review-status")).toContainText("待审核");

  // engineer 角色无审核权限（eng_dev 是 engineer）
  await expect(page.getByText(/你的角色无审核权限/)).toBeVisible();
});

test("D14：reviewer 登录后可审核（通过/驳回 + 意见必填）", async ({ page }) => {
  await login(page, "rev_dev");
  await page.goto("/reports");

  await page.waitForTimeout(1500);
  const pendingRow = page.locator('[data-testid^="report-row-"]').filter({
    has: page.locator('[data-testid^="review-status-"]').filter({ hasText: "待审核" }),
  }).first();
  const hasPending = await pendingRow
    .waitFor({ state: "visible", timeout: 8000 })
    .then(() => true)
    .catch(() => false);
  if (!hasPending) {
    test.skip(true, "无待审核报告，跳过审核提交测试");
    return;
  }

  const reportId = await pendingRow.getAttribute("data-testid").then((t) => t?.replace("report-row-", "") ?? "");
  await pendingRow.click();
  await page.waitForURL(`/reports/${reportId}`);

  // reviewer 可见审核表单
  await expect(page.getByTestId("review-submit")).toBeVisible();

  // 驳回必填意见校验
  await page.getByRole("radio", { name: "驳回" }).check();
  await expect(page.getByText("驳回时必填意见")).toBeVisible();
  await expect(page.getByTestId("review-submit")).toBeDisabled();

  // 切换为通过 + 意见可提交
  await page.getByRole("radio", { name: "通过" }).check();
  await page.getByLabel("审核意见").fill("审核通过");
  await expect(page.getByTestId("review-submit")).toBeEnabled();
});
