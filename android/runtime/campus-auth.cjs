const { BrowserWindow, call } = require("./platform.cjs");

class CampusBrowserSessionExpired extends Error {}
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function inLoginFrame(script) {
  return `(() => {
    if (location.hostname !== 'auth.bupt.edu.cn') return null;
    const frame = document.querySelector('#loginIframe');
    const target = frame ? frame.contentWindow : window;
    if (!target || target.location.hostname !== 'auth.bupt.edu.cn') return null;
    return target.eval(${JSON.stringify(script)});
  })()`;
}
function isPortal(value) {
  try {
    const url = new URL(value);
    return url.hostname === "my.bupt.edu.cn" && !url.pathname.includes("/system/resource/code/auth/clogin.jsp");
  } catch { return false; }
}

let authentication;
async function authenticatePortalWithPlaywright(options) {
  if (!authentication) authentication = authenticatePortal(options).finally(() => { authentication = null; });
  return authentication;
}
async function authenticatePortal({ startUrl, account, password }) {
  const window = new BrowserWindow();
  try {
    await window.loadURL(startUrl);
    let submitted = false;
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
      const url = window.webContents.getURL();
      if (isPortal(url)) return await call("cookies");
      const host = new URL(url).hostname;
      if (host !== "auth.bupt.edu.cn") {
        await pause(300);
        continue;
      }
      const state = await window.webContents.executeJavaScript(inLoginFrame(`(() => {
        const user = document.querySelector('#username, input[name="学工号"], input[autocomplete="username"]');
        const password = document.querySelector('#password, input[type="password"]');
        return { form: Boolean(user && password), captcha: Boolean(document.querySelector('#cptValue, .img-code')?.offsetParent),
          error: document.querySelector('.error-message, #msg')?.textContent?.trim() || '' };
      })()`));
      if (submitted && state?.error && !state.captcha) throw new Error(`统一认证：${state.error.slice(0, 160)}`);
      if (state?.form && !submitted) {
        // Only the trusted authentication origin receives credentials.
        await window.webContents.executeJavaScript(inLoginFrame(`(() => {
          if (location.hostname !== 'auth.bupt.edu.cn') return;
          const tabs = [...document.querySelectorAll('a[href="javascript:;"]')];
          if (tabs[1]) tabs[1].click();
          const set = (el, value) => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
          };
          set(document.querySelector('#username, input[name="学工号"], input[autocomplete="username"]'), ${JSON.stringify(account)});
          set(document.querySelector('#password, input[type="password"]'), ${JSON.stringify(password)});
          const captcha = document.querySelector('#cptValue, .img-code');
          if (!captcha || !captcha.offsetParent) {
            const button = [...document.querySelectorAll('input.submit-btn, button[type=submit]')].find(el => el.offsetParent);
            button?.click();
          }
        })()`));
        submitted = true;
        await window.show();
      }
      await pause(500);
    }
    throw new Error("统一认证未完成，请检查账号密码或在登录窗口完成验证");
  } finally { window.destroy(); }
}

async function openCampusServiceWithPlaywright({ startUrl, successHost, successPath, cookies }) {
  await call("setCookies", { cookies });
  const window = new BrowserWindow();
  try {
    await window.loadURL(startUrl);
    const deadline = Date.now() + 30_000;
    while (Date.now() < deadline) {
      const url = new URL(window.webContents.getURL());
      if (url.hostname === successHost && url.pathname.includes(successPath)) {
        return { url: url.href, cookies: await call("cookies"), html: "" };
      }
      if (url.hostname === "auth.bupt.edu.cn") throw new CampusBrowserSessionExpired("统一认证会话已失效");
      await pause(300);
    }
    throw new Error("校园服务登录未完成，请重试");
  } finally { window.destroy(); }
}
module.exports = { authenticatePortalWithPlaywright, openCampusServiceWithPlaywright, CampusBrowserSessionExpired };
