const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("../web/node_modules/typescript");
const { __test: cloud } = require("../client/ucloud.cjs");

function loadTs(name) {
  const filename = path.resolve(__dirname, `../web/src/${name}.ts`);
  const compiled = new Module(filename, module);
  compiled.filename = filename;
  compiled.paths = Module._nodeModulePaths(path.dirname(filename));
  compiled._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, filename);
  return compiled.exports;
}
const { reconcileHomework, isHomeworkSnapshot, canDeleteTask, compareTasks, sameHomeworkCourse } = loadTs("homework");
const { scheduleLayout } = loadTs("schedule-layout");
const row = { type: 3, activityId: "hw-1", activityName: "练习一", siteId: "course-1", endTime: "2026-09-25 20:00:00" };
const detail = { assignmentTitle: "练习一", assignmentContent: "<p>完成第 1、2 题。</p>", assignmentEndTime: row.endTime, siteId: row.siteId };
const item = cloud.assignmentItem(row, detail, "现代控制理论");
const snapshot = { items: [item], accountKey: "a".repeat(64), complete: true, updatedAt: "2026-09-18T01:00:00.000Z" };
const personal = { id: 1, title: "个人任务", course: "计划", dueAt: "2026-10-01T00:00:00.000Z", status: "todo", reminderMinutes: 60, remindDuringQuiet: false, createdAt: snapshot.updatedAt };
const auth = { token: "fixture-token", userId: "fixture-user", identity: "JS005:test" };
const response = data => new Response(JSON.stringify({ code: 200, data }), { status: 200 });

test("ucloud reads the official iClass cookie prefix only on its own origin", () => {
  const vm = require("node:vm");
  const context = {
    location: { hostname: "ucloud.bupt.edu.cn" },
    document: { cookie: `iClass-token=fixture; iClass-user-info=${encodeURIComponent(JSON.stringify({ id: "123", account: "student" }))}; iClass-identity=JS005%3Atest` },
  };
  const result = vm.runInNewContext(cloud.sessionScript(), context);
  assert.equal(result.token, "fixture");
  assert.equal(result.account, "student");
  assert.equal(result.identity, "JS005:test");
  context.location.hostname = "untrusted.example";
  assert.equal(vm.runInNewContext(cloud.sessionScript(), context), null);
});

test("selected-week layout retains spanning sections, hides empty weekends and trims trailing rows", () => {
  const layout = scheduleLayout([{ weekday: 1, startSection: 3, endSection: 4 }, { weekday: 5, startSection: 9, endSection: 11 }]);
  assert.equal(layout.days, 5);
  assert.equal(layout.lastSection, 11);
  assert.deepEqual(layout.occupied, [false, false, true, true, false, false, false, false, true, true, true]);
  assert.equal(scheduleLayout([{ weekday: 7, startSection: 13, endSection: 14 }]).days, 7);
  assert.equal(scheduleLayout([{ weekday: 6, startSection: 1, endSection: 14 }]).occupied.filter(Boolean).length, 14);
  assert.equal(scheduleLayout([]).lastSection, 14);
  assert.equal(scheduleLayout([]).occupied.filter(Boolean).length, 14);
});

test("official undone envelope must be complete; only assignment type 3 is imported", () => {
  assert.deepEqual(cloud.undoneRows({ undoneNum: 0, undoneList: [] }), []);
  assert.deepEqual(cloud.undoneRows({ undoneNum: 2, undoneList: [row, { type: 5, activityId: "peer-review" }] }), [row]);
  assert.throws(() => cloud.undoneRows({}));
  assert.throws(() => cloud.undoneRows({ undoneNum: 3, undoneList: [row] }));
  assert.throws(() => cloud.undoneRows({ undoneList: [{ type: 3 }] }));
});

test("assignment uses official work detail and China-time deadline without device-zone ambiguity", () => {
  assert.equal(item.title, "[作业][现代控制理论]练习一");
  assert.equal(item.contentHtml, detail.assignmentContent);
  assert.equal(item.dueAt, "2026-09-25T12:00:00.000Z");
  assert.equal(cloud.deadline(""), "");
  assert.throws(() => cloud.deadline("not-a-date"));
  assert.throws(() => cloud.assignmentItem(row, {}, "课程"));
  assert.throws(() => cloud.assignmentItem(row, detail, ""));
});

test("all assignments are fetched, course names resolved and auth headers stay in runtime", async () => {
  const rows = Array.from({ length: 8 }, (_, i) => ({ ...row, activityId: `hw-${i}` }));
  const calls = [];
  const items = await cloud.fetchAssignments(auth, async (url, init) => {
    calls.push(url);
    assert.equal(init.headers["Blade-Auth"], auth.token);
    assert.equal(init.redirect, "error");
    if (url.includes("/student/undone")) return response({ undoneList: rows, undoneNum: 8 });
    if (url.includes("/site/detail")) return response({ siteName: "现代控制理论" });
    return response(detail);
  });
  assert.equal(items.length, 8);
  assert.equal(calls.filter(url => url.includes("/site/detail")).length, 1);
  assert.equal(JSON.stringify(items).includes(auth.token), false);
  assert.ok(calls.some(url => url.includes("/ykt-site/work/detail?assignmentId=")));
});

test("network, authentication, schema and partial-detail failures never yield an empty success", async () => {
  for (const badResponse of [
    new Response("denied", { status: 401 }),
    new Response("<html>login</html>"),
    response({}),
    new Response(JSON.stringify({ code: 500, data: { undoneList: [] } })),
  ]) await assert.rejects(cloud.fetchAssignments(auth, async () => badResponse));
  await assert.rejects(cloud.fetchAssignments(auth, async url =>
    url.includes("/student/undone") ? response({ undoneList: [row] }) : response({ assignmentTitle: "missing content" })));
});

test("cancelling a sync aborts the underlying homework fetch", async () => {
  const controller = new AbortController();
  let networkAborted = false;
  const request = cloud.fetchAssignments(auth, async (_url, { signal }) => new Promise((_, reject) => {
    signal.addEventListener("abort", () => { networkAborted = true; reject(signal.reason); }, { once: true });
  }), controller.signal);
  controller.abort(new Error("test cancellation"));
  await assert.rejects(request, /test cancellation/);
  assert.equal(networkAborted, true);
});

test("reconciliation keeps personal tasks first, only system marks submitted, and can restore reopened homework", () => {
  let tasks = reconcileHomework([personal], snapshot, 60);
  assert.equal(tasks.length, 2);
  assert.equal(tasks[1].status, "todo");
  assert.equal(canDeleteTask(tasks[1]), false);
  assert.equal(tasks.sort(compareTasks)[0].id, personal.id);
  const identity = tasks[1].id;
  tasks = reconcileHomework(tasks, { ...snapshot, items: [] }, 60);
  assert.equal(tasks[1].status, "submitted");
  assert.equal(tasks[0].status, "todo");
  assert.equal(canDeleteTask(tasks[1]), true);
  tasks = reconcileHomework(tasks, snapshot, 60);
  assert.equal(tasks[1].status, "todo");
  assert.equal(tasks[1].id, identity);
  assert.equal(reconcileHomework(tasks, snapshot, 60).length, 2);
});

test("incomplete snapshots cannot mutate state; account isolation and deleted submitted items are preserved", () => {
  const tasks = reconcileHomework([personal], snapshot, 60);
  const before = JSON.stringify(tasks);
  assert.throws(() => reconcileHomework(tasks, { ...snapshot, complete: false }, 60));
  assert.equal(JSON.stringify(tasks), before);
  assert.equal(reconcileHomework(tasks, { ...snapshot, accountKey: "b".repeat(64), items: [] }, 60)[1].status, "todo");
  assert.equal(reconcileHomework([personal], { ...snapshot, items: [] }, 60).length, 1);
  assert.equal(isHomeworkSnapshot({ ...snapshot, items: [item, item] }), false);
  assert.equal(sameHomeworkCourse("现代 控制理论", "现代控制理论"), true);
  assert.equal(sameHomeworkCourse("现代控制理论#", "现代控制理论"), true);
  assert.equal(sameHomeworkCourse("现代控制理论", "控制理论"), false);
});
