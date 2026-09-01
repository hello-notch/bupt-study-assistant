export type PageId = "today" | "tasks" | "courses" | "campus" | "electricity" | "assistant" | "notifications" | "settings";
export type TaskStatus = "todo" | "done";
export type CampusKind = "notice" | "activity";

export interface StudyTask {
  id: number;
  title: string;
  course: string;
  dueAt: string;
  reminderMinutes: number | null;
  remindDuringQuiet: boolean;
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
  color: "blue" | "violet" | "green" | "orange" | "rose" | "cyan" | "indigo" | "teal";
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

export interface ElectricityResult {
  dormitory: string;
  balance: number;
  unit: "元" | "度";
  updatedAt: string;
  queriedAt: string;
  sourceUrl: string;
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
  attachments?: AssistantAttachment[];
  action?: AssistantAction;
}

export interface AssistantToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface AssistantAttachment {
  id: string;
  name: string;
  mimeType: "image/png" | "image/jpeg" | "image/webp";
  size: number;
  dataUrl: string;
}

export interface AssistantConversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  thinkingEnabled: boolean;
  messages: AssistantMessage[];
}

export interface Preferences {
  theme: "system" | "light" | "dark";
  courseReminder: number;
  defaultTaskReminder: number;
  semesterStart: string;
  quietStart: string;
  quietEnd: string;
  browserNotifications: boolean;
  memoryEnabled: boolean;
  analyticsEnabled: boolean;
}
