const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("../client/node_modules/playwright");

async function main() {
  const root = path.resolve(__dirname, "../web/dist");
  const output = path.resolve(__dirname, "../.test-tmp/android-tasks-ui");
  await fs.mkdir(output, { recursive: true });
  const server = http.createServer(async (request, response) => {
    const file = path.resolve(root, `.${new URL(request.url, "http://localhost").pathname.replace(/\/$/, "/index.html")}`);
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    try {
      response.setHeader("Content-Type", { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" }[path.extname(file)] || "application/octet-stream");
      response.end(await fs.readFile(file));
    } catch { response.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, timezoneId: "Asia/Shanghai" });
    await context.addInitScript(() => {
      document.addEventListener("DOMContentLoaded", () => { document.documentElement.dataset.platform = "android"; });
      const start = new Date("2099-09-21T00:00:00+08:00");
      start.setDate(start.getDate() + ((8 - start.getDay()) % 7));
      const at = (hour, minute = 0) => { const date = new Date(start); date.setHours(hour, minute, 0, 0); return date.toISOString(); };
      const activity = (id, title, eventTime, eventEndTime) => ({
        id, title, kind: "activity", url: `https://dekt.bupt.edu.cn/activity/${id}`, source: "第二课堂", category: "活动",
        summary: "测试活动", publishedAt: at(7), eventTime, eventEndTime,
        registrationStartTime: at(6), registrationEndTime: at(7), activityStatus: ["需报名"], read: false,
      });
      window.activityFixtures = [
        activity("red", "课程直接冲突", at(8, 30), at(10)),
        activity("yellow", "课程缓冲冲突", at(9, 45), at(10, 30)),
        activity("clear", "无冲突活动", at(12), at(13)),
        activity("schedule", "日程直接冲突", at(15, 30), at(16, 30)),
      ];
      if (!localStorage.getItem("youxueban-state-v10")) localStorage.setItem("youxueban-state-v10", JSON.stringify({
        profileName: "测试用户",
        preferences: { semesterStart: "2099-09-21", reduceMotion: true, browserNotifications: true, soundNotifications: false, quietStart: "00:00", quietEnd: "00:00" },
        tasks: [{ id: 1, title: "旧版待办", course: "个人计划", dueAt: at(18), status: "todo", reminderMinutes: 10, createdAt: new Date().toISOString() }],
        courses: [{ id: 1, name: "测试课程", weekday: 1, startSection: 1, endSection: 2, weeks: "1", color: "blue", startTime: "08:00", endTime: "09:35", reminderMinutes: 20, teacher: "教师", location: "教学楼" }],
        campusItems: window.activityFixtures,
      }));
      window.nativeQueue = [];
      window.youxuebanRuntime = {
        syncReminders: items => { window.nativeQueue = items; return true; },
        requestReminderPermissions: () => {},
        notify: async () => true,
        request: async route => ({ status: 200, body: route === "/api/local/settings/status"
          ? { campus: { configured: true, accountKey: "a".repeat(64) }, ai: { configured: false } }
          : route === "/api/homework/sync" ? { items: [], complete: true, accountKey: "a".repeat(64), updatedAt: new Date().toISOString() }
          : { items: window.activityFixtures, statuses: [{ source: "activity", mode: "online", itemCount: 4 }], errors: [] } }),
      };
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const base = `http://127.0.0.1:${server.address().port}`;
    await page.goto(`${base}/#/tasks`);
    const nav = page.getByRole("navigation", { name: "移动端主导航" });
    await page.locator(".android-task-kinds").getByRole("button", { name: "待办", exact: true }).click();
    assert.equal(await page.locator(".task-row").count(), 1);
    assert.equal(await page.locator(".task-due").getByText(/开始/).count(), 0);
    await page.getByRole("button", { name: "添加任务", exact: true }).click();
    let dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "日程", exact: true }).click();
    await dialog.getByLabel("任务内容").fill("下午日程");
    const date = await page.evaluate(() => window.activityFixtures[3].eventTime.slice(0, 10));
    await dialog.getByLabel("开始时间").fill(`${date}T15:00`);
    await dialog.getByLabel("结束时间").fill(`${date}T14:00`);
    await dialog.getByRole("button", { name: "添加任务", exact: true }).click();
    assert.equal(await dialog.count(), 1);
    await dialog.getByLabel("结束时间").fill(`${date}T16:00`);
    await dialog.getByRole("button", { name: "添加任务", exact: true }).click();
    await page.locator(".android-task-kinds").getByRole("button", { name: "日程", exact: true }).click();
    assert.equal(await page.locator(".task-row").count(), 1);
    const scheduleQueue = await page.evaluate(() => window.nativeQueue.find(item => item.title === "日程开始提醒"));
    assert.equal(scheduleQueue.at, Date.parse(`${date}T14:00:00+08:00`));
    await page.locator(".task-row").getByRole("button", { name: "编辑任务", exact: true }).click();
    dialog = page.getByRole("dialog");
    await dialog.getByLabel("开始时间").fill(`${date}T15:10`);
    await dialog.getByRole("button", { name: "保存修改" }).click();
    assert.equal(await page.evaluate(() => window.nativeQueue.find(item => item.title === "日程开始提醒").at), Date.parse(`${date}T14:10:00+08:00`));
    await nav.getByRole("button", { name: "校园", exact: true }).click();
    await page.getByRole("button", { name: "第二课堂", exact: true }).click();
    const card = title => page.locator(".campus-card").filter({ hasText: title });
    assert.equal(await card("课程直接冲突").locator(".time-conflict-direct").count(), 1);
    assert.equal(await card("课程缓冲冲突").locator(".time-conflict-buffer").count(), 1);
    assert.equal(await card("日程直接冲突").locator(".time-conflict-direct").count(), 1);
    assert.equal(await card("无冲突活动").locator("[class*=time-conflict]").count(), 0);
    await card("无冲突活动").getByRole("button", { name: "提醒报名", exact: true }).click();
    assert.ok(await card("无冲突活动").getByRole("button", { name: "取消报名提醒" }).isVisible());
    const firstAlarm = await page.evaluate(() => window.nativeQueue.find(item => item.id.startsWith("registration:clear:")));
    assert.equal(firstAlarm.at, Date.parse(`${date}T05:55:00+08:00`));
    await card("无冲突活动").getByRole("button", { name: "加入日程", exact: true }).click();
    assert.ok(await card("无冲突活动").getByRole("button", { name: "已加入日程" }).isDisabled());
    assert.equal(await card("无冲突活动").locator("[class*=time-conflict]").count(), 0);
    for (const width of [320, 390, 720, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth));
      await page.screenshot({ path: path.join(output, `activities-${width}.png`), fullPage: true });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await nav.getByRole("button", { name: "设置", exact: true }).click();
    await page.getByLabel("报名前提醒").fill("10");
    await page.getByLabel("报名前提醒").blur();
    assert.equal(await page.evaluate(() => window.nativeQueue.find(item => item.id.startsWith("registration:clear:")).at), firstAlarm.at - 5 * 60000);
    await page.reload();
    await page.getByLabel("报名前提醒").waitFor();
    assert.equal(await page.getByLabel("报名前提醒").inputValue(), "10");
    await nav.getByRole("button", { name: "校园", exact: true }).click();
    await page.getByRole("button", { name: "第二课堂", exact: true }).click();
    await card("无冲突活动").getByRole("button", { name: "取消报名提醒" }).click();
    assert.equal(await page.evaluate(() => window.nativeQueue.filter(item => item.id.startsWith("registration:clear:")).length), 0);
    await nav.getByRole("button", { name: "任务", exact: true }).click();
    await page.locator(".android-task-kinds").getByRole("button", { name: "日程", exact: true }).click();
    assert.equal(await page.locator(".task-row").count(), 2);
    const imported = page.locator(".task-row").filter({ hasText: "无冲突活动" });
    await imported.getByRole("button", { name: "删除任务", exact: true }).click();
    await imported.getByRole("button", { name: "确认删除任务", exact: true }).click();
    assert.equal(await page.locator(".task-row").count(), 1);
    assert.equal(await page.evaluate(() => window.nativeQueue.filter(item => item.body.includes("无冲突活动")).length), 0);
    assert.ok(await page.locator(".task-row").evaluate(row => {
      const body = row.querySelector(".task-body").getBoundingClientRect();
      const due = row.querySelector(".task-due").getBoundingClientRect();
      return body.bottom <= due.top;
    }));
    await page.screenshot({ path: path.join(output, "tasks-390.png"), fullPage: true });
    assert.deepEqual(errors, []);
    console.log("PASS: Android migration, schedule validation/edit/start reminders, course/schedule conflicts, registration reschedule/cancel, activity deduplication, reload/delete, 320/390/720/1280px.");
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
