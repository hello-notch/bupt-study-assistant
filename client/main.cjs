const { app, BrowserWindow, ipcMain, Menu, safeStorage, shell } = require("electron");
const fs = require("node:fs");
const path = require("node:path");

const devUrl = process.env.YOUXUEBAN_CLIENT_URL || "";
const packagedAppUrl = "http://[2001:da8:215:8f02:7f5b:8f99:8107:90c3]:8787";
const distEntry = app.isPackaged
  ? path.join(__dirname, "web", "dist", "index.html")
  : path.resolve(__dirname, "..", "web", "dist", "index.html");

function credentialPath() {
  return path.join(app.getPath("userData"), "saved-login.bin");
}

function readSavedLogin() {
  try {
    if (!safeStorage.isEncryptionAvailable() || !fs.existsSync(credentialPath())) return null;
    const decrypted = safeStorage.decryptString(fs.readFileSync(credentialPath()));
    const value = JSON.parse(decrypted);
    return typeof value?.nickname === "string" && typeof value?.password === "string"
      ? { nickname: value.nickname, password: value.password }
      : null;
  } catch {
    return null;
  }
}

function writeSavedLogin(value) {
  if (!safeStorage.isEncryptionAvailable()) throw new Error("当前系统无法安全保存登录信息");
  const nickname = String(value?.nickname || "");
  const password = String(value?.password || "");
  if (!nickname || !password) throw new Error("登录信息不完整");
  fs.mkdirSync(path.dirname(credentialPath()), { recursive: true });
  fs.writeFileSync(credentialPath(), safeStorage.encryptString(JSON.stringify({ nickname, password })));
}

function clearSavedLogin() {
  try {
    if (fs.existsSync(credentialPath())) fs.rmSync(credentialPath());
  } catch {
    // The login flow remains usable even if an already inaccessible credential file cannot be removed.
  }
}

ipcMain.handle("youxueban:credentials:load", () => readSavedLogin());
ipcMain.handle("youxueban:credentials:save", (_event, value) => writeSavedLogin(value));
ipcMain.handle("youxueban:credentials:clear", () => clearSavedLogin());

function createWindow() {
  const window = new BrowserWindow({
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
      preload: path.join(__dirname, "preload.cjs"),
    },
  });
  window.setMenuBarVisibility(false);
  window.once("ready-to-show", () => window.show());
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  const appUrl = devUrl || (app.isPackaged ? packagedAppUrl : "");
  if (appUrl) window.loadURL(appUrl);
  else window.loadFile(distEntry);
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createWindow();
  app.on("activate", () => { if (!BrowserWindow.getAllWindows().length) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
