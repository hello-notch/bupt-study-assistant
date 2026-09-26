const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("../client/node_modules/playwright");

async function main() {
  const output = path.resolve(__dirname, "../.test-tmp/android-schedule-layout");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.connectOverCDP(process.env.ANDROID_CDP_URL || "http://127.0.0.1:9224");
  try {
    const page = browser.contexts().flatMap(context => context.pages()).find(page => page.url().includes("/web/index.html"));
    assert.ok(page, "Forward the current Android WebView debugging socket first");
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.getByRole("navigation", { name: "移动端主导航" }).getByRole("button", { name: "课程", exact: true }).click();
    await page.locator(".schedule-grid").waitFor();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const dimensions = await page.evaluate(() => {
      const wrap = document.querySelector(".schedule-wrap");
      const nav = document.querySelector(".mobile-nav");
      const empty = document.querySelector(".courses-page > .empty-state");
      const courses = [...document.querySelectorAll(".course-cell")];
      return {
        width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth > innerWidth,
        visibleHeight: wrap.clientHeight, contentHeight: wrap.scrollHeight,
        bottomGap: nav.getBoundingClientRect().top - wrap.getBoundingClientRect().bottom - (empty?.getBoundingClientRect().height || 0),
        courseHeights: courses.map(el => el.getBoundingClientRect().height),
        homeworkBadges: document.querySelectorAll(".course-homework-badge").length,
        badgesWithinCards: [...document.querySelectorAll(".course-homework-badge")].every(el =>
          el.getBoundingClientRect().bottom <= el.parentElement.getBoundingClientRect().bottom),
      };
    });
    console.log("Android schedule dimensions", JSON.stringify(dimensions));
    assert.equal(dimensions.overflow, false);
    assert.ok(dimensions.bottomGap >= -1);
    assert.ok(dimensions.visibleHeight <= dimensions.contentHeight + 1);
    assert.ok(dimensions.badgesWithinCards);
    assert.ok(dimensions.courseHeights.every(height => height >= 107.9 && height <= 150));
    await page.screenshot({ path: path.join(output, "courses-top.png"), animations: "disabled" });
    await page.locator(".schedule-wrap").evaluate(el => { el.scrollTop = el.scrollHeight; });
    if (dimensions.contentHeight > dimensions.visibleHeight + 1) {
      assert.ok(await page.locator(".schedule-wrap").evaluate(el => el.scrollTop > 0));
    }
    await page.screenshot({ path: path.join(output, "courses-bottom.png"), animations: "disabled" });
    await page.locator(".schedule-wrap").evaluate(el => { el.scrollTop = 0; });
    assert.deepEqual(errors, []);
    console.log("PASS: Android device schedule layout", JSON.stringify(dimensions));
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
