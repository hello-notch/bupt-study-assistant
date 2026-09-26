const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("../web/node_modules/typescript");
const filename = path.resolve(__dirname, "../web/src/android-tasks.ts");
const compiled = new Module(filename, module);
compiled._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, filename);
const { activityConflict, campusTimestamp, registrationAlarm, taskAlarm, taskReminderTarget } = compiled.exports;
const vm = require("node:vm");
const androidCloud = require("../android/runtime/ucloud.cjs").__test;
const cloud = require("../client/ucloud.cjs").__test;
const time = minute => Date.parse("2099-09-22T00:00:00Z") + minute * 60000;
const activity = (start, end) => ({ eventTime: new Date(time(start)).toISOString(), eventEndTime: new Date(time(end)).toISOString() });

test("activity overlaps are red, with direct conflicts taking priority over buffer conflicts", () => {
  assert.equal(activityConflict(activity(20, 40), [{ start: time(30), end: time(50) }]), "direct");
  assert.equal(activityConflict(activity(20, 40), [{ start: time(0), end: time(10) }, { start: time(30), end: time(50) }]), "direct");
});
test("both intervals expand by ten minutes, with open end boundaries", () => {
  for (const gap of [0, 1, 10, 19]) {
    assert.equal(activityConflict(activity(30, 60), [{ start: time(60 + gap), end: time(100) }]), "buffer");
    assert.equal(activityConflict(activity(60 + gap, 100), [{ start: time(30), end: time(60) }]), "buffer");
  }
  assert.equal(activityConflict(activity(30, 60), [{ start: time(80), end: time(100) }]), "");
});
test("invalid activity times never produce invented conflicts", () => {
  assert.equal(activityConflict({}, [{ start: time(0), end: time(100) }]), "");
  assert.equal(activityConflict(activity(40, 30), [{ start: time(0), end: time(100) }]), "");
  assert.equal(activityConflict(activity(30, 40), [{ start: NaN, end: time(100) }]), "");
});
test("campus timestamps use China time and support cross-midnight conflicts", () => {
  assert.equal(campusTimestamp("2026-09-22 08:00:00"), Date.parse("2026-09-22T00:00:00Z"));
  assert.equal(activityConflict({ eventTime: "2099-09-22 23:50", eventEndTime: "2099-09-23 00:20" },
    [{ start: campusTimestamp("2099-09-23 00:10"), end: campusTimestamp("2099-09-23 01:00") }]), "direct");
});
test("schedule reminders target start, old tasks and homework target deadline", () => {
  assert.equal(taskReminderTarget({ dueAt: "end" }), "end");
  assert.equal(taskReminderTarget({ kind: "todo", dueAt: "end", startAt: "start" }), "end");
  assert.equal(taskReminderTarget({ kind: "schedule", dueAt: "end", startAt: "start" }), "start");
  assert.equal(taskReminderTarget({ kind: "schedule", dueAt: "end" }), "");
});
test("tasks already inside their reminder window catch up once using a stable alarm ID", () => {
  const task = { id: 1, kind: "schedule", startAt: new Date(time(30)).toISOString(), dueAt: new Date(time(90)).toISOString(), status: "todo", reminderMinutes: 60 };
  const first = taskAlarm(task, time(0)), second = taskAlarm(task, time(1));
  assert.equal(first.at, time(0) + 1000);
  assert.equal(first.id, second.id);
  assert.equal(taskAlarm(task, time(31)), null);
  assert.equal(taskAlarm({ ...task, status: "done" }, time(0)), null);
  assert.equal(taskAlarm({ ...task, reminderMinutes: null }, time(0)), null);
});
test("registration alerts reschedule by setting, reject missing and expired times", () => {
  const reminder = { activityId: "123", title: "activity", registrationStartTime: new Date(time(60)).toISOString() };
  assert.equal(registrationAlarm(reminder, 5, time(0)).at, time(55));
  assert.equal(registrationAlarm(reminder, 10, time(0)).at, time(50));
  assert.equal(registrationAlarm(reminder, 0, time(0)).at, time(60));
  assert.equal(registrationAlarm(reminder, 5, time(56)), null);
  assert.equal(registrationAlarm({ ...reminder, registrationStartTime: "" }, 5, time(0)), null);
  for (const minutes of [-1, 10081, NaN, 1.5]) assert.equal(registrationAlarm(reminder, minutes, time(0)), null);
});

function readSession(cookie, hostname = "ucloud.bupt.edu.cn") {
  return vm.runInNewContext(androidCloud.sessionScript(), {
    location: { hostname }, document: { cookie }, atob, TextDecoder, Uint8Array,
  });
}
test("Android uCloud reads JWT identity when user-info is missing or malformed", () => {
  const token = `header.${Buffer.from(JSON.stringify({ user_id: "user-123", account: "student", real_name: "测试" })).toString("base64url")}.signature`;
  for (const extra of ["", "; iClass-user-info=broken", "; iClass-user-info=null"]) {
    const session = readSession(`iClass-token=${token}${extra}`);
    assert.equal(session.userId, "user-123");
    assert.equal(session.account, "student");
  }
  assert.equal(readSession(`iClass-token=${token}`, "other.bupt.edu.cn"), null);
  assert.equal(readSession("iClass-token=broken"), null);
});
test("Android uCloud retains legacy session and identity cookie support", () => {
  const session = readSession(`iClass-token=test; iClass-user-info=${encodeURIComponent(JSON.stringify({ id: "123", account: "student" }))}; iClass-identity=JS005%3Atest`);
  assert.equal(session.userId, "123");
  assert.equal(session.identity, "JS005:test");
});
test("Android imports genuine assignments with unavailable site ID without requesting a nonexistent course", async () => {
  const requested = [];
  const items = await cloud.fetchAssignments({ userId: "student", token: "fixture" }, async url => {
    requested.push(new URL(url).pathname);
    const data = url.includes("/undone?")
      ? { undoneNum: 1, undoneList: [{ type: 3, activityId: "work-1", activityName: "Work", siteId: -1, siteName: "" }] }
      : { assignmentTitle: "Work", assignmentContent: "<p>Real work</p>", assignmentEndTime: "2099-09-22 20:00", className: "Class A" };
    return new Response(JSON.stringify({ code: 200, data }));
  }, undefined, androidCloud.courseNameFallback);
  assert.equal(items.length, 1);
  assert.equal(items[0].course, "课程名称未提供");
  assert.equal(items[0].dueAt, "2099-09-22T12:00:00.000Z");
  assert.deepEqual(requested, ["/ykt-site/site/student/undone", "/ykt-site/work/detail"]);
  assert.equal(androidCloud.courseNameFallback({}), "课程名称未提供");
});
