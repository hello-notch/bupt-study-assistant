const { app, BrowserWindow, ipcMain, Menu, Notification, safeStorage, session, shell } = require("electron");
const path = require("node:path");
const { createLocalRuntime } = require("./local-runtime.cjs");

const devUrl = process.env.YOUXUEBAN_CLIENT_URL || "";
const distEntry = app.isPackaged
  ? path.join(__dirname, "web", "dist", "index.html")
  : path.resolve(__dirname, "..", "web", "dist", "index.html");

app.disableHardwareAcceleration();

const localRuntime = createLocalRuntime({ app, BrowserWindow, safeStorage, session });
ipcMain.handle("youxueban:runtime:request", (_event, route, init) => localRuntime.request(String(route || ""), init));
ipcMain.handle("youxueban:notify", (_event, title, body) => {
  if (!Notification.isSupported()) return false;
  new Notification({
    title: String(title || "邮学伴提醒").slice(0, 80),
    body: String(body || "").slice(0, 500),
    icon: path.join(__dirname, "resources", "app-icon.png"),
    silent: false,
  }).show();
  return true;
});

function createWindow() {
  const window = new BrowserWindow({
    title: "邮学伴 1.0.1",
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#eef4fa",
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });
  window.setMenuBarVisibility(false);
  window.once("ready-to-show", () => window.show());
  window.webContents.once("did-finish-load", () => window.show());
  const showTimer = setTimeout(() => {
    if (!window.isDestroyed()) window.show();
  }, 3000);
  window.once("closed", () => clearTimeout(showTimer));
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  const loadPromise = devUrl ? window.loadURL(devUrl) : window.loadFile(distEntry);
  loadPromise.catch((error) => {
    if (window.isDestroyed()) return;
    const detail = String(error?.message || error);
    const errorPage = `<!doctype html><meta charset="utf-8"><title>邮学伴启动失败</title><style>body{font-family:system-ui;background:#eef4fa;color:#17324d;display:grid;place-items:center;min-height:100vh;margin:0}.card{max-width:560px;background:white;padding:32px;border-radius:20px;box-shadow:0 16px 48px #17324d22}h1{margin-top:0}code{word-break:break-all}</style><main class="card"><h1>邮学伴启动失败</h1><p>本地页面未能加载，请重新安装完整客户端</p><code>${detail.replace(/[&<>]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[character])}</code></main>`;
    window.loadURL(`data:text/html;charset=UTF-8,${encodeURIComponent(errorPage)}`);
    window.show();
  });
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createWindow();
  app.on("activate", () => { if (!BrowserWindow.getAllWindows().length) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
