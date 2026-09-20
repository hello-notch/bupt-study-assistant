import type { Course } from "./types";

export function scheduleLayout(courses: Course[]) {
  const days = courses.some(course => course.weekday >= 6) ? 7 : 5;
  const lastSection = courses.length ? Math.min(14, Math.max(...courses.map(course => course.endSection))) : 14;
  const occupied = Array.from({ length: lastSection }, (_, index) =>
    !courses.length || courses.some(course => course.startSection <= index + 1 && course.endSection >= index + 1));
  return {
    days,
    lastSection,
    occupied,
    // Keep interior gaps identifiable without giving them a full course row.
    rows: ["32px", ...occupied.map(value => value ? "minmax(0, 1fr)" : "18px")].join(" "),
  };
}
