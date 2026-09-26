const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const Module = require("node:module");
const ts = require("../web/node_modules/typescript");
const { retryCampus, DELAY_MS, ATTEMPTS } = require("../android/runtime/retry.cjs");
const compiled = new Module(__filename, module);
compiled._compile(ts.transpileModule(fs.readFileSync(require.resolve("../web/src/electricity-history.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, __filename);
const { chinaDate, hasSnapshotForDate, saveSnapshot, usageChart } = compiled.exports;
const { createCourseResolver } = require("../android/runtime/ucloud.cjs").__test;
const { BrowserWindow } = require("../android/runtime/platform.cjs");
const snapshot = (date, balance, extra = {}) => ({ date, balance, unit: "元", dormitory: "A410", accountKey: "one", ...extra });

test("five bounded retries, four-second production delay, sanitized final error", async () => {
  assert.equal(DELAY_MS, 4000);
  assert.equal(ATTEMPTS, 5);
  let attempts = 0;
  await assert.rejects(retryCampus("校园", async () => { attempts++; throw Error("secret-token"); }, undefined, { delay: 0 }), error =>
    error.message.includes("5 次") && !error.message.includes("secret-token"));
  assert.equal(attempts, 5);
});
test("Android automatic authentication never asks the native bridge to show a window", async () => {
  const previous = global.NativeRuntime;
  global.NativeRuntime = { call() { assert.fail("Authentication window must stay hidden"); } };
  try { await BrowserWindow.prototype.show.call({id:"fixture"}); }
  finally { global.NativeRuntime = previous; }
});
test("UI and native homework deadlines leave room for all five bounded attempts", () => {
  const entry = fs.readFileSync(require.resolve("../android/runtime/entry.cjs"), "utf8");
  const ui = fs.readFileSync(require.resolve("../web/src/App.vue"), "utf8");
  const bridge = fs.readFileSync(require.resolve("../android/runtime/ui-bridge.js"), "utf8");
  assert.match(entry, /route === "\/api\/homework\/sync" \? 330_000/);
  assert.match(ui, /isAndroidRuntime \? 340_000 : 170_000/);
  assert.match(bridge, /route === "\/api\/homework\/sync" \? 350_000/);
  assert.ok(ATTEMPTS * 60000 + (ATTEMPTS - 1) * DELAY_MS < 330000);
});
test("retry success stops immediately including an empty result", async () => {
  let attempts = 0;
  const result = await retryCampus("校园", async () => { if (++attempts < 3) throw Error(); return []; }, undefined, { delay: 0 });
  assert.deepEqual(result, []);
  assert.equal(attempts, 3);
});
test("cancel stops retries and aborts the active attempt", async () => {
  const controller = new AbortController();
  let attempts = 0, attemptSignal;
  await assert.rejects(retryCampus("校园", async (_, signal) => {
    attempts++; attemptSignal = signal; controller.abort(Error("cancelled"));
    return new Promise(() => {});
  }, controller.signal, { delay: 0 }), /cancelled/);
  assert.equal(attempts, 1);
  assert.ok(attemptSignal.aborted);
});
test("each timed-out attempt is aborted before the next one", async () => {
  const signals = [];
  await assert.rejects(retryCampus("校园", async (_, signal) => {
    assert.ok(signals.every(item => item.aborted)); signals.push(signal);
    return new Promise(() => {});
  }, undefined, { delay: 0, timeout: 5 }), /5 次/);
  assert.equal(signals.length, 5);
  assert.ok(signals.every(item => item.aborted));
});
test("snapshots retain prior dates and isolate dormitories, accounts and units", () => {
  let history = [snapshot("2026-09-20", 20), snapshot("2026-09-21", 17)];
  history = saveSnapshot(history, snapshot("2026-09-21", 16));
  assert.equal(history.length, 2);
  const unchanged = saveSnapshot(history, snapshot("2026-09-21", 16));
  assert.equal(unchanged, history);
  history = saveSnapshot(history, snapshot("2026-09-22", 13));
  history.push(snapshot("2026-09-22", 1, { dormitory: "B410" }), snapshot("2026-09-22", 2, { accountKey: "two" }));
  const chart = usageChart(history, "A410", "one", "元", Date.parse("2026-09-22T12:00:00Z"));
  assert.equal(chart.points.length, 7);
  assert.deepEqual(chart.points.slice(-2).map(point => point.usage), [4, 3]);
  assert.equal(hasSnapshotForDate(history, "2026-09-22", "A410", "one", "元"), true);
  assert.equal(hasSnapshotForDate(history, "2026-09-23", "A410", "one"), false);
});
test("missing days and recharges are gaps, not zero or multi-day consumption", () => {
  const chart = usageChart([snapshot("2026-09-17", 20), snapshot("2026-09-19", 12),
    snapshot("2026-09-20", 10), snapshot("2026-09-21", 30), snapshot("2026-09-22", 27)],
  "A410", "one", "元", Date.parse("2026-09-22T12:00:00Z"));
  assert.deepEqual(chart.points.slice(-4).map(point => point.usage), [null, 2, null, 3]);
  assert.equal(chart.segments.length, 2);
  assert.equal(chart.points.at(-1).x, 592);
});
test("China dates normalize query timestamps around midnight", () => {
  assert.equal(chinaDate("2026-09-22T17:00:00Z"), "2026-09-23");
  assert.equal(chinaDate("2026-09-22 23:59:00"), "2026-09-22");
  assert.equal(chinaDate("invalid"), "");
});

test("missing site ID resolves by exact assignment ID, not shared teaching-class name", async () => {
  const resolve = createCourseResolver();
  let courseRequests = 0;
  const request = async (url, init) => {
    if (url.includes("/site/list/")) {
      courseRequests++;
      return { records: [{id:"1",siteName:"课程甲"},{id:"2",siteName:"课程乙"}], total:2 };
    }
    assert.equal(url, "/ykt-site/work/student/list");
    assert.equal(init.method, "POST");
    const body = JSON.parse(init.body);
    return { records: [{id:body.siteId === "1" ? "work-a" : "work-b"}], total:1 };
  };
  const detail = {className:"同一个教学班"};
  assert.deepEqual(await resolve(detail,{activityId:"work-a"},request,{userId:"fixture"}),{name:"课程甲",siteId:"1"});
  assert.deepEqual(await resolve(detail,{activityId:"work-b"},request,{userId:"fixture"}),{name:"课程乙",siteId:"2"});
  assert.equal(courseRequests, 1);
  assert.equal(await resolve(detail,{activityId:"unknown"},request,{userId:"fixture"}),"课程名称未提供");
});

test("course resolver follows pagination and rejects incomplete metadata", async () => {
  const resolve = createCourseResolver();
  const calls=[];
  const request=async (url,init) => {
    if(!init) return {records:[{id:"site",siteName:"课程"}],total:1};
    const page=JSON.parse(init.body).current;
    calls.push(page);
    return {records:[{id:page===1?"first":"wanted"}],total:2};
  };
  assert.equal((await resolve({}, {activityId:"wanted"}, request, {userId:"fixture"})).name, "课程");
  assert.deepEqual(calls,[1,2]);
  await assert.rejects(createCourseResolver()({}, {activityId:"wanted"}, async()=>({records:[],total:2}), {}), /不完整/);
});
