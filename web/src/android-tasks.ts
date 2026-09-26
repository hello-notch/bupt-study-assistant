import type { CampusItem, RegistrationReminder, StudyTask } from "./types";

export function campusTimestamp(value?: string): number {
  if (!value) return NaN;
  const text = value.trim().replace(" ", "T");
  return Date.parse(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(text) ? `${text}+08:00` : text);
}

export interface TimeInterval { start: number; end: number }
export type TimeConflict = "direct" | "buffer" | "";

export function activityConflict(item: CampusItem, intervals: TimeInterval[]): TimeConflict {
  const start = campusTimestamp(item.eventTime);
  const end = campusTimestamp(item.eventEndTime);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return "";
  let result: TimeConflict = "";
  for (const interval of intervals) {
    if (!Number.isFinite(interval.start) || !Number.isFinite(interval.end) || interval.end <= interval.start) continue;
    if (start < interval.end && end > interval.start) return "direct";
    // Both intervals receive ten minutes before and after, so gaps under 20 minutes conflict.
    const buffer = 10 * 60_000;
    if (start - buffer < interval.end + buffer && end + buffer > interval.start - buffer) result = "buffer";
  }
  return result;
}

export function taskReminderTarget(task: StudyTask): string {
  return task.kind === "schedule" ? task.startAt || "" : task.dueAt;
}

export function taskAlarm(task: StudyTask, now: number) {
  const target = Date.parse(taskReminderTarget(task));
  const minutes = task.reminderMinutes;
  if (task.status !== "todo" || minutes == null || !Number.isInteger(minutes) || minutes < 0 || minutes > 10080 || !Number.isFinite(target) || target <= now) return null;
  const requestedAt = target - minutes * 60_000;
  // The native receiver deduplicates this stable ID even when delivery is brought forward to now.
  return { id: `task:${task.id}:${task.createdAt || ""}:${requestedAt}`, at: Math.max(requestedAt, now + 1000) };
}

export function registrationAlarm(reminder: RegistrationReminder, minutes: number, now: number) {
  const start = campusTimestamp(reminder.registrationStartTime);
  const at = start - minutes * 60_000;
  if (!Number.isInteger(minutes) || minutes < 0 || minutes > 10080 || !Number.isFinite(at) || at < now) return null;
  return { id: `registration:${reminder.activityId}:${at}`, at, title: "第二课堂报名提醒",
    body: `${reminder.title}（报名即将开始）` };
}
