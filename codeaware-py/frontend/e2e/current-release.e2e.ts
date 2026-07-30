import { expect, test, type Page } from "@playwright/test";

const projectPath = process.env.CODEAWARE_E2E_PROJECT_PATH;

async function openDomain(page: Page, label: string) {
  await page.goto("/");
  await expect(page.getByText("API · ONLINE")).toBeVisible();
  await page.getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

test.describe.serial("C2 current-release seven-domain browser closure", () => {
  test("Code Review: structured result and visible stable failure", async ({ page }) => {
    await openDomain(page, "Code Review");
    await page.getByRole("button", { name: "开始评审" }).click();
    await expect(page.getByText("浏览器评审完成")).toBeVisible();
    await expect(page.getByText("CRITICAL 1")).toBeVisible();
    await expect(page.getByText("字符串拼接 SQL")).toBeVisible();

    await page.getByLabel("源代码").fill("BROWSER_INVALID_OUTPUT");
    await page.getByRole("button", { name: "开始评审" }).click();
    await expect(page.getByText("CODE_REVIEW_OUTPUT_INVALID")).toBeVisible();
  });

  test("Unit Test: generated JUnit5 code without execution claim", async ({ page }) => {
    await openDomain(page, "Unit Test");
    await expect(
      page.getByText("当前仅支持 JUnit5；只生成并保存测试代码，不会在项目中执行。"),
    ).toBeVisible();
    await page.getByRole("button", { name: "生成单测" }).click();
    await expect(page.getByText("JUnit5", { exact: true })).toBeVisible();
    await expect(page.getByText(/class CalcTest/)).toBeVisible();
    await expect(page.getByText(/addsNumbers/)).toBeVisible();
  });

  test("AIReadMe: allowlisted snapshot metadata is visible", async ({ page }) => {
    if (!projectPath) throw new Error("CODEAWARE_E2E_PROJECT_PATH is required");
    await openDomain(page, "AI ReadMe");
    await expect(page.getByText("本地项目快照能力可用")).toBeVisible();
    await page.getByLabel("项目名").fill("browser-readme");
    await page.getByLabel("项目路径").fill(projectPath);
    await page.getByRole("button", { name: "生成文档" }).click();
    await expect(page.getByText("v1", { exact: true })).toBeVisible();
    await expect(page.getByText("Browser Fixture", { exact: true })).toBeVisible();
    await expect(page.getByText("3", { exact: true })).toBeVisible();
    await expect(page.getByText("否", { exact: true })).toBeVisible();
  });

  test("Chat: typed stream persists and reloads by real cid", async ({ page }) => {
    await openDomain(page, "Chat");
    const editor = page.getByPlaceholder("输入消息，Enter 发送，Shift+Enter 换行");
    await editor.fill("browser chat persistence");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText(/Browser reply\s+line/)).toBeVisible();
    await expect(
      page.locator("p").filter({ hasText: "browser chat persistence" }),
    ).toBeVisible();

    await page.reload();
    await expect(page.getByText("API · ONLINE")).toBeVisible();
    await page.getByText("browser chat persistence", { exact: true }).click();
    await expect(page.getByText(/Browser reply\s+line/)).toBeVisible();
    await expect(
      page.locator("p").filter({ hasText: "browser chat persistence" }),
    ).toBeVisible();
  });

  test("Knowledge: text/file upload, hybrid search, and delete", async ({ page }) => {
    await openDomain(page, "Knowledge");
    await page.locator('input[type="file"]').setInputFiles({
      name: "browser.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Browser file\n\nbrowser file knowledge"),
    });
    await expect(page.getByText("已上传 browser.md")).toBeVisible();

    await page.getByLabel("标题").fill("Browser caching");
    await page.getByLabel("文档内容").fill(
      "# browser caching\n\nBrowser caching uses a bloom filter.",
    );
    await page.getByRole("button", { name: "上传文本" }).click();
    await expect(page.getByText("已上传", { exact: true })).toBeVisible();

    await page.getByPlaceholder(/检索知识库/).fill("browser caching");
    await page.getByRole("button", { name: "检索", exact: true }).click();
    await expect(page.getByText("Browser caching uses a bloom filter.")).toBeVisible();
    await expect(page.getByText("both", { exact: true }).first()).toBeVisible();

    const resultCard = page
      .locator("div.bg-panel")
      .filter({ hasText: "Browser caching uses a bloom filter." })
      .first();
    await resultCard.getByTitle("删除该文档").click();
    await expect(page.getByText("Browser caching uses a bloom filter.")).toHaveCount(0);
  });

  test("Memory: REFERENCE save, semantic recall, and delete", async ({ page }) => {
    await openDomain(page, "Memory");
    await expect(page.getByText(/手动录入固定为 REFERENCE/)).toBeVisible();
    await page.getByLabel("内容").fill("browser memory uses SQLAlchemy async");
    await page.getByRole("button", { name: "录入记忆" }).click();

    await page.getByPlaceholder(/自然语言查询/).fill("browser memory uses SQLAlchemy async");
    await page.getByRole("button", { name: "召回", exact: true }).click();
    await expect(page.getByText("browser memory uses SQLAlchemy async")).toBeVisible();
    await expect(page.getByText("REFERENCE", { exact: true }).first()).toBeVisible();

    const memoryCard = page
      .locator("div.bg-panel")
      .filter({ hasText: "browser memory uses SQLAlchemy async" })
      .first();
    await memoryCard.getByTitle("删除记忆").click();
    await expect(page.getByText("browser memory uses SQLAlchemy async")).toHaveCount(0);
  });

  test("Prompt: create v2, preview, and rollback to v1", async ({ page }) => {
    await openDomain(page, "Prompt");
    await page.getByLabel("新建 Prompt 版本").click();
    await page.locator("select").selectOption("CODE_REVIEW");
    await page.getByLabel("版本名称").fill("Browser Prompt v2");
    await page.getByRole("button", { name: "创建并激活" }).click();

    await expect(page.getByText("Browser Prompt v2", { exact: true })).toBeVisible();
    await expect(page.getByText("v2", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/public class Example/)).toBeVisible();

    const original = page.getByRole("button", {
      name: /Java Code Review 专家模板 v2/,
    });
    await original.click();
    await page.getByRole("button", { name: "激活此版本" }).click();
    await expect(original).toContainText("ACTIVE");
    await expect(page.getByRole("button", { name: "激活此版本" })).toHaveCount(0);
  });
});
