export type PageId = "today" | "tasks" | "courses" | "campus" | "assistant" | "notifications" | "settings";
export type TaskStatus = "todo" | "done";
export type CampusKind = "notice" | "activity";

export interface StudyTask {
  id: number;
  title: string;
  course: string;
  dueAt: string;
  reminderMinutes: number | null;
  status: TaskStatus;
  createdAt: string;
}

export interface Course {
  id: number;
  name: string;
  teacher: string;
  location: string;
  weekday: number;
  startSection: number;
  endSection: number;
  startTime: string;
  endTime: string;
  weeks: string;
  reminderMinutes: number;
  color: "blue" | "violet" | "green" | "orange";
}

export interface CampusItem {
  id: string;
  url: string;
  kind: CampusKind;
  category: string;
  title: string;
  summary: string;
  source: string;
  publishedAt: string;
  campus?: string;
  eventTime?: string;
  subscribed: boolean;
  read: boolean;
}

export interface AppNotification {
  id: number;
  title: string;
  body: string;
  createdAt: string;
  type: "task" | "course" | "campus";
  read: boolean;
}

export interface AssistantAction {
  type: "create-task" | "navigate";
  label: string;
  payload: Record<string, string | number>;
  completed?: boolean;
}

export interface AssistantMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  action?: AssistantAction;
}

export interface Preferences {
  theme: "system" | "light" | "dark";
  courseReminder: number;
  defaultTaskReminder: number;
  quietStart: string;
  quietEnd: string;
  browserNotifications: boolean;
  memoryEnabled: boolean;
  analyticsEnabled: boolean;
}
