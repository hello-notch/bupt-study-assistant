import type { HomeworkSnapshot, StudyTask } from "./types";

export function isHomeworkSnapshot(value: unknown): value is HomeworkSnapshot {
  if (!value || typeof value !== "object") return false;
  const data = value as HomeworkSnapshot;
  return data.complete === true && /^[a-f0-9]{64}$/.test(data.accountKey)
    && Number.isFinite(Date.parse(data.updatedAt)) && Array.isArray(data.items)
    && new Set(data.items.map(item => item?.sourceId)).size === data.items.length
    && data.items.every(item => item && typeof item.sourceId === "string" && item.sourceId.length > 0
      && typeof item.courseId === "string" && typeof item.course === "string" && item.course.trim()
      && typeof item.title === "string" && item.title.startsWith("[作业][")
      && typeof item.contentHtml === "string" && item.contentHtml.length <= 200_000
      && typeof item.dueAt === "string" && (!item.dueAt || Number.isFinite(Date.parse(item.dueAt)))
      && typeof item.url === "string"
      && item.url.startsWith("https://ucloud.bupt.edu.cn/uclass/course.html#/student/assignmentDetails_fullpage?"));
}

export function reconcileHomework(tasks: StudyTask[], snapshot: HomeworkSnapshot, reminderMinutes: number): StudyTask[] {
  if (!isHomeworkSnapshot(snapshot)) throw new Error("教学云同步数据不完整，已保留现有作业");
  const incoming = new Map(snapshot.items.map(item => [item.sourceId, item]));
  let nextId = Math.max(0, ...tasks.map(task => task.id)) + 1;
  const result = tasks.map(task => {
    if (task.homework?.accountKey !== snapshot.accountKey) return task;
    const item = incoming.get(task.homework.sourceId);
    if (!item) return { ...task, status: "submitted" as const };
    incoming.delete(item.sourceId);
    return { ...task, title: item.title, course: item.course, dueAt: item.dueAt, status: "todo" as const,
      homework: { ...item, accountKey: snapshot.accountKey } };
  });
  for (const item of incoming.values()) result.push({
    id: nextId++, title: item.title, course: item.course, dueAt: item.dueAt,
    reminderMinutes: item.dueAt ? reminderMinutes : null, remindDuringQuiet: false,
    status: "todo", createdAt: snapshot.updatedAt, homework: { ...item, accountKey: snapshot.accountKey },
  });
  return result;
}

export function canDeleteTask(task: StudyTask): boolean {
  return !task.homework || task.status === "submitted";
}

export function sameHomeworkCourse(first: string, second: string): boolean {
  const normalize = (value: string) => value.normalize("NFKC").replace(/\s+/g, "").replace(/[#○◇]+$/u, "");
  return normalize(first) === normalize(second);
}

export function compareTasks(first: StudyTask, second: StudyTask): number {
  return Number(Boolean(first.homework)) - Number(Boolean(second.homework))
    || (first.dueAt || "9999").localeCompare(second.dueAt || "9999") || first.id - second.id;
}
