import type { Course } from "./types";

export function scheduleLayout(courses: Course[], android = false) {
  const days = courses.some(course => course.weekday >= 6) ? 7 : 5;
  const lastSection = courses.length ? Math.min(14, Math.max(...courses.map(course => course.endSection))) : 14;
  const occupied = Array.from({ length: lastSection }, (_, index) =>
    !courses.length || courses.some(course => course.startSection <= index + 1 && course.endSection >= index + 1));
  const minimumRows: number[] = occupied.map(value => value ? 32 : 14);
  if (android) {
    // A spanning course shares its readable minimum across its sections.
    for (const course of courses) {
      const start = Math.max(1, course.startSection);
      const end = Math.min(lastSection, course.endSection);
      const minimum = Math.ceil(108 / (end - start + 1));
      for (let section = start; section <= end; section++) {
        minimumRows[section - 1] = Math.max(minimumRows[section - 1]!, minimum);
      }
    }
  }
  return {
    days,
    lastSection,
    occupied,
    // Keep interior gaps identifiable without giving them a full course row.
    // Use small spare-space allowances, not unbounded fractional stretching.
    rows: ["32px", ...occupied.map((value, index) => value
      ? android ? `minmax(${minimumRows[index]}px, ${minimumRows[index]! + 4}px)` : "minmax(0, 1fr)" : "14px")].join(" "),
  };
}
