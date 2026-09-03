const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createLocalRuntime, __test } = require("./local-runtime.cjs");
const { __test: browserAuthTest } = require("./playwright-auth.cjs");

test("personal schedule splits courses that share one cell in different weeks", () => {
  const courseCell = `<td><div class="kbcontent">课程甲<br>教师甲<br>1(周)[01-02节]<br>教室甲<br>课程乙<br>课程类别<br>教师乙<br>3-10(周)[03-04节]<br>教室乙</div><div class="kbcontent1">不应重复</div></td>`;
  const emptyCell = "<td></td>";
  const row = `<tr><td>节次</td>${courseCell}${emptyCell.repeat(6)}</tr>`;
  const courses = __test.parsePersonalSchedule(`<table>${row}${row}</table>`);

  assert.deepEqual(courses, [
    { name: "课程甲", teacher: "教师甲", location: "教室甲", weeks: "1", weekday: 1, startSection: 1, endSection: 2 },
    { name: "课程乙 课程类别", teacher: "教师乙", location: "教室乙", weeks: "3-10", weekday: 1, startSection: 1, endSection: 2 },
  ]);
});

test("dormitory parser maps current campus building names", () => {
  assert.equal(__test.parseDormitory("A410").campus, "沙河");
  assert.equal(__test.parseDormitory("A410").park, "雁北园");
  assert.equal(__test.parseDormitory("S2-410").park, "雁南园");
  assert.equal(__test.parseDormitory("学8 321").campus, "西土城");
});

test("electricity parser reads the official d.data response envelope", () => {
  const dormitory = __test.parseDormitory("A410");
  const building = { partmentId: "shahe-a", partmentName: "沙河校区雁北园A座" };
  const room = { dromNum: "room-410", dromName: "A楼410宿舍" };
  const payload = { e: 0, d: { data: [building, room] } };

  assert.deepEqual(__test.dataRows(payload), [building, room]);
  assert.equal(__test.houseMatches(building, dormitory), true);
  assert.equal(__test.roomMatches(room, dormitory), true);
  assert.deepEqual(__test.electricityData({ e: 0, d: { data: { surplus: "12.34" } } }), { surplus: "12.34" });
});

test("portal pagination keeps only later pages from the notice list", () => {
  const html = [
    '<a href="list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154&page=2">下一页</a>',
    '<a href="list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154&a1154p=3">第三页</a>',
    '<a href="list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154&page=1">首页</a>',
    '<a href="list.jsp?wbtreeid=999&page=3">其他栏目</a>',
  ].join("");

  assert.deepEqual(__test.portalPaginationUrls(html, "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154"), [
    "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154&page=2",
    "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154&a1154p=3",
  ]);
});

test("week parser removes the section suffix returned by jwgl", () => {
  assert.equal(__test.normalizeScheduleWeeks("1(周)[01-02-03-04-05-06节]"), "1");
  assert.equal(__test.normalizeScheduleWeeks("3-18(周)[03-04节]"), "3-18");
});

test("JWGL course name removes its leading dash separator", () => {
  assert.equal(__test.normalizeScheduleCourseName("- 工程管理概论"), "工程管理概论");
  assert.equal(__test.normalizeScheduleCourseName("现代控制理论#"), "现代控制理论#");
});

test("activity rows accept the current nested list response", () => {
  assert.deepEqual(__test.activityRows({ data: { list: [{ id: 1 }] } }), [{ id: 1 }]);
  assert.deepEqual(__test.activityRows({ data: [] }), []);
});

test("campus cookie header only sends cookies valid for the target URL", () => {
  const future = Date.now() / 1000 + 3600;
  const cookies = [
    { name: "portal", value: "one", domain: "my.bupt.edu.cn", path: "/", secure: false, expires: -1 },
    { name: "auth", value: "two", domain: "auth.bupt.edu.cn", path: "/", secure: true, expires: future },
    { name: "expired", value: "three", domain: "my.bupt.edu.cn", path: "/", secure: false, expires: 1 },
  ];
  assert.equal(__test.cookieHeaderForUrl(cookies, "http://my.bupt.edu.cn/list.jsp"), "portal=one");
  assert.equal(__test.cookieHeaderForUrl(cookies, "https://auth.bupt.edu.cn/authserver/login"), "auth=two");
});

test("Playwright campus cookies are reduced to serializable BUPT fields", () => {
  assert.deepEqual(browserAuthTest.sanitizeCookies([
    { name: "TGC", value: "secret", domain: "auth.bupt.edu.cn", path: "/authserver", expires: -1, httpOnly: true, secure: true, sameSite: "None", priority: "High" },
    { name: "other", value: "ignored", domain: "example.com", path: "/" },
  ]), [
    { name: "TGC", value: "secret", domain: "auth.bupt.edu.cn", path: "/authserver", expires: -1, httpOnly: true, secure: true, sameSite: "None" },
  ]);
});

test("assistant titles always use the dedicated summary model", async () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "youxueban-title-test-"));
  const originalFetch = global.fetch;
  let requestBody;
  global.fetch = async (_url, init) => {
    requestBody = JSON.parse(init.body);
    return { ok: true, json: async () => ({ choices: [{ message: { content: "高等数学复习" } }] }) };
  };
  try {
    const runtime = createLocalRuntime({
      app: { getPath: () => temporaryRoot },
      BrowserWindow: function BrowserWindow() {},
      safeStorage: {
        isEncryptionAvailable: () => true,
        encryptString: (value) => Buffer.from(value, "utf8"),
        decryptString: (value) => Buffer.from(value).toString("utf8"),
      },
      session: {},
    });
    assert.equal((await runtime.request("/api/local/settings/ai", { method: "POST", body: JSON.stringify({ apiKey: "test-key", model: "deepseek-v4-pro" }) })).status, 200);
    const result = await runtime.request("/api/assistant/title", { method: "POST", body: JSON.stringify({ messages: [{ role: "user", content: "帮我复习高数" }] }) });
    assert.equal(result.status, 200);
    assert.equal(requestBody.model, "deepseek-v4-flash");
    assert.deepEqual(requestBody.thinking, { type: "disabled" });
  } finally {
    global.fetch = originalFetch;
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});

test("deleting campus credentials also removes the public account names", async () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "youxueban-campus-delete-"));
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(value, "utf8"),
    decryptString: (value) => Buffer.from(value).toString("utf8"),
  };
  const runtime = createLocalRuntime({
    app: { getPath: () => temporaryRoot },
    BrowserWindow: function BrowserWindow() {},
    safeStorage,
    session: { fromPartition: () => ({ clearStorageData: async () => undefined }) },
  });
  fs.writeFileSync(path.join(temporaryRoot, "local-settings.bin"), safeStorage.encryptString(JSON.stringify({
    campus: { ssoAccount: "old-account", ssoPassword: "old-password", jwglAccount: "old-account", jwglPassword: "old-password" },
    ai: { apiKey: "key", model: "deepseek-v4-flash" },
  })));
  try {
    const result = await runtime.request("/api/local/settings/campus", { method: "DELETE" });
    assert.equal(result.status, 200);
    const status = (await runtime.request("/api/local/settings/status")).body;
    assert.deepEqual(status.campus, { configured: false, ssoAccount: "", jwglAccount: "" });
  } finally {
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});
