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

test("portal pagination resolves official query-only PAGENUM links", () => {
  const base = "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154";
  const html = '<a href="?totalpage=1598&amp;PAGENUM=2&amp;urltype=tree.TreeTempUrl&amp;wbtreeid=1154">下页</a>';
  const [next] = __test.portalPaginationUrls(html, base);
  assert.equal(new URL(next).pathname, "/list.jsp");
  assert.equal(new URL(next).searchParams.get("PAGENUM"), "2");
});

test("portal data requests select the full template and scope cookies to the target", () => {
  const headers = __test.portalRequestHeaders([
    { name: "portal", value: "test", domain: "my.bupt.edu.cn", path: "/", expires: -1 },
    { name: "auth", value: "private", domain: "auth.bupt.edu.cn", path: "/", expires: -1 },
  ], "http://my.bupt.edu.cn/list.jsp");
  assert.match(headers["User-Agent"], /Windows NT/);
  assert.doesNotMatch(headers["User-Agent"], /Android|Mobile/);
  assert.equal(headers.Cookie, "portal=test");
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

const activityFixture = [
  { id: 101, name: "Lecture", activity_start_time: "2026-09-21T01:30:00Z", area: 0, location: "Hall" },
  { id: 102, name: "Film", activity_start_time: "2026-09-16T06:00:00Z", area: 1, location: "Cinema" },
  { id: 103, name: "Careers", activity_start_time: "2026-09-17T06:00:00Z", area: 0, location: "Room 101" },
];

test("official demands bitmask preserves all combinations and unknown fields", () => {
  for (let demands = 0; demands < 8; demands++) {
    const item = __test.toActivityItem({ ...activityFixture[0], demands: String(demands) });
    assert.deepEqual(item.activityStatus, [
      demands & 1 ? "需报名" : "不报名",
      demands & 2 ? "需签到" : "不签到",
      demands & 4 ? "需签退" : "不签退",
    ]);
  }
  assert.deepEqual(__test.toActivityItem(activityFixture[0]).activityStatus, ["报名状态未知", "签到状态未知", "签退状态未知"]);
  assert.equal(__test.toActivityItem({ ...activityFixture[0], demands: 7, attend_count: 20, attend_limit: 20 }).registrationFull, true);
  assert.equal(__test.toActivityItem({ ...activityFixture[0], demands: 7, attend_count: 20, attend_limit: 0 }).registrationFull, false);
  assert.equal(__test.toActivityItem({ ...activityFixture[0], demands: 0, attend_count: 20, attend_limit: 20 }).registrationFull, false);
});

test("official organization directory and detail metadata are merged into activity cards", async () => {
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (url.pathname === "/api/v1/group/org-college") return Response.json({ data: [{ id: 12, name: "校团委" }] });
    if (url.pathname === "/api/v1/activity") return Response.json({ data: [{ ...activityFixture[0], belong_to: 12 }] });
    return Response.json({ data: { id: 101, demands: 7, attend_count: 100, attend_limit: 100,
      signup_start_time: "2026-09-15T08:00:00Z", signup_end_time: "2026-09-20T08:00:00Z", detail: "<p>Official</p>" } });
  };
  try {
    const [item] = await __test.fetchActivityList("test-token");
    assert.equal(item.source, "校团委");
    assert.deepEqual(item.activityStatus, ["需报名", "需签到", "需签退", "人数已满"]);
    assert.equal(item.registrationStartTime, "2026-09-15T08:00:00Z");
    assert.equal(item.registrationEndTime, "2026-09-20T08:00:00Z");
  } finally { global.fetch = originalFetch; }
});

test("student activity feed uses the required filters and preserves all three activities", async () => {
  const originalFetch = global.fetch;
  global.fetch = async (url, init) => {
    assert.equal(url.origin, "https://dekt.bupt.edu.cn");
    assert.equal(init.headers.Authorization, "Bearer test-token");
    if (url.pathname !== "/api/v1/activity") {
      const id = Number(url.pathname.split("/").pop());
      assert.ok(activityFixture.some((row) => row.id === id));
      return new Response(JSON.stringify({ status: "ok", data: { id, detail: `<p>Official detail ${id}</p>` }, error: null }));
    }
    assert.deepEqual(Object.fromEntries(url.searchParams), {
      college_id: "0", grade: "0", class_id: "0", role_id: "0", page: "1", page_size: "50",
    });
    return new Response(JSON.stringify({ status: "ok", data: activityFixture, digest: [], error: null }));
  };
  try {
    const items = await __test.fetchActivityList("test-token");
    assert.deepEqual(items.map((item) => item.id), ["101", "102", "103"]);
    assert.equal(items[0].eventTime, "2026-09-21T01:30:00Z");
    assert.equal(items[0].campus, "西土城校区 Hall");
    assert.equal(items[1].campus, "沙河校区 Cinema");
    assert.equal(items[0].kind, "activity");
    assert.equal(items[0].publishedAt, items[0].eventTime);
    assert.equal(items[0].summary, "Official detail 101");
    assert.equal(items[0].detailHtml, "<p>Official detail 101</p>");
  } finally { global.fetch = originalFetch; }
});

test("portal keeps the full title, department and date from the same list row", () => {
  const rows = `<ul><li><span>教务处</span><a href="xntz_content.jsp?wbnewsid=1" title="完整的通知标题">完整的通...</a><span>2026-09-15</span></li>
    <li><span title="学生工作部（处）">学生工作...</span><a href="xntz_content.jsp?wbnewsid=2">另一条通知</a><span>2026/09/14</span></li></ul>`;
  const items = __test.parsePortalList(rows, "http://my.bupt.edu.cn/");
  assert.equal(items[0].title, "完整的通知标题");
  assert.equal(items[0].source, "教务处");
  assert.equal(items[0].publishedAt, "2026-09-15");
  assert.equal(items[1].source, "学生工作部（处）");
  assert.equal(items[1].publishedAt, "2026-09-14");
  const missing = __test.parsePortalList('<li><a href="xntz_content.jsp?wbnewsid=3">无日期通知</a></li>', "http://my.bupt.edu.cn/")[0];
  assert.equal(missing.publishedAt, "");
  assert.equal(missing.source, "发布部门未提供");
  const liveShape = '<ul class="newslist list-unstyled"><li><a href="xntz_content.jsp?wbnewsid=142172" title="关于开展2026-2027学年学生社团注册工作的通知">关于开展2026-2027学年...</a><span class="author">校团委</span><span class="time">2026-09-15</span></li></ul>';
  const [official] = __test.parsePortalList(liveShape, "http://my.bupt.edu.cn/");
  assert.equal(official.title, "关于开展2026-2027学年学生社团注册工作的通知");
  assert.equal(official.source, "校团委");
  assert.equal(official.publishedAt, "2026-09-15");
});

test("activity details preserve paragraphs and images and remove unsafe HTML", () => {
  const delta = JSON.stringify([{ insert: "第一段\n第二段\n" }, { insert: { image: "https://dekt.bupt.edu.cn/static/image.png" } }]);
  const html = __test.activityDetailHtml(delta);
  assert.match(html, /第一段/);
  assert.match(html, /第二段/);
  assert.match(html, /<img/);
  const sanitized = __test.activityDetailHtml('<p onclick="bad()">官方详情</p><script>bad()</script><img src="/static/x.png" onerror="bad()"><a href="javascript:bad()">链接</a>');
  assert.doesNotMatch(sanitized, /onclick|onerror|script|javascript/);
  assert.match(sanitized, /https:\/\/dekt.bupt.edu.cn\/static\/x.png/);
  assert.equal(__test.activityDetailHtml(null), "");
  assert.equal(__test.activityDetailHtml("<p></p>"), "");
  assert.equal(__test.activityDetailHtml("[]"), "");
  assert.match(__test.activityDetailHtml(JSON.stringify([{ insert: { image: "12345/poster.png" } }])), /https:\/\/dekt.bupt.edu.cn\/api\/v1\/image\/12345\/poster.png/);
  assert.throws(() => __test.activityDetailHtml("[invalid"));
});

test("one failed activity detail does not discard other activities or invent an AI summary", async () => {
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (url.pathname === "/api/v1/activity") return new Response(JSON.stringify({ data: activityFixture }));
    if (url.pathname.endsWith("/101")) return new Response("unavailable", { status: 500 });
    return new Response(JSON.stringify({ data: { detail: "<p>详情正文</p>" } }));
  };
  try {
    const items = await __test.fetchActivityList("test-token");
    assert.equal(items.length, 3);
    assert.match(items[0].detailError, /刷新重试/);
    assert.equal(items[1].summary, "详情正文");
    assert.equal(items[1].detailError, undefined);
  } finally { global.fetch = originalFetch; }
});

test("activity detail authentication and business errors are not treated as empty details", async () => {
  const originalFetch = global.fetch;
  try {
    for (const response of [
      () => new Response("expired", { headers: { "x-real-status": "401" } }),
      () => new Response(JSON.stringify({ status: "error", data: { detail: "" } })),
      () => new Response(JSON.stringify({ data: { id: 999, detail: "wrong activity" } })),
    ]) {
      global.fetch = async (url) => url.pathname === "/api/v1/activity"
        ? new Response(JSON.stringify({ data: [activityFixture[0]] })) : response();
      if (response().headers.get("x-real-status") === "401") {
        await assert.rejects(__test.fetchActivityList("test-token"), /登录已失效/);
      } else {
        const [item] = await __test.fetchActivityList("test-token");
        assert.ok(item.detailError);
      }
    }
  } finally { global.fetch = originalFetch; }
});

test("activity feed distinguishes a genuine empty list from HTTP and schema failures", async () => {
  const originalFetch = global.fetch;
  const cases = [
    [{ status: "ok", data: [], error: null }, {}, null],
    [{ status: "error", data: [], error: "private upstream detail" }, {}, /查询失败/],
    [{ success: false, data: [] }, {}, /查询失败/],
    [{ code: 401, data: [] }, {}, /查询失败/],
    [{ unexpected: [] }, {}, /格式已变化/],
    [{ data: null }, {}, /格式已变化/],
    [{ data: [null] }, {}, /格式已变化/],
    [{ data: [{ id: 1 }] }, {}, /缺少活动编号、名称或时间/],
    [{ data: [{ id: 1, name: "Missing time" }] }, {}, /缺少活动编号、名称或时间/],
    [{ data: [] }, { headers: { "x-real-status": "401" } }, /登录已失效/],
    [{ data: [] }, { headers: { "x-real-status": "403" } }, /登录已失效/],
    [{ data: [] }, { headers: { "x-real-status": "500" } }, /HTTP 500/],
    [{ data: [] }, { status: 503 }, /HTTP 503/],
  ];
  try {
    for (const [payload, init, error] of cases) {
      global.fetch = async () => new Response(JSON.stringify(payload), init);
      if (error) await assert.rejects(__test.fetchActivityList("test-token"), error);
      else assert.deepEqual(await __test.fetchActivityList("test-token"), []);
    }
    global.fetch = async () => new Response("<html>Login</html>");
    await assert.rejects(__test.fetchActivityList("test-token"), /没有返回有效数据/);
  } finally { global.fetch = originalFetch; }
});

test("activity mapping never fabricates the current time for missing or invalid upstream dates", () => {
  assert.equal(__test.toActivityItem({ id: 1, name: "Untimed" }), null);
  assert.equal(__test.toActivityItem({ id: 1, name: "Invalid", activity_start_time: "invalid" }), null);
  const legacy = __test.toActivityItem({ id: 1, name: "Legacy", start_time: "2026-09-21T01:30:00Z", location: "Hall" });
  assert.equal(legacy.eventTime, "2026-09-21T01:30:00Z");
  assert.equal(legacy.campus, "Hall");
});

test("failed activity refresh retains the last genuine cache instead of reporting online-empty", async () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "youxueban-activity-test-"));
  const originalFetch = global.fetch;
  const safeStorage = {
    isEncryptionAvailable: () => true,
    encryptString: (value) => Buffer.from(value),
    decryptString: (value) => value.toString(),
  };
  const runtime = createLocalRuntime({
    app: { getPath: () => temporaryRoot }, BrowserWindow: function () {}, safeStorage, session: {},
  });
  fs.writeFileSync(path.join(temporaryRoot, "local-settings.bin"), JSON.stringify({
    campus: {
      ssoAccount: "test", ssoPassword: "test", jwglAccount: "test", jwglPassword: "test",
      portalCookies: [{ expires: -1 }],
    },
  }));
  let activityPayload = { status: "ok", data: activityFixture, error: null };
  global.fetch = async (address) => {
    const url = new URL(address);
    if (url.hostname === "my.bupt.edu.cn") throw new Error("Portal unavailable");
    if (url.pathname === "/api/v1/auth/sessions") return new Response(JSON.stringify({ token: "test.session.token" }));
    assert.equal(url.pathname, "/api/v1/activity");
    return new Response(JSON.stringify(activityPayload));
  };
  try {
    const online = (await runtime.request("/api/campus")).body;
    assert.equal(online.statuses.find((status) => status.source === "activity").mode, "online");
    assert.equal(online.items.length, 3);
    activityPayload = { status: "error", data: [], error: "upstream-secret" };
    const failed = (await runtime.request("/api/campus")).body;
    assert.equal(failed.statuses.find((status) => status.source === "activity").mode, "cache");
    assert.equal(failed.items.length, 3);
    assert.ok(!JSON.stringify(failed).includes("upstream-secret"));
    activityPayload = { status: "ok", data: [], error: null };
    const empty = (await runtime.request("/api/campus")).body;
    assert.equal(empty.statuses.find((status) => status.source === "activity").mode, "online");
    assert.equal(empty.items.length, 0);
  } finally {
    global.fetch = originalFetch;
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
});

test("portal fetches fifty unique notices with departments across the full-template pages", async () => {
  const temporaryRoot = fs.mkdtempSync(path.join(os.tmpdir(), "youxueban-portal-test-"));
  const originalFetch = global.fetch;
  const pages = [];
  try {
    fs.writeFileSync(path.join(temporaryRoot, "local-settings.bin"), JSON.stringify({
      campus: {
        ssoAccount: "test", ssoPassword: "test", jwglAccount: "test", jwglPassword: "test",
        portalCookies: [{ name: "portal", value: "test", domain: "my.bupt.edu.cn", path: "/", expires: -1 }],
      },
    }));
    const runtime = createLocalRuntime({
      app: { getPath: () => temporaryRoot }, BrowserWindow: function () {}, session: {},
      safeStorage: { isEncryptionAvailable: () => true, decryptString: value => value.toString() },
    });
    global.fetch = async (address, init) => {
      const url = new URL(address);
      let body = "";
      if (url.hostname === "my.bupt.edu.cn") {
        assert.match(init.headers["User-Agent"], /Windows NT/);
        if (url.pathname === "/list.jsp") {
          const page = Number(url.searchParams.get("PAGENUM") || 1);
          pages.push(page);
          // A pinned announcement is repeated on every page.
          const ids = [1, ...Array.from({ length: 19 }, (_, i) => 2 + (page - 1) * 19 + i)];
          body = `<ul>${ids.map(id => `<li><a href="xntz_content.jsp?wbnewsid=${id}">Notice ${id}</a><span class="author">Department ${id % 3}</span><span class="time">2026-09-16</span></li>`).join("")}</ul>`;
          body += `<a href="?PAGENUM=${page + 1}&amp;wbtreeid=1154">下页</a>`;
        }
      } else {
        assert.equal(init.headers["User-Agent"], undefined);
        body = JSON.stringify(url.pathname.endsWith("/sessions") ? { token: "test.session.token" } : { status: "ok", data: [], error: null });
      }
      const response = new Response(body);
      Object.defineProperty(response, "url", { value: url.href });
      return response;
    };
    const result = await runtime.request("/api/campus");
    assert.equal(result.status, 200);
    assert.deepEqual(pages, [1, 2, 3]);
    assert.equal(result.body.items.length, 50);
    assert.equal(new Set(result.body.items.map(item => item.id)).size, 50);
    assert.ok(result.body.items.every(item => /^Department [0-2]$/.test(item.source)));
    assert.equal(result.body.statuses.find(status => status.source === "portal").mode, "online");
  } finally {
    global.fetch = originalFetch;
    fs.rmSync(temporaryRoot, { recursive: true, force: true });
  }
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
