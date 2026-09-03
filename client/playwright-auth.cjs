const { chromium } = require("playwright");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

let executablePromise;

async function ensureChromiumExecutable() {
  if (executablePromise) return executablePromise;
  executablePromise = (async () => {
    const candidates = [chromium.executablePath(), ...commonChromiumPaths()];
    const existing = candidates.find((candidate) => candidate && fs.existsSync(candidate));
    if (existing) return existing;
    const cli = path.join(path.dirname(require.resolve("playwright/package.json")), "cli.js");
    const result = spawnSync(process.execPath, [cli, "install", "chromium", "--no-shell"], {
      stdio: "ignore",
      env: { ...process.env, PLAYWRIGHT_BROWSERS_PATH: process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(process.env.LOCALAPPDATA || path.dirname(require.resolve("playwright")), "ms-playwright") },
    });
    if (result.status !== 0) throw new Error("未找到 Chromium，自动下载失败，请检查网络后重试");
    const downloaded = [chromium.executablePath(), ...commonChromiumPaths()].find((candidate) => candidate && fs.existsSync(candidate));
    if (!downloaded) throw new Error("Chromium 下载完成但未找到可执行文件");
    return downloaded;
  })();
  return executablePromise;
}

function commonChromiumPaths() {
  const roots = [
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "ms-playwright"),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application"),
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google", "Chrome", "Application"),
    process.env["PROGRAMFILES(X86)"] && path.join(process.env["PROGRAMFILES(X86)"], "Google", "Chrome", "Application"),
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Microsoft", "Edge", "Application"),
  ].filter(Boolean);
  const result = [];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    if (path.basename(root).toLowerCase() === "application") {
      result.push(path.join(root, "chrome.exe"), path.join(root, "msedge.exe"));
      continue;
    }
    for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
      if (!entry.isDirectory() || !entry.name.startsWith("chromium-")) continue;
      result.push(path.join(root, entry.name, "chrome-win", "chrome.exe"), path.join(root, entry.name, "chrome-win64", "chrome.exe"));
    }
  }
  return result;
}

class CampusBrowserSessionExpired extends Error {}

async function authenticatePortalWithPlaywright({ startUrl, account, password }) {
  return await withCampusBrowser(async (context) => {
    const page = await context.newPage();
    await page.goto(startUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
    if (!isPortalPage(page.url())) await submitPortalLogin(page, account, password);
    if (!isPortalPage(page.url())) throw new Error("统一认证登录后没有进入信息门户");
    return sanitizeCookies(await context.cookies());
  });
}

async function openCampusServiceWithPlaywright({ startUrl, successHost, successPath, cookies }) {
  return await withCampusBrowser(async (context) => {
    const reusableCookies = sanitizeCookies(cookies);
    if (reusableCookies.length) await context.addCookies(reusableCookies);
    const page = await context.newPage();
    await page.goto(startUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
    if (page.url().includes("auth.bupt.edu.cn/authserver/login")) {
      throw new CampusBrowserSessionExpired("统一认证会话已失效");
    }
    const url = new URL(page.url());
    if (url.hostname !== successHost || !url.pathname.includes(successPath)) {
      throw new Error(`校园服务登录后进入了非预期页面（${url.hostname}${url.pathname}）`);
    }
    return { url: page.url(), html: await page.content(), cookies: sanitizeCookies(await context.cookies()) };
  });
}

async function withCampusBrowser(callback) {
  const executablePath = await ensureChromiumExecutable();
  const browser = await chromium.launch({
    executablePath,
    headless: false,
    args: ["--disable-blink-features=AutomationControlled"],
    ignoreDefaultArgs: ["--enable-automation"],
  });
  try {
    const context = await browser.newContext();
    return await callback(context);
  } finally {
    await browser.close();
  }
}

async function submitPortalLogin(page, account, password) {
  await page.locator("#loginIframe").waitFor({ state: "attached", timeout: 15_000 });
  const frame = page.frameLocator("#loginIframe");
  const loginTabs = frame.locator('a[href="javascript:;"]');
  await loginTabs.nth(1).waitFor({ state: "visible", timeout: 15_000 });
  await loginTabs.nth(1).click();
  const username = frame.locator("#username");
  const passwordBox = frame.locator("#password");
  await username.waitFor({ state: "visible", timeout: 15_000 });
  await username.fill(account);
  await passwordBox.fill(password);
  const captcha = frame.locator("#cptValue");
  if (await captcha.isVisible()) {
    try {
      await page.waitForURL((url) => isPortalPage(url.toString()), { waitUntil: "domcontentloaded", timeout: 90_000 });
    } catch {
      throw new Error("请在弹出的统一认证窗口中完成验证码后重试");
    }
    return;
  }
  await frame.locator("input.submit-btn:visible").first().click();
  try {
    await page.waitForURL((url) => isPortalPage(url.toString()), { waitUntil: "domcontentloaded", timeout: 30_000 });
  } catch {
    const detail = await loginError(frame);
    throw new Error(detail || "统一认证登录未完成，请检查账号密码或验证码");
  }
}

function sanitizeCookies(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((cookie) => cookie && /(^|\.)bupt\.edu\.cn$/i.test(String(cookie.domain || ""))).map((cookie) => ({
    name: String(cookie.name || ""),
    value: String(cookie.value || ""),
    domain: String(cookie.domain || ""),
    path: String(cookie.path || "/"),
    expires: Number(cookie.expires) || -1,
    httpOnly: Boolean(cookie.httpOnly),
    secure: Boolean(cookie.secure),
    sameSite: ["Strict", "Lax", "None"].includes(cookie.sameSite) ? cookie.sameSite : "Lax",
  })).filter((cookie) => cookie.name && cookie.domain);
}

function isPortalPage(value) {
  try {
    const url = new URL(value);
    return url.hostname === "my.bupt.edu.cn" && !url.pathname.includes("/system/resource/code/auth/clogin.jsp");
  } catch {
    return false;
  }
}

async function loginError(frame) {
  for (const selector of ["#msg", ".login-error", ".auth_error", ".errors", ".error", '[role="alert"]']) {
    const items = frame.locator(selector);
    for (let index = 0; index < await items.count(); index += 1) {
      const item = items.nth(index);
      if (!await item.isVisible()) continue;
      const value = String(await item.textContent() || "").replace(/\s+/g, " ").trim();
      if (value) return value.slice(0, 200);
    }
  }
  return "";
}

module.exports = {
  authenticatePortalWithPlaywright,
  openCampusServiceWithPlaywright,
  CampusBrowserSessionExpired,
  __test: { sanitizeCookies },
};
