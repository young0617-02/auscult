/**
 * M4.2 E2E（D6-D10 出口）：发起诊断 → 节点进度 → 终态（完成/待审核/失败）→ chat:ask 追问。
 * 真实链路：REST POST /api/diagnose → runner 后台图执行（TDengine/Milvus/Neo4j/Ollama）
 * → socket diagnosis:progress/done → 会话流渲染；追问走 socket chat:ask ack。
 */

import { test, expect } from "@playwright/test";
import { execSync } from "node:child_process";

const PY = "<REPO>\\.venv\\Scripts\\python.exe";
const INSERT_SCRIPT = "<REPO>\\scripts\\insert_test_alarm.py";

async function login(page: import("@playwright/test").Page, username = "eng_dev") {
  await page.goto("/login");
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码").fill("Auscult#Dev2026");
  await page.getByRole("button", { name: /登录/ }).click();
  await page.waitForURL("**/alarms", { timeout: 15_000 });
}

test("D6：未选会话时诊断控制台显示空态引导", async ({ page }) => {
  await login(page);
  await page.goto("/diagnosis");
  await expect(page.getByText("未选择诊断会话")).toBeVisible();
  await expect(page.getByText("推理轨迹")).toBeVisible();
});

test("D6-D10：发起诊断 → 实时节点进度 → 终态消息 → 追问闭环", async ({ page }) => {
  test.setTimeout(300_000); // 真实图执行含本地 7B 推理（diagnose 节点 30s 超时 + 重试/降级余量）
  await login(page);
  await page.waitForTimeout(1200); // 看板初始数据加载

  // 插入测试告警并等待看板可见
  const out = execSync(`"${PY}" "${INSERT_SCRIPT}" --severity critical --metric e2e_diag_test`, {
    encoding: "utf-8",
    timeout: 15_000,
    cwd: "<REPO>",
  });
  const alarmId = out.match(/alarm_id=(\S+)/)?.[1] ?? "";
  expect(alarmId).toContain("e2e-");

  await expect(page.getByText("e2e_diag_test").first()).toBeVisible({ timeout: 8000 });

  // D6：发起诊断 → 跳转 /diagnosis?thread=
  await page.getByTestId(`diagnose-btn-${alarmId}`).click();
  await page.waitForURL(/\/diagnosis\?thread=/, { timeout: 15_000 });

  // 会话入列 + 状态胶囊 + 进度面板渲染（内联/右栏双挂载，取可见面板）
  await expect(page.getByTestId("thread-status")).toBeVisible();
  const steps = page.locator('[data-testid="progress-steps"]').filter({ visible: true }).first();
  await expect(steps).toBeVisible();
  await expect(steps.getByText("告警解析")).toBeVisible();
  await expect(steps.getByText("诊断推理")).toBeVisible();
  await expect(page.getByTestId("thread-list").first()).toBeVisible();
  await expect(page.getByText("e2e_diag_test").first()).toBeVisible(); // 告警上下文卡

  // D7：节点进度推进（diagnosis:progress 实时驱动；轮询兜底 8s）
  await expect(steps.getByText("✓").first()).toBeVisible({ timeout: 30_000 });

  // D9：终态（完成 / 待审核 / 失败 三者其一，100s 内必达）
  const terminal = page
    .locator('[data-testid="diagnosis-done"], [data-testid="waiting-review"], [data-testid="diagnosis-error"]')
    .first();
  await expect(terminal).toBeVisible({ timeout: 100_000 });

  // 状态胶囊翻转（非 分析中）
  await expect(page.getByTestId("thread-status").getByText(/已完成|待审核|失败/)).toBeVisible({
    timeout: 10_000,
  });

  // D9：done 时应有报告入口（[id] 详情页 M4.3 实装，此处仅断言链接）
  const doneCard = page.getByTestId("diagnosis-done");
  if (await doneCard.isVisible()) {
    await expect(doneCard.getByRole("link", { name: /查看报告/ })).toBeVisible();
  }

  // D10：追问闭环（done / waiting_review 均可追问；error 跳过）
  const askable = await page
    .locator('[data-testid="diagnosis-done"], [data-testid="waiting-review"]')
    .first()
    .isVisible();
  if (askable) {
    const input = page.getByLabel("追问输入框");
    await expect(input).toBeVisible();
    await input.fill("主要的判断依据是什么？");
    await page.getByLabel("发送追问").click();

    // 乐观消息（思考中）→ QaBlock 答案渲染（含引用或明确无依据）
    await expect(page.getByText("助手思考中…")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByTestId("qa-block").first()).toBeVisible({ timeout: 60_000 });
  } else {
    test.info().annotations.push({ type: "skip-ask", description: "线程以 error 终态结束，追问不可用（符合契约）" });
  }
});
