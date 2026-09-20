const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const { execFileSync, spawn } = require("node:child_process");
const { chromium } = require("../client/node_modules/playwright");
const adb = path.resolve(__dirname, "../.test-tmp/android-sdk/platform-tools/adb.exe");
const serial = process.env.ANDROID_SERIAL;
if (!serial) throw new Error("Set ANDROID_SERIAL to the authorized test device");
const shell = (...args) => execFileSync(adb, ["-s", serial, "shell", ...args], { encoding: "utf8" });
const taskName = "Android background reminder regression";

async function main() {
  const browser = await chromium.connectOverCDP("http://127.0.0.1:9224");
  try {
    const page = browser.contexts().flatMap(c => c.pages()).find(p => p.url().includes("/web/index.html"));
    assert.ok(page);
    const nav = page.getByRole("navigation", { name: "移动端主导航" });
    const go = name => nav.getByRole("button", { name, exact: true }).click();
    const back = async () => {
      shell("input", "keyevent", "4");
      await page.waitForTimeout(500);
    };
    const mode = process.argv[2] || "layout";
    if (mode === "layout") {
      await go("课程");
      const originalWeek = await page.getByLabel("查看第几周课程").inputValue();
      await page.getByRole("button", { name: "添加课程", exact: true }).click();
      await page.getByRole("dialog").waitFor();
      await back();
      assert.equal(await page.getByRole("dialog").count(), 0);
      const course = page.locator(".course-cell").first();
      if (await course.count()) {
        await course.click();
        await page.getByRole("button", { name: "编辑课程", exact: true }).click();
        await back();
        assert.equal(await page.locator(".drawer .course-edit-form").count(), 0);
        assert.equal(await page.locator(".drawer").count(), 1);
        await back();
        assert.equal(await page.locator(".drawer").count(), 0);
        await course.click();
        await page.getByRole("button", { name: "编辑课程", exact: true }).click();
        await page.getByRole("dialog").getByRole("button", { name: "关闭", exact: true }).click();
        await go("任务");
        await back();
        assert.ok(page.url().endsWith("/courses"), "A dismissed course editor must not consume the next Back");
      }
      const week = page.getByLabel("查看第几周课程");
      await week.fill("22");
      await week.press("Enter");
      if (await page.locator(".course-cell").count() === 0) {
        assert.equal(await page.locator(".section-label:visible").count(), 14);
      }
      const centered = await page.locator(".course-import-button").evaluate(el => {
        const button = el.getBoundingClientRect(), icon = el.querySelector("svg").getBoundingClientRect();
        return Math.abs(button.x + button.width / 2 - icon.x - icon.width / 2) < 1 &&
          Math.abs(button.y + button.height / 2 - icon.y - icon.height / 2) < 1;
      });
      assert.ok(centered);
      await page.screenshot({ path: ".test-tmp/android-empty-week-fixed.png" });
      await week.fill(originalWeek);
      await week.press("Enter");
      await page.getByRole("button", { name: "导入课表", exact: true }).click();
      await back();
      assert.equal(await page.getByRole("dialog").count(), 0);
      await go("任务");
      await page.getByRole("button", { name: "添加任务", exact: true }).click();
      await back();
      assert.equal(await page.getByRole("dialog").count(), 0);
      await go("助手");
      assert.ok(await page.locator(".thinking-toggle").evaluate(el => {
        const toggle = el.getBoundingClientRect();
        const send = document.querySelector(".composer-send").getBoundingClientRect();
        return toggle.right <= send.left && Math.abs(toggle.y - send.y) < 1;
      }));
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth));
      console.log("PASS native back: add/edit course, task, import; empty-week rows; centered import; composer alignment");
    }
    if (mode === "reminder") {
      const logs = [];
      const logcat = spawn(adb, ["-s", serial, "logcat", "-T", "1", "-v", "brief"]);
      let buffer = "";
      logcat.stdout.on("data", chunk => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop();
        logs.push(...lines.filter(line => /YouXueBan|ReminderReceiver/.test(line)));
      });
      try {
      await go("任务");
      await page.getByRole("button", { name: "添加任务", exact: true }).click();
      const dialog = page.getByRole("dialog");
      await dialog.getByLabel("任务内容", { exact: true }).fill(taskName);
      const dueAt = await page.evaluate(() => {
        const date = new Date(Date.now() + 120000);
        const pad = n => String(n).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
      });
      await dialog.getByLabel("截止时间", { exact: true }).fill(dueAt);
      await dialog.getByLabel("提前提醒（分钟）", { exact: true }).fill("0");
      await dialog.getByRole("switch").check();
      await dialog.getByRole("button", { name: "添加任务", exact: true }).click();
      await page.waitForTimeout(800);
      const alarm = shell("dumpsys", "alarm");
      assert.ok(alarm.includes("cn.edu.bupt.youxueban.REMIND"));
      const testId = await page.evaluate(name => {
        const state = JSON.parse(localStorage.getItem("youxueban-state-v10"));
        return state.tasks.filter(task => task.title === name).sort((a, b) => b.id - a.id)[0].id;
      }, taskName);
      shell("input", "keyevent", "3");
      console.log("Scheduled temporary task; waiting in background for two minutes.");
      await new Promise(resolve => setTimeout(resolve, 125000));
      const records = shell("dumpsys", "notification").split("\n").filter(line => /NotificationRecord.*cn.edu.bupt.youxueban/.test(line));
      console.log("Native notification records:", records);
      console.log("App-specific delivery log:", logs.slice(-25).join("\n"));
      assert.ok(records.some(line => line.includes(`tag=task:${testId}:`)), "The newly scheduled notification must arrive without reopening the app");
      } finally { logcat.kill(); }
    }
    if (mode === "image") {
      await go("助手");
      console.log(await page.evaluate(async () => {
        const result = await window.youxuebanRuntime.request("/api/config");
        return { model: result.body.assistant?.model, allowed: result.body.assistant?.allowedFileTypes };
      }));
      await page.getByRole("button", { name: "上传图片", exact: true }).click();
      console.log("Opened native image picker");
    }
    if (mode === "image-send") {
      await go("助手");
      assert.equal(await page.locator(".assistant-composer textarea").inputValue(), "", "Do not overwrite a user's draft");
      const original = await page.evaluate(() => JSON.parse(localStorage.getItem("youxueban-state-v10")).activeConversationId);
      const create = page.getByRole("button", { name: "新建对话", exact: true });
      if (await create.count()) await create.click();
      const testConversation = await page.evaluate(() => JSON.parse(localStorage.getItem("youxueban-state-v10")).activeConversationId);
      const image = await page.evaluate(() => {
        const canvas = document.createElement("canvas");
        canvas.width = 512; canvas.height = 512;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 512, 512);
        ctx.fillStyle = "#0066ff"; ctx.fillRect(100, 100, 312, 312);
        return canvas.toDataURL("image/png").split(",")[1];
      });
      await page.locator(".assistant-composer input[type=file]").setInputFiles({
        name: "youxueban-test-square.png", mimeType: "image/png", buffer: Buffer.from(image, "base64"),
      });
      await page.locator(".assistant-attachment-tray img").waitFor();
      await page.locator(".assistant-composer textarea").fill("这是图片上传回归测试。请只用一句话描述图片中的颜色和图形，不调用任何工具。");
      await page.getByRole("button", { name: "发送", exact: true }).click();
      await page.waitForFunction(() => document.querySelector(".assistant-composer textarea").value === "" &&
        !document.querySelector(".typing"), undefined, { timeout: 90000 });
      const reply = await page.locator(".message.assistant .markdown-body").last().innerText();
      console.log("Image response:", reply);
      assert.ok(/蓝/.test(reply) && /方/.test(reply), "The upstream model should identify the synthetic blue square");
      await page.screenshot({ path: ".test-tmp/android-image-response.png" });
      if (await page.evaluate(() => innerHeight < 620)) await back();
      const testItem = page.locator(`.conversation-item[data-conversation-id="${testConversation}"]`);
      await testItem.getByRole("button", { name: "删除对话", exact: true }).click();
      await testItem.getByRole("button", { name: "确认删除对话", exact: true }).click();
      const prior = page.locator(`.conversation-item[data-conversation-id="${original}"] .conversation-select`);
      if (await prior.count()) await prior.click();
      console.log("PASS real image decode, preview, native bridge and upstream image response; test conversation removed");
    }
    if (mode === "cleanup") {
      await go("任务");
      await page.getByPlaceholder("搜索任务或课程").fill(taskName);
      const rows = page.locator(".task-row").filter({ hasText: taskName });
      const count = await rows.count();
      while (await rows.count()) {
        await rows.first().getByRole("button", { name: "删除任务", exact: true }).click();
        await rows.first().getByRole("button", { name: "确认删除任务", exact: true }).click();
      }
      await page.getByPlaceholder("搜索任务或课程").fill("");
      await go("课程");
      await page.evaluate(name => {
        const key = "youxueban-state-v10";
        const state = JSON.parse(localStorage.getItem(key));
        state.notifications = state.notifications.filter(item =>
          !(item.type === "task" && item.body.startsWith(`${name}（截止 `)));
        localStorage.setItem(key, JSON.stringify(state));
      }, taskName);
      console.log(`Removed ${count} temporary reminder tasks; existing tasks retained. Restart the app to reload the cleaned test-message list.`);
    }
    if (mode === "theme") {
      await go("设置");
      const original = await page.locator(".appearance-settings .segmented button.active").innerText();
      try {
        for (const [label, name, color] of [["浅色", "light", "rgb(238, 244, 250)"], ["深色", "dark", "rgb(11, 16, 24)"]]) {
          await page.getByRole("button", { name: label, exact: true }).click();
          await go("课程");
          await page.waitForTimeout(500);
          assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), color);
          fs.writeFileSync(`.test-tmp/android-system-bars-${name}.png`, execFileSync(adb, ["-s", serial, "exec-out", "screencap", "-p"]));
          await go("设置");
        }
      } finally {
        await page.getByRole("button", { name: original, exact: true }).click();
        await go("课程");
      }
      console.log("Captured light/dark native system bars; original theme restored");
    }
    if (mode === "gesture") {
      await go("任务");
      await page.getByRole("button", { name: "添加任务", exact: true }).click();
      const sizes = [...shell("wm", "size").matchAll(/(\d+)x(\d+)/g)];
      const [, width, height] = sizes.at(-1);
      // Use the right edge away from the OEM's left-side quick-tools handle.
      shell("input", "swipe", String(Number(width) - 2), String(Math.round(Number(height) * .78)),
        String(Math.round(Number(width) * .65)), String(Math.round(Number(height) * .78)), "200");
      await page.waitForTimeout(700);
      assert.equal(await page.getByRole("dialog").count(), 0);
      assert.ok(page.url().endsWith("/tasks"));
      console.log("PASS Android edge-back gesture closes task dialog and keeps its parent page");
    }
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
