const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

function loadAuth() {
  const urls = [];
  let destroyed = 0;
  class BrowserWindow {
    webContents = { getURL: () => "http://my.bupt.edu.cn/list.jsp" };
    async loadURL(url) { urls.push(url); }
    destroy() { destroyed++; }
  }
  const context = {
    module: { exports: {} }, URL, setTimeout,
    require: name => {
      assert.equal(name, "./platform.cjs");
      return { BrowserWindow, call: async operation => {
        assert.equal(operation, "cookies");
        return [{ name: "fixture", value: "fixture", domain: "my.bupt.edu.cn" }];
      } };
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../android/runtime/campus-auth.cjs"), "utf8"), context);
  return { auth: context.module.exports, urls, destroyed: () => destroyed };
}

test("Android forced renewal reaches CAS even when a portal cookie remains valid", async () => {
  const { auth, urls, destroyed } = loadAuth();
  const startUrl = "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154";
  const cookies = await auth.authenticatePortalWithPlaywright({ startUrl, forceRefresh: true });
  const target = new URL(urls[0]);
  assert.equal(target.origin, "https://auth.bupt.edu.cn");
  assert.equal(target.pathname, "/authserver/login");
  assert.equal(target.searchParams.get("service"), startUrl);
  assert.equal(cookies.length, 1);
  assert.equal(destroyed(), 1);
});

test("Android normal portal access still reuses the existing session", async () => {
  const { auth, urls, destroyed } = loadAuth();
  const startUrl = "http://my.bupt.edu.cn/list.jsp";
  await auth.authenticatePortalWithPlaywright({ startUrl });
  assert.deepEqual(urls, [startUrl]);
  assert.equal(destroyed(), 1);
});
