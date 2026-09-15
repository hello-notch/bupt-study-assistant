const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const test = require("node:test");
const ts = require("../web/node_modules/typescript");
const XLSX = require("../web/node_modules/xlsx");
const { __test } = require("../client/local-runtime.cjs");

const filename = path.resolve(__dirname, "../web/src/course-import.ts");
const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = Module._nodeModulePaths(path.dirname(filename));
compiled._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, filename);
const { parseCourseFile, normalizeImportedCourses, isSameCourseSession } = compiled.exports;

async function parseMatrix(matrix) {
  const workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet(matrix), "Schedule");
  return parseCourseFile(new File([XLSX.write(workbook, { type: "buffer", bookType: "biff8" })], "schedule.xls"));
}

const header = ["", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"];
const cell = "\n工程管理概论\n教师甲\n3-10[周]\n教室甲\n[06-07]节\n工程管理概论\n教师乙\n11-18[周]\n教室甲\n[06-07]节";

test("XLS repeated cells retain both teaching periods without duplicate sessions", async () => {
  const rows = await parseMatrix([header, ["6", cell], ["7", cell]]);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map(({ name, teacher, weeks, startSection, endSection }) =>
    ({ name, teacher, weeks, startSection, endSection })), [
    { name: "工程管理概论", teacher: "教师甲", weeks: "3-10", startSection: 6, endSection: 7 },
    { name: "工程管理概论", teacher: "教师乙", weeks: "11-18", startSection: 6, endSection: 7 },
  ]);
  assert.equal(isSameCourseSession(rows[0], rows[1]), false);
  assert.equal(isSameCourseSession(rows[0], { ...rows[0], weeks: "3,4,5,6,7,8,9,10" }), true);
  assert.equal(isSameCourseSession(rows[0], { ...rows[0], teacher: "教师丙" }), false);
  assert.equal(isSameCourseSession(rows[0], { ...rows[0], location: "教室乙" }), false);
});

test("multiline course names do not become only the class number", async () => {
  const rows = await parseMatrix([header, ["3", "\n太极拳\n(165)\n教师甲\n3-18[周]\n体育场\n[03-04]节"]]);
  assert.equal(rows[0].name, "太极拳 (165)");
});

test("online and file imports use identical session identity for split semesters", async () => {
  const empty = "<td><div class=\"kbcontent\"> </div></td>";
  const onlineCell = "<td><div class=\"kbcontent\">工程管理概论<br>教师甲<br>3-10(周)[06-07节]<br>教室甲<br>工程管理概论<br>教师乙<br>11-18(周)[06-07节]<br>教室甲</div></td>";
  const html = `<table>${Array.from({ length: 7 }, (_, i) =>
    `<tr><td>${i + 1}</td>${i >= 5 ? onlineCell : empty}${empty.repeat(6)}</tr>`).join("")}</table>`;
  const online = normalizeImportedCourses(__test.parsePersonalSchedule(html));
  const file = await parseMatrix([header, ["6", cell], ["7", cell]]);
  assert.deepEqual(online, file);
  const saved = [];
  for (const item of [...file, ...online]) {
    const existing = saved.find((course) => isSameCourseSession(course, item));
    if (existing) Object.assign(existing, item);
    else saved.push({ ...item });
  }
  assert.equal(saved.length, 2);
});
