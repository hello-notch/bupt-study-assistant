const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("../client/node_modules/playwright");

// Isolated UI fixtures: no personal storage, credentials, or upstream requests.
async function main() {
  const root = path.resolve(__dirname, "../web/dist");
  const output = path.resolve(__dirname, "../.test-tmp/mobile-ui");
  await fs.mkdir(output, { recursive: true });
  const server = http.createServer(async (request, response) => {
    const file = path.resolve(root, `.${new URL(request.url, "http://localhost").pathname.replace(/\/$/, "/index.html")}`);
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    try {
      const mime = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".webp": "image/webp" };
      response.setHeader("Content-Type", mime[path.extname(file)] || "application/octet-stream");
      response.end(await fs.readFile(file));
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    await context.addInitScript(() => {
      const now = new Date().toISOString();
      localStorage.setItem("youxueban-state-v9", JSON.stringify({
        profileName: "界面回归", preferences: { reduceMotion: true, soundNotifications: false, browserNotifications: false },
        courses: ["工程管理概论", "传感器与检测技术基础", "模式识别与机器学习", "系统工程", "太极拳", "数字图像处理", "现代控制理论"].map((name, i) => ({
          id: i + 1, name, location: "教学实验综合楼-N308", teacher: "测试教师", weekday: i + 1,
          startSection: 3, endSection: 4, startTime: "09:50", endTime: "11:25",
          weeks: "1-22", reminderMinutes: 0, color: ["blue", "cyan", "violet", "orange", "rose", "green", "teal"][i],
        })),
        assistantConversations: [{ id: "long", title: "长对话测试", createdAt: now, updatedAt: now,
          thinkingEnabled: false, messages: Array.from({ length: 80 }, (_, i) => ({
            id: i + 1, role: i % 2 ? "assistant" : "user", content: "这是一段用于检验长对话滚动和布局的测试内容。".repeat(20), createdAt: now,
          })) }], activeConversationId: "long",
      }));
      window.youxuebanRuntime = {
        notify: async () => true,
        request: async route => ({ status: 200, body: route === "/api/local/settings/status"
          ? { campus: { configured: true }, ai: { configured: true, model: "deepseek-chat" } }
          : route === "/api/config" ? { assistant: { model: "deepseek-chat", contextWindow: 128000, thinkingSupported: true } }
          : route === "/api/assistant/models" ? { models: ["deepseek-chat"] }
          : { items: [], statuses: [], errors: [] } }),
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/#/courses`);
    await page.locator(".course-cell").first().waitFor();
    const nav = page.getByRole("navigation", { name: "移动端主导航" });
    assert.equal(await nav.getByRole("button").count(), 8);
    assert.equal(await page.getByText("更多", { exact: true }).count(), 0);
    async function go(label) {
      await nav.getByRole("button", { name: label, exact: true }).click();
    }
    async function noOverflow() {
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth));
    }
    for (const width of [320, 390, 720]) {
      await page.setViewportSize({ width, height: 844 });
      await noOverflow();
      assert.equal(await page.locator(".day-header").count(), 7);
      assert.equal(await page.locator(".course-cell").first().evaluate(el => getComputedStyle(el).gridRowEnd), "span 2");
      assert.ok(await nav.evaluate(el => Array.from(el.querySelectorAll("button")).every(button => button.scrollWidth <= button.clientWidth)));
      await page.screenshot({ path: path.join(output, `courses-${width}.png`) });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await go("设置");
    await page.getByRole("button", { name: "保存资料", exact: true }).scrollIntoViewIfNeeded();
    assert.ok(await page.locator(".profile-editor").evaluate(el => {
      const button = el.querySelector(":scope > button").getBoundingClientRect();
      return Math.abs(button.right - el.getBoundingClientRect().right) < 2;
    }));
    assert.ok(!(await page.locator(".notification-settings").innerText()).includes("Windows"));
    await page.getByLabel("昵称", { exact: true }).fill("保存验证");
    await page.getByRole("button", { name: "保存资料", exact: true }).click();
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("youxueban-state-v9")).profileName), "保存验证");
    await page.screenshot({ path: path.join(output, "settings.png") });
    assert.ok(await page.locator(".danger-zone > .danger-button").evaluateAll(buttons =>
      buttons.every(button => getComputedStyle(button).justifySelf === "end")));
    await go("校园");
    const refresh = page.getByRole("button", { name: "刷新", exact: true });
    const border = await refresh.evaluate(el => getComputedStyle(el).borderColor);
    await page.getByRole("button", { name: "第二课堂", exact: true }).tap();
    assert.equal(await refresh.evaluate(el => getComputedStyle(el).borderColor), border);
    await page.getByRole("button", { name: "信息门户", exact: true }).tap();
    assert.equal(await refresh.evaluate(el => getComputedStyle(el).borderColor), border);
    await go("助手");
    const prompts = page.locator(".quick-prompts");
    const promptBox = await prompts.boundingBox();
    assert.ok(promptBox.height >= 34);
    assert.ok(await page.locator(".chat-panel").evaluate(el => el.scrollHeight > el.clientHeight && el.clientHeight > 0));
    await page.locator(".chat-panel").evaluate(el => { el.scrollTop = 0; });
    assert.equal((await prompts.boundingBox()).height, promptBox.height);
    await noOverflow();
    await page.screenshot({ path: path.join(output, "assistant-long.png") });
    async function swipe(selector, dx, dy = 0, multi = false) {
      await page.locator(selector).evaluate((el, { dx, dy, multi }) => {
        const touch = (x, y, id = 1) => new Touch({ identifier: id, target: el, clientX: x, clientY: y });
        el.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, touches: [touch(250, 250)] }));
        el.dispatchEvent(new TouchEvent("touchmove", { bubbles: true, touches: multi ? [touch(250 + dx, 250 + dy), touch(200, 250, 2)] : [touch(250 + dx, 250 + dy)] }));
        el.dispatchEvent(new TouchEvent("touchend", { bubbles: true, touches: [], changedTouches: [touch(250 + dx, 250 + dy)] }));
      }, { dx, dy, multi });
      await page.waitForTimeout(100);
    }
    await swipe(".quick-prompts", -120);
    assert.ok(page.url().endsWith("/assistant"));
    await swipe(".assistant-composer textarea", -120);
    assert.ok(page.url().endsWith("/assistant"));
    await swipe(".assistant-page h1", -120, 80);
    assert.ok(page.url().endsWith("/assistant"));
    await swipe(".assistant-page h1", -120, 0, true);
    assert.ok(page.url().endsWith("/assistant"));
    await swipe(".assistant-page h1", -120);
    assert.ok(page.url().endsWith("/notifications"));
    await swipe(".page-heading h1", 120);
    assert.ok(page.url().endsWith("/assistant"));
    await go("今天");
    await swipe(".today-heading h1", 120);
    assert.ok(page.url().endsWith("/today"));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.locator(".side-nav").getByRole("button", { name: "课程", exact: true }).click();
    await noOverflow();
    await page.screenshot({ path: path.join(output, "courses-desktop.png") });
    assert.deepEqual(errors, []);
    console.log("PASS: 8 navigation entries; 320/390/720px grid; profile save/alignment; system notification copy; campus tab borders; long chat; swipe guards; desktop; no page errors.");
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
