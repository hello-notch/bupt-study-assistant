import * as XLSX from "xlsx";
import type { Course } from "./types";

export type ImportedCourse = Omit<Course, "id" | "color" | "reminderMinutes">;
type CourseColumn = keyof ImportedCourse | "sections";

const aliases: Record<CourseColumn, string[]> = {
  name: ["课程名", "课程名称", "课程", "name"],
  teacher: ["教师", "老师", "任课教师", "teacher"],
  location: ["教室", "地点", "上课地点", "location"],
  weekday: ["星期", "周几", "星期几", "weekday"],
  startSection: ["开始节次", "起始节次", "开始节", "start_section", "startsection"],
  endSection: ["结束节次", "终止节次", "结束节", "end_section", "endsection"],
  sections: ["节次", "上课节次", "课程节次", "上课时间", "sections", "section"],
  startTime: [],
  endTime: [],
  weeks: ["周次", "起止周", "教学周", "weeks"],
};

const sectionTimes: Record<number, string> = {
  1: "08:00", 2: "08:50", 3: "09:50", 4: "10:40", 5: "11:30",
  6: "13:30", 7: "14:20", 8: "15:20", 9: "16:10", 10: "17:00",
  11: "18:30", 12: "19:20", 13: "20:10", 14: "21:00",
};

export function courseTimes(startSection: number, endSection: number): { startTime: string; endTime: string } {
  const startTime = sectionTimes[startSection] ?? "08:00";
  const endStart = sectionTimes[endSection] ?? startTime;
  const end = new Date(`2000-01-01T${endStart}:00`);
  end.setMinutes(end.getMinutes() + 45);
  const endTime = `${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
  return { startTime, endTime };
}

export async function parseCourseFile(file: File): Promise<ImportedCourse[]> {
  const buffer = await file.arrayBuffer();
  const workbook = file.name.toLowerCase().endsWith(".csv")
    ? XLSX.read(new TextDecoder("utf-8").decode(buffer), { type: "string", raw: true })
    : XLSX.read(buffer, { type: "array", cellDates: false });
  const firstSheet = workbook.Sheets[workbook.SheetNames[0] ?? ""];
  if (!firstSheet) throw new Error("课表文件中没有工作表");

  const matrix = XLSX.utils.sheet_to_json<unknown[]>(firstSheet, { header: 1, defval: "", raw: false });
  const matrixRows = parseBuptMatrix(matrix);
  if (matrixRows.length) return matrixRows;

  const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(firstSheet, { defval: "", raw: false });
  return parseTabularRows(rows);
}

export function normalizeImportedCourses(rows: Array<Partial<ImportedCourse>>): ImportedCourse[] {
  return rows.map((row, index) => normalizeCourse(row, index));
}

/** Remove common HTML entities that occasionally appear in exported course names. */
export function cleanImportedCourseName(value: string): string {
  return value
    .replace(/&(?:nbsp|ensp|emsp|thinsp|zwnj|zwj|amp|lt|gt|quot|apos|#\d+|#x[\da-f]+);?/gi, " ")
    .replace(/\\u00a0/gi, " ")
    .replace(/\u00a0/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parseTabularRows(rows: Record<string, unknown>[]): ImportedCourse[] {
  if (!rows.length) throw new Error("课表文件为空");
  const headers = Object.keys(rows[0]!);
  const mapping = new Map<CourseColumn, string>();
  for (const header of headers) {
    const normalized = header.trim().toLowerCase();
    for (const [target, choices] of Object.entries(aliases) as Array<[CourseColumn, string[]]>) {
      if (choices.some((choice) => choice.toLowerCase() === normalized)) mapping.set(target, header);
    }
  }
  for (const required of ["name", "weekday", "weeks"] as const) {
    if (!mapping.has(required)) throw new Error(`无法识别“${aliases[required][0]}”列`);
  }
  if (!mapping.has("sections") && !mapping.has("startSection")) {
    throw new Error("无法识别“节次”或“开始节次”列");
  }
  return rows
    .filter((row) => String(row[mapping.get("name") ?? ""] ?? "").trim())
    .map((row, index) => {
      const combinedValue = row[mapping.get("sections") ?? mapping.get("startSection") ?? ""];
      const [startSection, inferredEndSection] = parseSectionRange(combinedValue);
      const endValue = mapping.has("endSection") ? row[mapping.get("endSection")!] : undefined;
      const [, explicitEndSection] = parseSectionRange(endValue, inferredEndSection);
      return normalizeCourse({
        name: String(row[mapping.get("name") ?? ""] ?? ""),
        teacher: String(row[mapping.get("teacher") ?? ""] ?? ""),
        location: String(row[mapping.get("location") ?? ""] ?? ""),
        weekday: parseWeekday(row[mapping.get("weekday") ?? ""]),
        startSection,
        endSection: endValue === undefined || String(endValue).trim() === "" ? inferredEndSection : explicitEndSection,
        weeks: String(row[mapping.get("weeks") ?? ""] ?? ""),
      }, index);
    });
}

function parseBuptMatrix(matrix: unknown[][]): ImportedCourse[] {
  let headerIndex = -1;
  const weekdayColumns = new Map<number, number>();
  for (let rowIndex = 0; rowIndex < matrix.length; rowIndex += 1) {
    const candidates = new Map<number, number>();
    matrix[rowIndex]!.forEach((value, column) => {
      const text = String(value ?? "").trim();
      if (/^(?:星期|周)[一二三四五六日天]$/.test(text)) candidates.set(column, parseWeekday(text));
    });
    if (candidates.size >= 5) {
      headerIndex = rowIndex;
      candidates.forEach((weekday, column) => weekdayColumns.set(column, weekday));
      break;
    }
  }
  if (headerIndex < 0) return [];

  const result: ImportedCourse[] = [];
  const seen = new Set<string>();
  const pattern = /([^\n]+)\n([^\n]+)\n(\d+(?:[-~～,，]\d+)*)\[周\]\n([^\n]*)\n\[(\d+(?:-\d+)*)\]节/g;
  for (const row of matrix.slice(headerIndex + 1)) {
    weekdayColumns.forEach((weekday, column) => {
      const text = String(row[column] ?? "").replace(/\r\n?/g, "\n").trim();
      for (const match of text.matchAll(pattern)) {
        const sections = match[5]!.split("-").map(Number);
        const item = normalizeCourse({
          name: match[1], teacher: match[2], weeks: match[3], location: match[4], weekday,
          startSection: Math.min(...sections), endSection: Math.max(...sections),
        }, result.length);
        const key = `${item.name}|${item.teacher}|${item.weeks}|${item.location}|${item.weekday}|${item.startSection}|${item.endSection}`;
        if (!seen.has(key)) {
          seen.add(key);
          result.push(item);
        }
      }
    });
  }
  if (!result.length) throw new Error("识别到了教务课表布局，但没有解析出课程，请使用教务系统直接下载的原文件");
  return result;
}

function normalizeCourse(row: Partial<ImportedCourse>, index: number): ImportedCourse {
  const name = cleanImportedCourseName(String(row.name ?? ""));
  const weekday = parseWeekday(row.weekday);
  const startSection = Number(row.startSection);
  const endSection = Number(row.endSection);
  if (!name) throw new Error(`第 ${index + 2} 行课程名为空`);
  if (!Number.isInteger(startSection) || !Number.isInteger(endSection) || startSection < 1 || endSection < startSection || endSection > 20) {
    throw new Error(`第 ${index + 2} 行节次无效`);
  }
  let weeks: string;
  try {
    weeks = normalizeWeeks(String(row.weeks ?? ""));
  } catch {
    throw new Error(`第 ${index + 2} 行周次格式无效`);
  }
  return {
    name,
    teacher: String(row.teacher ?? "").trim() || "未填写",
    location: String(row.location ?? "").trim() || "待定",
    weekday,
    startSection,
    endSection,
    ...courseTimes(startSection, endSection),
    weeks,
  };
}

/** Normalize inputs such as "1，2，3" to the compact range "1-3". */
export function normalizeWeeks(value: string): string {
  const text = value.trim().replace(/周/g, "").replace(/[~～—–至]/g, "-").replace(/，/g, ",").replace(/\s+/g, "");
  if (!text || !/^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$/.test(text)) throw new Error("周次格式无效");
  const ranges = text.split(",").map((part) => {
    const [startText, endText] = part.split("-");
    const start = Number(startText);
    const end = Number(endText ?? startText);
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start) throw new Error("周次格式无效");
    return [start, end] as const;
  }).sort((left, right) => left[0] - right[0] || left[1] - right[1]);
  const merged: Array<[number, number]> = [];
  for (const [start, end] of ranges) {
    const previous = merged.at(-1);
    if (previous && start <= previous[1] + 1) previous[1] = Math.max(previous[1], end);
    else merged.push([start, end]);
  }
  return merged.map(([start, end]) => start === end ? String(start) : `${start}-${end}`).join(",");
}

function parseWeekday(value: unknown): number {
  if (typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= 7) return value;
  const text = String(value ?? "").trim().replace(/星期|周/g, "");
  const names: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 7, 天: 7 };
  const result = names[text] ?? Number(text);
  if (!Number.isInteger(result) || result < 1 || result > 7) throw new Error(`无法识别星期“${String(value)}”`);
  return result;
}

function parseSectionRange(value: unknown, fallback = Number.NaN): [number, number] {
  const sections = String(value ?? "")
    .replace(/[~～—–至]/g, "-")
    .match(/\d+/g)
    ?.map(Number) ?? [];
  if (!sections.length) return [fallback, fallback];
  return [Math.min(...sections), Math.max(...sections)];
}
