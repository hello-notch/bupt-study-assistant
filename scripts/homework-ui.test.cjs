const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("../client/node_modules/playwright");

async function main() {
  const root = path.resolve(__dirname, "../web/dist");
  const output = path.resolve(__dirname, "../.test-tmp/homework-ui");
  await fs.mkdir(output, { recursive: true });
  const server = http.createServer(async (request, response) => {
    const file = path.resolve(root, `.${new URL(request.url, "http://localhost").pathname.replace(/\/$/, "/index.html")}`);
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    try {
      response.setHeader("Content-Type", { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".webp": "image/webp" }[path.extname(file)] || "application/octet-stream");
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
      const accountKey = "a".repeat(64);
      const dueAt = "2099-09-25T12:00:00.000Z";
      const item = (id, course) => ({ sourceId: id, courseId: course, course, title: `[作业][${course}]练习一`,
        dueAt, contentHtml: '<p>完成第 1、2 题。</p><p><strong>写出推导过程。</strong></p><img src="x" onerror="window.injected=true"><script>window.injected=true</script>',
        url: `https://ucloud.bupt.edu.cn/uclass/course.html#/student/assignmentDetails_fullpage?assignmentId=${id}`,
      });
      window.homeworkFixture = { items: [item("one", "现代控制理论"), item("two", "系统工程")], complete: true, accountKey, updatedAt: now };
      if (sessionStorage.getItem("homework-empty")) window.homeworkFixture.items = [];
      window.homeworkFail = false;
      localStorage.setItem("youxueban-state-v9", JSON.stringify({
        profileName: "回归测试", preferences: { reduceMotion: true, browserNotifications: false, soundNotifications: false },
        tasks: [{ id: 1, title: "个人任务", course: "计划", dueAt: "2099-12-25T12:00:00.000Z", status: "todo", reminderMinutes: 60, createdAt: now }],
        courses: [
          { id: 1, name: "现代控制理论", weekday: 1, startSection: 3, endSection: 4, weeks: "1", color: "blue" },
          { id: 2, name: "系统工程", weekday: 5, startSection: 10, endSection: 11, weeks: "1", color: "green" },
          { id: 3, name: "周末课程", weekday: 7, startSection: 13, endSection: 14, weeks: "2", color: "rose" },
        ].map(course => ({ ...course, location: "教学实验综合楼-N308", teacher: "测试教师", startTime: "09:50", endTime: "11:25", reminderMinutes: 0 })),
      }));
      window.youxuebanRuntime = {
        notify: async () => true,
        request: async route => {
          if (route === "/api/homework/sync") return window.homeworkFail
            ? { status: 502, body: { error: "测试网络异常，已保留现有作业" } }
            : { status: 200, body: JSON.parse(JSON.stringify(window.homeworkFixture)) };
          return { status: 200, body: route === "/api/local/settings/status"
            ? { campus: { configured: true, accountKey }, ai: { configured: false } }
            : { items: [], statuses: [], errors: [] } };
        },
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/#/courses`);
    await page.locator(".schedule-grid").waitFor();
    const nav = page.getByRole("navigation", { name: "移动端主导航" });
    async function week(number) {
      const input = page.getByRole("textbox", { name: "查看第几周课程" });
      await input.fill(String(number));
      await input.press("Enter");
    }
    async function bounds() {
      const result = await page.evaluate(() => {
        const box = document.querySelector(".schedule-grid").getBoundingClientRect();
        const navBox = document.querySelector(".mobile-nav").getBoundingClientRect();
        return { right: box.right, bottom: box.bottom, navTop: navBox.top, width: innerWidth,
          height: innerHeight, scrollHeight: document.documentElement.scrollHeight, scrollWidth: document.documentElement.scrollWidth };
      });
      assert.ok(result.right <= result.width);
      assert.ok(result.scrollWidth <= result.width);
      assert.ok(result.bottom <= result.navTop, JSON.stringify(result));
      assert.ok(result.scrollHeight <= result.height + 1, JSON.stringify(result));
    }
    for (const [width, height] of [[320, 640], [390, 844], [720, 900]]) {
      await page.setViewportSize({ width, height });
      await week(1);
      assert.equal(await page.locator(".day-header:visible").count(), 5);
      assert.equal(await page.locator(".section-label:visible").count(), 11);
      const rowHeights = await page.locator(".section-label:visible").evaluateAll(elements => elements.map(el => el.getBoundingClientRect().height));
      assert.ok(rowHeights[0] < rowHeights[2]);
      await bounds();
      await page.screenshot({ path: path.join(output, `weekdays-${width}.png`) });
      await week(2);
      assert.equal(await page.locator(".day-header:visible").count(), 7);
      assert.equal(await page.locator(".section-label:visible").count(), 14);
      await bounds();
      await page.screenshot({ path: path.join(output, `weekend-${width}.png`) });
      await week(22);
      assert.equal(await page.locator(".course-cell").count(), 0);
      assert.equal(await page.locator(".section-label:visible").count(), 14);
      assert.equal(await page.locator(".section-label.empty-section:visible").count(), 0);
      await bounds();
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await week(1);
    await page.locator(".course-cell").first().click();
    await page.getByRole("button", { name: "查看作业", exact: true }).click();
    await page.locator(".homework-course-filter").waitFor();
    assert.equal(await page.locator(".homework-row").count(), 1);
    assert.ok((await page.locator(".homework-row").innerText()).includes("现代控制理论"));
    await page.getByRole("button", { name: "清除课程筛选" }).click();
    assert.equal(await page.locator(".task-row").count(), 3);
    assert.ok((await page.locator(".task-row").first().innerText()).includes("个人任务"));
    assert.equal(await page.locator(".homework-row").getByRole("button", { name: "删除任务", exact: true }).count(), 0);
    assert.equal(await page.locator(".homework-row").getByRole("button", { name: "编辑任务", exact: true }).count(), 0);
    assert.ok(await page.locator(".homework-row .task-check").first().isDisabled());
    await page.locator(".homework-title").first().click();
    await page.getByRole("dialog").waitFor();
    assert.ok((await page.locator(".homework-content").innerText()).includes("写出推导过程"));
    assert.equal(await page.locator(".homework-content script, .homework-content [onerror]").count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.injected)), false);
    await page.screenshot({ path: path.join(output, "homework-detail.png") });
    await page.getByRole("button", { name: "关闭作业详情" }).click();
    async function sync() {
      await page.getByRole("button", { name: "同步作业", exact: true }).click();
      await page.getByRole("button", { name: "同步作业", exact: true }).waitFor();
    }
    await page.evaluate(() => { window.homeworkFail = true; });
    await sync();
    assert.equal(await page.locator(".homework-row").count(), 2);
    assert.equal(await page.locator(".homework-row .task-due").getByText("已提交", { exact: true }).count(), 0);
    await page.evaluate(() => { window.homeworkFail = false; window.homeworkFixture.items = []; sessionStorage.setItem("homework-empty", "1"); });
    await sync();
    await page.getByRole("button", { name: "已提交 2", exact: true }).click();
    assert.equal(await page.locator(".homework-row").count(), 2);
    await page.locator(".homework-row").first().getByRole("button", { name: "删除任务", exact: true }).click();
    await page.locator(".homework-row").first().getByRole("button", { name: "确认删除任务", exact: true }).click();
    assert.equal(await page.locator(".homework-row").count(), 1);
    await sync();
    assert.equal(await page.locator(".homework-row").count(), 1);
    await page.screenshot({ path: path.join(output, "submitted.png") });
    await page.reload();
    await page.getByRole("button", { name: "已提交 1", exact: true }).waitFor();
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("youxueban-state-v10")).tasks.filter(task => task.homework).length), 1);
    await nav.getByRole("button", { name: "课程", exact: true }).click();
    await week(1);
    await page.setViewportSize({ width: 1280, height: 900 });
    assert.equal(await page.locator(".day-header:visible").count(), 7);
    assert.equal(await page.locator(".section-label:visible").count(), 14);
    assert.deepEqual(errors, []);
    console.log("PASS: compact weekdays/weekends/empty weeks at 320/390/720px; desktop unchanged; course filter; homework detail/XSS; system-only status; fail-retention; submitted deletion; migration.");
  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
