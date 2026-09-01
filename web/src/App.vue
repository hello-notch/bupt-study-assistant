<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import "katex/dist/katex.min.css";
import IconGlyph from "./components/IconGlyph.vue";
import { renderAssistantContent } from "./assistant-markdown";
import { courseTimes, normalizeImportedCourses, normalizeWeeks, parseCourseFile, type ImportedCourse } from "./course-import";
import type {
  AssistantAttachment,
  AssistantConversation,
  AssistantMessage,
  AssistantToolCall,
  AppNotification,
  CampusItem,
  Course,
  ElectricityResult,
  PageId,
  Preferences,
  StudyTask,
} from "./types";

type ReminderUnit = "minutes" | "hours" | "days";
type ImportStrategy = "replace" | "merge";
interface AssistantRuntimeInfo {
  provider: string;
  model: string;
  thinkingSupported?: boolean;
  thinkingEnabled?: boolean;
  webSearchEnabled?: boolean;
  allowedFileTypes?: string[];
}
interface CampusSourceStatus {
  source: "portal" | "activity";
  label: string;
  mode: "online" | "cache" | "error";
  message: string;
  itemCount: number;
}
interface WelcomeOrb {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  hue: number;
}
interface AssistantToolResponse {
  reply?: string;
  toolCalls?: AssistantToolCall[];
  error?: string;
}
interface AssistantToolResult {
  success: boolean;
  [key: string]: unknown;
}

const assistantTools: Array<Record<string, unknown>> = [
  assistantFunction("course_list", "查看当前课表，可按星期筛选", {
    weekday: { type: ["integer", "null"], minimum: 1, maximum: 7 },
  }, []),
  assistantFunction("course_edit", "编辑当前课表中的一门课程", {
    course_id: { type: "integer", minimum: 1 }, name: { type: "string" }, teacher: { type: "string" },
    location: { type: "string" }, weekday: { type: "integer", minimum: 1, maximum: 7 },
    start_section: { type: "integer", minimum: 1, maximum: 20 }, end_section: { type: "integer", minimum: 1, maximum: 20 },
    weeks: { type: "string" }, reminder_minutes: { type: ["integer", "null"], minimum: 0, maximum: 10080 },
  }, ["course_id"]),
  assistantFunction("course_add", "添加一门课程到当前课表", {
    name: { type: "string" }, teacher: { type: "string" }, location: { type: "string" },
    weekday: { type: "integer", minimum: 1, maximum: 7 }, start_section: { type: "integer", minimum: 1, maximum: 20 },
    end_section: { type: "integer", minimum: 1, maximum: 20 }, weeks: { type: "string" }, reminder_minutes: { type: "integer", minimum: 0, maximum: 10080 },
  }, ["name", "weekday", "start_section", "end_section", "weeks"]),
  assistantFunction("ddl_list", "查看当前未完成或全部 DDL", {
    status: { type: "string", enum: ["todo", "done", "all"] },
  }, []),
  assistantFunction("ddl_show", "查看一条 DDL", { ddl_id: { type: "integer", minimum: 1 } }, ["ddl_id"]),
  assistantFunction("ddl_add", "添加 DDL；deadline 支持 1分钟后、明天15:30 或 ISO 时间，reminder_minutes=0 表示截止时提醒", {
    content: { type: "string" }, deadline: { type: "string" }, reminder_minutes: { type: ["integer", "null"], minimum: 0, maximum: 10080 },
  }, ["content", "deadline"]),
  assistantFunction("ddl_edit", "编辑一条未完成 DDL", {
    ddl_id: { type: "integer", minimum: 1 }, content: { type: "string" }, deadline: { type: "string" },
    reminder_minutes: { type: ["integer", "null"], minimum: 0, maximum: 10080 },
  }, ["ddl_id"]),
  assistantFunction("ddl_remind", "设置一条 DDL 的提醒，0 表示截止时提醒，null 表示关闭", {
    ddl_id: { type: "integer", minimum: 1 }, reminder_minutes: { type: ["integer", "null"], minimum: 0, maximum: 10080 },
  }, ["ddl_id", "reminder_minutes"]),
  assistantFunction("ddl_done", "把一条 DDL 标记为完成", { ddl_id: { type: "integer", minimum: 1 } }, ["ddl_id"]),
  assistantFunction("campus_query", "查看已加载的信息门户通知或第二课堂活动", {
    kind: { type: "string", enum: ["notice", "activity", "all"] }, query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 20 },
  }, []),
  assistantFunction("electricity_query", "查询绑定宿舍或指定宿舍的电费/剩余电量", { dormitory: { type: "string" } }, []),
];

function assistantFunction(name: string, description: string, properties: Record<string, unknown>, required: string[]): Record<string, unknown> {
  return { type: "function", function: { name, description, parameters: { type: "object", properties, required, additionalProperties: false } } };
}

const STORAGE_KEY = "youxueban-state-v7";
const LEGACY_STORAGE_KEYS = ["youxueban-state-v6", "youxueban-state-v5", "youxueban-state-v4", "youxueban-state-v3", "youxueban-state-v2", "youxueban-demo-state-v1"];
const MAX_ASSISTANT_FILE_SIZE = 1_000_000;
const MAX_ASSISTANT_ATTACHMENTS = 2;
const MAX_ACADEMIC_WEEK = 22;
const ASSISTANT_GREETING = "你好，你可以问我学习问题。我可以结合你的课程、DDL、校园通知和电费回答问题，也能按你的要求查看或编辑课程和 DDL。";
const LEGACY_ASSISTANT_GREETING = "你好，我可以结合你的课程、任务与校园信息回答问题，也能帮你规划学习安排。";
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const weekdayOptions = ["一", "二", "三", "四", "五", "六", "日"];
const courseColors: Course["color"][] = ["blue", "violet", "green", "orange", "rose", "cyan", "indigo", "teal"];
const sectionRows = Array.from({ length: 14 }, (_, index) => {
  const section = index + 1;
  const { startTime, endTime } = courseTimes(section, section);
  return { key: section, label: String(section), startTime, endTime };
});
const campusServices = [
  { name: "信息门户", description: "通知、办事与校内服务", url: "http://my.bupt.edu.cn/" },
  { name: "教学云平台", description: "查看作业与课件", url: "https://ucloud.bupt.edu.cn/uclass/#/student/homePage" },
  { name: "教务系统", description: "课表、成绩与教学事务", url: "https://jwgl.bupt.edu.cn/jsxsd/" },
];
const navItems: Array<{ id: PageId; label: string; icon: string }> = [
  { id: "today", label: "今天", icon: "today" },
  { id: "tasks", label: "任务", icon: "tasks" },
  { id: "courses", label: "课程", icon: "courses" },
  { id: "campus", label: "校园", icon: "campus" },
  { id: "electricity", label: "查电费", icon: "electricity" },
  { id: "assistant", label: "助手", icon: "assistant" },
];

const defaultPreferences: Preferences = {
  theme: "system",
  courseReminder: 20,
  defaultTaskReminder: 60,
  semesterStart: mondayOf(new Date()).toISOString().slice(0, 10),
  quietStart: "23:00",
  quietEnd: "07:00",
  browserNotifications: true,
  memoryEnabled: true,
  analyticsEnabled: true,
};

const saved = (() => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
      ?? LEGACY_STORAGE_KEYS.map((key) => localStorage.getItem(key)).find(Boolean)
      ?? "{}";
    return JSON.parse(raw) as Partial<{
      profileName: string;
      profileAvatar: string;
      tasks: StudyTask[];
      courses: Course[];
      campusItems: CampusItem[];
      notifications: AppNotification[];
      preferences: Preferences;
      assistantConversations: AssistantConversation[];
      activeConversationId: string;
      electricityDormitory: string;
      sidebarWidth: number;
    }>;
  } catch {
    return {};
  }
})();

const currentPage = ref<PageId>("today");
const profileName = ref(saved.profileName?.trim() ?? "");
const profileAvatar = ref(isImageDataUrl(saved.profileAvatar) ? saved.profileAvatar : "");
const profileDraftName = ref(profileName.value);
const profileDraftAvatar = ref(profileAvatar.value);
const profileEditError = ref("");
const welcomeName = ref("");
const welcomeError = ref("");
const tasks = ref<StudyTask[]>((saved.tasks ?? []).map((task) => ({ ...task, remindDuringQuiet: task.remindDuringQuiet ?? false })));
const courses = ref<Course[]>(normalizeCourseColors((saved.courses ?? []).map((course) => ({
  ...course,
  ...courseTimes(course.startSection, course.endSection),
}))));
const campusItems = ref<CampusItem[]>((saved.campusItems ?? []).filter(isCampusItemReadable));
const notifications = ref<AppNotification[]>(saved.notifications ?? []);
const preferences = ref<Preferences>({ ...defaultPreferences, ...saved.preferences });
const reminderParts = splitReminder(preferences.value.defaultTaskReminder);
const defaultTaskReminderValue = ref(reminderParts.value);
const defaultTaskReminderUnit = ref<ReminderUnit>(reminderParts.unit);
const toast = ref("");
const taskModalOpen = ref(false);
const courseImportOpen = ref(false);
const importStep = ref(1);
const importMode = ref<"class" | "file">("class");
const importClassId = ref("");
const importFile = ref<File | null>(null);
const importPreview = ref<ImportedCourse[]>([]);
const importSelections = ref<boolean[]>([]);
const importError = ref("");
const importBusy = ref(false);
const importStrategy = ref<ImportStrategy>("replace");
const selectedCourse = ref<Course | null>(null);
const courseAddOpen = ref(false);
const courseEditing = ref(false);
const courseForm = ref<Omit<Course, "id">>(blankCourse());
const pendingCourseSlot = ref<{ weekday: number; startSection: number } | null>(null);
const selectedCampusItem = ref<CampusItem | null>(null);
const taskFilter = ref<"todo" | "all" | "done">("todo");
const taskSearch = ref("");
const campusTab = ref<"notice" | "activity">("notice");
const campusSearch = ref("");
const campusBusy = ref(false);
const campusError = ref("");
const campusUpdatedAt = ref("");
const campusStatuses = ref<CampusSourceStatus[]>([]);
const portalVisibleCount = ref(10);
const campusSummaryBusy = ref(false);
const campusSummaryError = ref("");
const assistantInput = ref("");
const assistantBusy = ref(false);
const assistantToolStatus = ref("");
const assistantMode = ref<"unknown" | "online" | "error">("unknown");
const assistantError = ref("");
const assistantRuntime = ref<AssistantRuntimeInfo | null>(null);
const assistantAttachments = ref<AssistantAttachment[]>([]);
const assistantFileInput = ref<HTMLInputElement | null>(null);
const assistantTextarea = ref<HTMLTextAreaElement | null>(null);
const assistantDeleteConfirmId = ref<string | null>(null);
const deleteConfirmId = ref<number | null>(null);
const courseDeleteConfirming = ref(false);
const taskForm = ref({ title: "", course: "", dueAt: "", reminderMinutes: 60, remindDuringQuiet: false });
const clock = ref(new Date());
const selectedWeek = ref(1);
const suggestionIndex = ref(0);
const resetConfirming = ref(false);
const courseClearConfirming = ref(false);
const electricityDormitory = ref(saved.electricityDormitory?.trim() ?? "");
const electricityDormitoryDraft = ref(electricityDormitory.value);
const electricityResult = ref<ElectricityResult | null>(null);
const electricityBusy = ref(false);
const electricityError = ref("");
const electricityEditing = ref(!electricityDormitory.value);
const sidebarWidth = ref(Math.max(190, Math.min(320, Number(saved.sidebarWidth) || 224)));
let clockTimer: number | undefined;
let reminderTimer: number | undefined;
let resetConfirmTimer: number | undefined;
let courseClearConfirmTimer: number | undefined;
let courseDeleteConfirmTimer: number | undefined;
let assistantDeleteConfirmTimer: number | undefined;
let sidebarResizeCleanup: (() => void) | undefined;
let welcomeAnimationFrame: number | undefined;
let welcomeResizeObserver: ResizeObserver | undefined;
let welcomePreviousTime = 0;
let welcomeBounds = { width: 0, height: 0 };
let reminderAudioContext: AudioContext | undefined;
const welcomeOrbsContainer = ref<HTMLElement | null>(null);
const welcomeOrbs = ref<WelcomeOrb[]>([]);
const assistantConversations = ref<AssistantConversation[]>(saved.assistantConversations?.length
  ? migrateAssistantConversations(saved.assistantConversations)
  : [createAssistantConversation()]);
const activeConversationId = ref(saved.activeConversationId && assistantConversations.value.some((item) => item.id === saved.activeConversationId)
  ? saved.activeConversationId
  : assistantConversations.value[0]!.id);

const todayWeekday = computed(() => clock.value.getDay() || 7);
const dateHeading = computed(() => new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
}).format(clock.value));
const timeHeading = computed(() => new Intl.DateTimeFormat("zh-CN", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
}).format(clock.value));
const greeting = computed(() => {
  const hour = clock.value.getHours();
  return hour < 6 ? "夜深了" : hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
});
const profileInitial = computed(() => profileName.value.trim().slice(0, 1) || "邮");
const unreadCount = computed(() => notifications.value.filter((item) => !item.read).length);
const todoTasks = computed(() => tasks.value.filter((task) => task.status === "todo").sort((a, b) => a.dueAt.localeCompare(b.dueAt)));
const currentAcademicWeek = computed(() => weekNumberFor(clock.value));
const weekStart = computed(() => addDays(semesterStartDate(), (selectedWeek.value - 1) * 7));
const weekDates = computed(() => weekdays.map((label, index) => ({ label, date: addDays(weekStart.value, index) })));
const visibleCourses = computed(() => courses.value
  .filter((course) => courseOccursInWeek(course, selectedWeek.value))
  .sort((a, b) => a.weekday - b.weekday || a.startSection - b.startSection));
const todayCourses = computed(() => courses.value
  .filter((course) => course.weekday === todayWeekday.value && courseOccursInWeek(course, currentAcademicWeek.value))
  .sort((a, b) => a.startSection - b.startSection));
const currentCourse = computed(() => {
  const minutes = clock.value.getHours() * 60 + clock.value.getMinutes();
  return todayCourses.value.find((course) => timeToMinutes(course.startTime) <= minutes && minutes < timeToMinutes(course.endTime)) ?? null;
});
const upcomingCourse = computed(() => {
  const minutes = clock.value.getHours() * 60 + clock.value.getMinutes();
  return todayCourses.value.find((course) => timeToMinutes(course.startTime) > minutes) ?? null;
});
const nextCourse = computed(() => currentCourse.value ?? upcomingCourse.value);
const nextCourseState = computed(() => currentCourse.value ? "正在上课" : upcomingCourse.value ? "下一节课" : "今日课程已结束");
const activeConversation = computed(() => assistantConversations.value.find((item) => item.id === activeConversationId.value) ?? assistantConversations.value[0]!);
const assistantMessages = computed(() => activeConversation.value.messages);
const assistantThinkingEnabled = computed({
  get: () => activeConversation.value.thinkingEnabled,
  set: (enabled: boolean) => {
    activeConversation.value.thinkingEnabled = enabled;
    activeConversation.value.updatedAt = new Date().toISOString();
  },
});
const assistantModelLabel = computed(() => assistantRuntime.value?.model === "deepseek-v4-flash-vision-exp"
  ? "DeepSeek-V4-Flash-Vision-Exp"
  : assistantRuntime.value?.model ?? "");
const filteredTasks = computed(() => {
  const query = taskSearch.value.trim().toLowerCase();
  return tasks.value
    .filter((task) => taskFilter.value === "all" || task.status === taskFilter.value)
    .filter((task) => !query || `${task.title} ${task.course}`.toLowerCase().includes(query))
    .sort((a, b) => a.dueAt.localeCompare(b.dueAt));
});
const filteredCampusItems = computed(() => {
  const query = campusSearch.value.trim().toLowerCase();
  const matches = campusItems.value
    .filter((item) => item.kind === campusTab.value)
    .filter((item) => !query || `${item.title} ${item.summary} ${item.category}`.toLowerCase().includes(query));
  return campusTab.value === "notice" ? matches.slice(0, portalVisibleCount.value) : matches;
});
const portalItemCount = computed(() => campusItems.value.filter((item) => item.kind === "notice").length);
const canLoadMorePortalItems = computed(() => portalVisibleCount.value < Math.min(50, portalItemCount.value));
const activityIsEmptyOnline = computed(() => campusTab.value === "activity"
  && !campusSearch.value.trim()
  && campusStatuses.value.some((status) => status.source === "activity" && status.mode === "online" && status.itemCount === 0));
const activeConversationIsBlank = computed(() => isAssistantConversationBlank(activeConversation.value));
const studySuggestions = computed(() => {
  if (!preferences.value.analyticsEnabled) {
    return [
      "可以选一项当下最想推进的事情，专注 20 分钟后再决定下一步。",
      "如果有些疲惫，先休息十分钟，再从一个足够小的步骤开始。",
      "整理一下手边资料，为下一次学习减少启动成本。",
    ];
  }
  const suggestions: string[] = [];
  const nearest = todoTasks.value[0];
  if (nearest) suggestions.push(`先处理最临近的“${nearest.title}”，用 25 分钟完成一个清晰的小步骤。`);
  if (nextCourse.value) suggestions.push(`下一节是“${nextCourse.value.name}”，可以先用 15 分钟回顾上次笔记并列出两个问题。`);
  if (todoTasks.value.length > 1) suggestions.push(`从 ${todoTasks.value.length} 项待办里选一项预计 30 分钟内能推进的任务，完成后再重新排序。`);
  suggestions.push("暂时没有紧急事项，可以整理课程资料、回顾今天的笔记，或者休息十分钟。", "选一门本周课程，用 20 分钟建立一页知识框架，再标出最不熟悉的部分。", "清理一次下载目录和课程文件夹，让下一次开始学习时少一点阻力。");
  return suggestions;
});
const currentSuggestion = computed(() => studySuggestions.value[suggestionIndex.value % studySuggestions.value.length]);

watch([profileName, profileAvatar, tasks, courses, campusItems, notifications, preferences, assistantConversations, activeConversationId, electricityDormitory, sidebarWidth], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      profileName: profileName.value,
      profileAvatar: profileAvatar.value,
      tasks: tasks.value,
      courses: courses.value,
      campusItems: campusItems.value,
      notifications: notifications.value,
      preferences: preferences.value,
      assistantConversations: assistantConversations.value,
      activeConversationId: activeConversationId.value,
      electricityDormitory: electricityDormitory.value,
      sidebarWidth: sidebarWidth.value,
    }));
  } catch {
    showToast("对话中的图片较多，浏览器存储空间不足");
  }
}, { deep: true });

watch([defaultTaskReminderValue, defaultTaskReminderUnit], () => {
  const factor = defaultTaskReminderUnit.value === "days" ? 1440 : defaultTaskReminderUnit.value === "hours" ? 60 : 1;
  preferences.value.defaultTaskReminder = Math.max(0, Math.min(10080, Number(defaultTaskReminderValue.value) || 0) * factor);
});

watch(() => preferences.value.theme, applyTheme, { immediate: true });

watch(assistantInput, async () => {
  await nextTick();
  resizeAssistantComposer();
});

watch(selectedCourse, () => {
  courseDeleteConfirming.value = false;
  if (courseDeleteConfirmTimer !== undefined) window.clearTimeout(courseDeleteConfirmTimer);
});

watch(profileName, async (name) => {
  if (name) {
    stopWelcomeOrbs();
    return;
  }
  await nextTick();
  startWelcomeOrbs();
});

onMounted(async () => {
  const hash = location.hash.replace("#/", "") as PageId;
  if ([...navItems.map((item) => item.id), "notifications", "settings"].includes(hash)) currentPage.value = hash;
  clockTimer = window.setInterval(() => { clock.value = new Date(); }, 1000);
  reminderTimer = window.setInterval(checkDueReminders, 15_000);
  try {
    const response = await fetch("/api/config");
    const payload = await response.json() as { semesterStart?: string; assistant?: AssistantRuntimeInfo };
    if (response.ok && /^\d{4}-\d{2}-\d{2}$/.test(payload.semesterStart ?? "")) preferences.value.semesterStart = payload.semesterStart!;
    if (response.ok && payload.assistant?.model) assistantRuntime.value = payload.assistant;
  } catch {
    // The editable local semester start remains available when the service is offline.
  }
  selectedWeek.value = Math.max(1, Math.min(MAX_ACADEMIC_WEEK, currentAcademicWeek.value));
  await nextTick();
  if (!profileName.value) startWelcomeOrbs();
  await Promise.all([
    loadCampusData(),
    electricityDormitory.value ? queryElectricity(true) : Promise.resolve(),
  ]);
});

onBeforeUnmount(() => {
  if (clockTimer !== undefined) window.clearInterval(clockTimer);
  if (reminderTimer !== undefined) window.clearInterval(reminderTimer);
  if (resetConfirmTimer !== undefined) window.clearTimeout(resetConfirmTimer);
  if (courseClearConfirmTimer !== undefined) window.clearTimeout(courseClearConfirmTimer);
  if (courseDeleteConfirmTimer !== undefined) window.clearTimeout(courseDeleteConfirmTimer);
  if (assistantDeleteConfirmTimer !== undefined) window.clearTimeout(assistantDeleteConfirmTimer);
  sidebarResizeCleanup?.();
  stopWelcomeOrbs();
});

function applyTheme(): void {
  const theme = preferences.value.theme;
  document.documentElement.dataset.theme = theme === "system" ? "" : theme;
}

function blankCourse(): Omit<Course, "id"> {
  return { name: "", teacher: "", location: "", weekday: 1, startSection: 1, endSection: 2, startTime: "08:00", endTime: "09:35", weeks: "1-16", reminderMinutes: 20, color: "blue" };
}

function normalizeCourseColors(items: Course[]): Course[] {
  const colorsByName = new Map<string, Course["color"]>();
  const used = new Set<Course["color"]>();
  return items.map((course, index) => {
    const key = course.name.trim();
    const existing = colorsByName.get(key);
    const preferred = courseColors.includes(course.color) && !used.has(course.color) ? course.color : undefined;
    const color = existing ?? preferred ?? courseColors.find((candidate) => !used.has(candidate)) ?? courseColors[index % courseColors.length]!;
    colorsByName.set(key, color);
    used.add(color);
    return { ...course, color };
  });
}

function colorForCourse(name: string, existingCourses: Course[]): Course["color"] {
  const sameCourse = existingCourses.find((course) => course.name.trim() === name.trim());
  if (sameCourse) return sameCourse.color;
  const used = new Set(existingCourses.map((course) => course.color));
  return courseColors.find((color) => !used.has(color)) ?? courseColors[existingCourses.length % courseColors.length]!;
}

function mondayOf(date: Date): Date {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  result.setDate(result.getDate() - ((result.getDay() || 7) - 1));
  return result;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function semesterStartDate(): Date {
  const parsed = new Date(`${preferences.value.semesterStart}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? mondayOf(clock.value) : mondayOf(parsed);
}

function weekNumberFor(date: Date): number {
  return Math.max(1, Math.floor((mondayOf(date).getTime() - semesterStartDate().getTime()) / 604800000) + 1);
}

function courseOccursInWeek(course: Course, week: number): boolean {
  const text = course.weeks.replace(/周/g, "").replace(/[~～]/g, "-");
  const oddOnly = /单/.test(text);
  const evenOnly = /双/.test(text);
  if ((oddOnly && week % 2 === 0) || (evenOnly && week % 2 !== 0)) return false;
  const ranges = [...text.matchAll(/(\d+)(?:\s*-\s*(\d+))?/g)];
  if (!ranges.length) return true;
  return ranges.some((match) => week >= Number(match[1]) && week <= Number(match[2] ?? match[1]));
}

function formatWeekDate(date: Date): string {
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function timeToMinutes(value: string): number {
  const [hour, minute] = value.split(":").map(Number);
  return (hour || 0) * 60 + (minute || 0);
}

function splitReminder(minutes: number): { value: number; unit: ReminderUnit } {
  if (minutes > 0 && minutes % 1440 === 0) return { value: minutes / 1440, unit: "days" };
  if (minutes > 0 && minutes % 60 === 0) return { value: minutes / 60, unit: "hours" };
  return { value: minutes, unit: "minutes" };
}

function initialAssistantMessages(): AssistantMessage[] {
  return [{
    id: 1,
    role: "assistant",
    content: ASSISTANT_GREETING,
    createdAt: new Date().toISOString(),
  }];
}

function migrateAssistantConversations(conversations: AssistantConversation[]): AssistantConversation[] {
  return conversations.map((conversation) => ({
    ...conversation,
    messages: conversation.messages.map((message, index) => index === 0 && message.role === "assistant" && message.content === LEGACY_ASSISTANT_GREETING
      ? { ...message, content: ASSISTANT_GREETING }
      : message),
  }));
}

function createAssistantConversation(): AssistantConversation {
  const createdAt = new Date().toISOString();
  return {
    id: `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: "新对话",
    createdAt,
    updatedAt: createdAt,
    thinkingEnabled: false,
    messages: initialAssistantMessages(),
  };
}

function isCampusItemReadable(item: CampusItem): boolean {
  const text = `${item.title} ${item.source} ${item.summary}`;
  return Boolean(item.title.trim()) && !/(?:\uFFFD{2,}|��|锟斤拷|鍖椾含)/.test(text);
}

function navigate(page: PageId): void {
  currentPage.value = page;
  location.hash = `/${page}`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showToast(message: string): void {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = "";
  }, 2600);
}

async function completeWelcome(): Promise<void> {
  const name = welcomeName.value.trim();
  if (!name) {
    welcomeError.value = "请先告诉我该怎么称呼你";
    return;
  }
  profileName.value = name.slice(0, 20);
  profileDraftName.value = profileName.value;
  welcomeError.value = "";
  showToast(`欢迎你，${profileName.value}`);
  if (!campusItems.value.length) await loadCampusData();
}

function saveProfile(): void {
  const name = profileDraftName.value.trim();
  if (!name) {
    profileEditError.value = "昵称不能为空";
    return;
  }
  profileName.value = name.slice(0, 20);
  profileAvatar.value = isImageDataUrl(profileDraftAvatar.value) ? profileDraftAvatar.value : "";
  profileDraftName.value = profileName.value;
  profileDraftAvatar.value = profileAvatar.value;
  profileEditError.value = "";
  showToast("个人资料已保存");
}

async function selectAvatarFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!/^(?:image\/png|image\/jpeg|image\/webp)$/.test(file.type)) {
    profileEditError.value = "请选择 PNG、JPG 或 WebP 图片";
    return;
  }
  if (file.size > 2 * 1024 * 1024) {
    profileEditError.value = "头像文件不能超过 2 MB";
    return;
  }
  try {
    const dataUrl = await fileToDataUrl(file);
    if (!isImageDataUrl(dataUrl)) throw new Error("图片格式无效");
    profileDraftAvatar.value = dataUrl;
    profileEditError.value = "";
  } catch {
    profileEditError.value = "无法读取这张图片，请换一张重试";
  }
}

function clearAvatarDraft(): void {
  profileDraftAvatar.value = "";
  profileEditError.value = "";
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result ?? "")), { once: true });
    reader.addEventListener("error", () => reject(reader.error), { once: true });
    reader.readAsDataURL(file);
  });
}

function isImageDataUrl(value: unknown): value is string {
  return typeof value === "string" && /^data:image\/(?:png|jpeg|webp);base64,/i.test(value);
}

function startWelcomeOrbs(): void {
  const container = welcomeOrbsContainer.value;
  if (!container || profileName.value) return;
  stopWelcomeOrbs();
  const bounds = container.getBoundingClientRect();
  if (bounds.width < 1 || bounds.height < 1) return;
  welcomeBounds = { width: bounds.width, height: bounds.height };
  const diagonal = Math.hypot(bounds.width, bounds.height);
  const count = Math.max(9, Math.min(14, Math.round(bounds.width * bounds.height / 95_000)));
  const baseRadius = Math.max(14, Math.min(38, diagonal / 38));
  const placed: WelcomeOrb[] = [];
  for (let index = 0; index < count; index += 1) {
    const radius = Math.max(13, Math.min(48, baseRadius * (.58 + Math.random() * .76)));
    let x = radius;
    let y = radius;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      x = radius + Math.random() * Math.max(1, bounds.width - radius * 2);
      y = radius + Math.random() * Math.max(1, bounds.height - radius * 2);
      if (placed.every((orb) => Math.hypot(orb.x - x, orb.y - y) > orb.radius + radius + 8)) break;
    }
    const angle = Math.random() * Math.PI * 2;
    const speed = Math.max(45, Math.min(150, diagonal * (.045 + Math.random() * .035)));
    placed.push({ id: index + 1, x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed, radius, hue: 205 + Math.random() * 95 });
  }
  welcomeOrbs.value = placed;
  welcomePreviousTime = performance.now();
  welcomeResizeObserver = new ResizeObserver(() => constrainWelcomeOrbs());
  welcomeResizeObserver.observe(container);
  welcomeAnimationFrame = window.requestAnimationFrame(animateWelcomeOrbs);
}

function stopWelcomeOrbs(): void {
  if (welcomeAnimationFrame !== undefined) window.cancelAnimationFrame(welcomeAnimationFrame);
  welcomeAnimationFrame = undefined;
  welcomeResizeObserver?.disconnect();
  welcomeResizeObserver = undefined;
}

function constrainWelcomeOrbs(): void {
  const container = welcomeOrbsContainer.value;
  if (!container) return;
  const { width, height } = container.getBoundingClientRect();
  if (width < 1 || height < 1) return;
  const widthRatio = welcomeBounds.width ? width / welcomeBounds.width : 1;
  const heightRatio = welcomeBounds.height ? height / welcomeBounds.height : 1;
  const diagonalRatio = welcomeBounds.width && welcomeBounds.height
    ? Math.hypot(width, height) / Math.hypot(welcomeBounds.width, welcomeBounds.height)
    : 1;
  welcomeOrbs.value = welcomeOrbs.value.map((orb) => ({
    ...orb,
    radius: Math.max(13, Math.min(48, orb.radius * Math.max(.78, Math.min(1.22, diagonalRatio)))),
    x: orb.x * widthRatio,
    y: orb.y * heightRatio,
    vx: orb.vx * Math.max(.78, Math.min(1.22, diagonalRatio)),
    vy: orb.vy * Math.max(.78, Math.min(1.22, diagonalRatio)),
  })).map((orb) => ({
    ...orb,
    x: Math.max(orb.radius, Math.min(Math.max(orb.radius, width - orb.radius), orb.x)),
    y: Math.max(orb.radius, Math.min(Math.max(orb.radius, height - orb.radius), orb.y)),
  }));
  welcomeBounds = { width, height };
}

function animateWelcomeOrbs(now: number): void {
  const container = welcomeOrbsContainer.value;
  if (!container || profileName.value) {
    stopWelcomeOrbs();
    return;
  }
  const { width, height } = container.getBoundingClientRect();
  const delta = Math.min(.032, Math.max(.001, (now - welcomePreviousTime) / 1000));
  welcomePreviousTime = now;
  const next = welcomeOrbs.value.map((orb) => ({ ...orb, x: orb.x + orb.vx * delta, y: orb.y + orb.vy * delta }));

  for (const orb of next) {
    if (orb.x - orb.radius < 0) { orb.x = orb.radius; orb.vx = Math.abs(orb.vx); }
    if (orb.x + orb.radius > width) { orb.x = width - orb.radius; orb.vx = -Math.abs(orb.vx); }
    if (orb.y - orb.radius < 0) { orb.y = orb.radius; orb.vy = Math.abs(orb.vy); }
    if (orb.y + orb.radius > height) { orb.y = height - orb.radius; orb.vy = -Math.abs(orb.vy); }
  }

  for (let firstIndex = 0; firstIndex < next.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < next.length; secondIndex += 1) {
      const first = next[firstIndex]!;
      const second = next[secondIndex]!;
      const dx = second.x - first.x;
      const dy = second.y - first.y;
      const distance = Math.hypot(dx, dy) || .001;
      const minimumDistance = first.radius + second.radius;
      if (distance >= minimumDistance) continue;
      const normalX = dx / distance;
      const normalY = dy / distance;
      const overlap = minimumDistance - distance;
      first.x -= normalX * overlap / 2;
      first.y -= normalY * overlap / 2;
      second.x += normalX * overlap / 2;
      second.y += normalY * overlap / 2;
      const relativeSpeed = (second.vx - first.vx) * normalX + (second.vy - first.vy) * normalY;
      if (relativeSpeed >= 0) continue;
      first.hue = (first.hue + 47 + Math.random() * 70) % 360;
      second.hue = (second.hue + 89 + Math.random() * 70) % 360;
      const firstMass = first.radius * first.radius;
      const secondMass = second.radius * second.radius;
      const impulse = -(1.9 * relativeSpeed) / (1 / firstMass + 1 / secondMass);
      first.vx -= impulse * normalX / firstMass;
      first.vy -= impulse * normalY / firstMass;
      second.vx += impulse * normalX / secondMass;
      second.vy += impulse * normalY / secondMass;
    }
  }
  welcomeOrbs.value = next;
  welcomeAnimationFrame = window.requestAnimationFrame(animateWelcomeOrbs);
}

function resetAllPersonalData(): void {
  if (!resetConfirming.value) {
    resetConfirming.value = true;
    if (resetConfirmTimer !== undefined) window.clearTimeout(resetConfirmTimer);
    resetConfirmTimer = window.setTimeout(() => { resetConfirming.value = false; }, 8000);
    return;
  }
  if (resetConfirmTimer !== undefined) window.clearTimeout(resetConfirmTimer);
  if (courseClearConfirmTimer !== undefined) window.clearTimeout(courseClearConfirmTimer);
  [STORAGE_KEY, ...LEGACY_STORAGE_KEYS].forEach((key) => localStorage.removeItem(key));
  profileName.value = "";
  profileAvatar.value = "";
  profileDraftName.value = "";
  profileDraftAvatar.value = "";
  welcomeName.value = "";
  tasks.value = [];
  courses.value = [];
  campusItems.value = [];
  notifications.value = [];
  preferences.value = { ...defaultPreferences };
  const reminder = splitReminder(preferences.value.defaultTaskReminder);
  defaultTaskReminderValue.value = reminder.value;
  defaultTaskReminderUnit.value = reminder.unit;
  const conversation = createAssistantConversation();
  assistantConversations.value = [conversation];
  activeConversationId.value = conversation.id;
  assistantAttachments.value = [];
  assistantDeleteConfirmId.value = null;
  assistantMode.value = "unknown";
  assistantError.value = "";
  electricityDormitory.value = "";
  electricityDormitoryDraft.value = "";
  electricityResult.value = null;
  electricityError.value = "";
  electricityEditing.value = true;
  sidebarWidth.value = 224;
  selectedWeek.value = 1;
  resetConfirming.value = false;
  courseClearConfirming.value = false;
  currentPage.value = "today";
  location.hash = "/today";
  showToast("个人信息已重置");
}

function clearCourses(): void {
  if (!courseClearConfirming.value) {
    courseClearConfirming.value = true;
    if (courseClearConfirmTimer !== undefined) window.clearTimeout(courseClearConfirmTimer);
    courseClearConfirmTimer = window.setTimeout(() => { courseClearConfirming.value = false; }, 7000);
    return;
  }
  if (courseClearConfirmTimer !== undefined) window.clearTimeout(courseClearConfirmTimer);
  courses.value = [];
  selectedCourse.value = null;
  courseEditing.value = false;
  courseClearConfirming.value = false;
  showToast("课表已清空");
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  const sameDay = date.toDateString() === today.toDateString();
  const nextDay = date.toDateString() === tomorrow.toDateString();
  const prefix = sameDay ? "今天" : nextDay ? "明天" : `${date.getMonth() + 1}月${date.getDate()}日`;
  return `${prefix} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function relativeDue(value: string): string {
  const diff = new Date(value).getTime() - Date.now();
  if (diff < 0) return "已逾期";
  if (diff < 60 * 60 * 1000) return `${Math.max(1, Math.ceil(diff / 60000))} 分钟后`;
  if (diff < 24 * 60 * 60 * 1000) return `${Math.ceil(diff / 3600000)} 小时后`;
  return formatDateTime(value);
}

function toDateTimeInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function openTaskModal(prefill = ""): void {
  const due = new Date();
  due.setDate(due.getDate() + 1);
  due.setHours(20, 0, 0, 0);
  taskForm.value = {
    title: prefill,
    course: "",
    dueAt: toDateTimeInput(due),
    reminderMinutes: preferences.value.defaultTaskReminder,
    remindDuringQuiet: false,
  };
  taskModalOpen.value = true;
}

function createTask(): void {
  const title = taskForm.value.title.trim();
  if (!title || !taskForm.value.dueAt) {
    showToast("请填写任务内容和截止时间");
    return;
  }
  tasks.value.push({
    id: Math.max(0, ...tasks.value.map((task) => task.id)) + 1,
    title,
    course: taskForm.value.course.trim() || "个人计划",
    dueAt: new Date(taskForm.value.dueAt).toISOString(),
    reminderMinutes: taskForm.value.reminderMinutes,
    remindDuringQuiet: taskForm.value.remindDuringQuiet,
    status: "todo",
    createdAt: new Date().toISOString(),
  });
  taskModalOpen.value = false;
  showToast("任务已添加");
}

function checkDueReminders(): void {
  checkDueTaskReminders();
  checkDueCourseReminders();
}

function checkDueTaskReminders(): void {
  const now = Date.now();
  for (const task of tasks.value) {
    if (task.status !== "todo" || task.reminderMinutes == null) continue;
    const dueAt = new Date(task.dueAt).getTime();
    if (Number.isNaN(dueAt)) continue;
    const remindAt = dueAt - task.reminderMinutes * 60_000;
    if (now < remindAt || now > remindAt + 90_000 || (!task.remindDuringQuiet && isQuietTime(new Date()))) continue;
    const title = task.reminderMinutes === 0 ? "DDL 到期提醒" : "DDL 提前提醒";
    const body = `${task.title}（截止 ${formatDateTime(task.dueAt)}）`;
    if (notifications.value.some((item) => item.type === "task" && item.title === title && item.body === body)) continue;
    notifications.value.unshift({ id: Date.now(), title, body, createdAt: new Date().toISOString(), type: "task", read: false });
    emitReminder(title, body);
  }
}

function checkDueCourseReminders(): void {
  const now = Date.now();
  for (const course of courses.value) {
    if (course.reminderMinutes == null || !courseOccursInWeek(course, currentAcademicWeek.value)) continue;
    const start = addDays(semesterStartDate(), (currentAcademicWeek.value - 1) * 7 + course.weekday - 1);
    const [hour, minute] = course.startTime.split(":").map(Number);
    start.setHours(hour || 0, minute || 0, 0, 0);
    const remindAt = start.getTime() - course.reminderMinutes * 60_000;
    if (now < remindAt || now > remindAt + 90_000 || isQuietTime(new Date())) continue;
    const title = course.reminderMinutes === 0 ? "课程开始提醒" : "课程提前提醒";
    const body = `${course.name}（${formatDateTime(start.toISOString())}，${course.location}）`;
    if (notifications.value.some((item) => item.type === "course" && item.title === title && item.body === body)) continue;
    notifications.value.unshift({ id: Date.now(), title, body, createdAt: new Date().toISOString(), type: "course", read: false });
    emitReminder(title, body);
  }
}

function emitReminder(title: string, body: string): void {
  playReminderSound();
  if (preferences.value.browserNotifications && typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      new Notification(title, { body, icon: "/favicon.ico" });
    } catch {
      // The in-app notification and sound remain available if the OS notification is unavailable.
    }
  }
}

function playReminderSound(): void {
  try {
    if (!reminderAudioContext) reminderAudioContext = new AudioContext();
    const context = reminderAudioContext;
    const play = () => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const now = context.currentTime;
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(880, now);
      oscillator.frequency.setValueAtTime(660, now + 0.14);
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(0.16, now + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.3);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(now);
      oscillator.stop(now + 0.3);
    };
    if (context.state === "suspended") void context.resume().then(play).catch(() => undefined);
    else play();
  } catch {
    // Some browsers require a user gesture before allowing Web Audio.
  }
}

async function handleBrowserNotificationsChange(): Promise<void> {
  if (!preferences.value.browserNotifications) return;
  if (typeof Notification === "undefined") {
    preferences.value.browserNotifications = false;
    showToast("当前浏览器不支持 Windows 通知");
    return;
  }
  try {
    const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    if (permission !== "granted") {
      preferences.value.browserNotifications = false;
      showToast("未获得系统通知权限，仍会保留页面内提醒和声音");
      return;
    }
    showToast("Windows 通知已开启");
  } catch {
    preferences.value.browserNotifications = false;
    showToast("无法开启系统通知，仍会保留页面内提醒和声音");
  }
}

function isQuietTime(date: Date): boolean {
  const start = preferences.value.quietStart;
  const end = preferences.value.quietEnd;
  if (!start || !end || start === end) return false;
  const current = date.getHours() * 60 + date.getMinutes();
  const toMinutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5));
  const startMinutes = toMinutes(start);
  const endMinutes = toMinutes(end);
  return startMinutes < endMinutes ? current >= startMinutes && current < endMinutes : current >= startMinutes || current < endMinutes;
}

function toggleTask(task: StudyTask): void {
  task.status = task.status === "todo" ? "done" : "todo";
  showToast(task.status === "done" ? "已完成，可随时撤销" : "任务已恢复");
}

function deleteTask(task: StudyTask): void {
  if (deleteConfirmId.value !== task.id) {
    deleteConfirmId.value = task.id;
    window.setTimeout(() => {
      if (deleteConfirmId.value === task.id) deleteConfirmId.value = null;
    }, 5000);
    return;
  }
  tasks.value = tasks.value.filter((item) => item.id !== task.id);
  deleteConfirmId.value = null;
  showToast("任务已删除");
}

function courseGridPosition(course: Course): { gridColumn: string; gridRow: string } {
  const start = Math.max(1, Math.min(sectionRows.length, course.startSection));
  const end = Math.max(start, Math.min(sectionRows.length, course.endSection));
  return {
    gridColumn: String(course.weekday + 1),
    gridRow: `${start + 1} / span ${end - start + 1}`,
  };
}

function openImport(): void {
  importStep.value = 1;
  importFile.value = null;
  importPreview.value = [];
  importSelections.value = [];
  importError.value = "";
  importStrategy.value = courses.value.length ? "replace" : "merge";
  courseImportOpen.value = true;
}

function setImportPreview(items: ImportedCourse[]): void {
  importPreview.value = items;
  importSelections.value = items.map(() => true);
}

const selectedImportCourses = computed(() => importPreview.value.filter((_, index) => importSelections.value[index] !== false));

async function selectImportFile(event: Event): Promise<void> {
  importFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  importPreview.value = [];
  importSelections.value = [];
  importError.value = "";
  if (!importFile.value) return;
  importBusy.value = true;
  try {
    setImportPreview(await parseCourseFile(importFile.value));
  } catch (error) {
    importError.value = error instanceof Error ? error.message : "无法读取课表文件";
  } finally {
    importBusy.value = false;
  }
}

async function loadImportPreview(): Promise<boolean> {
  importError.value = "";
  if (importMode.value === "file") {
    if (!importFile.value) {
      importError.value = "请先选择 XLS、XLSX 或 CSV 课表文件";
      return false;
    }
    if (!importPreview.value.length) {
      await selectImportFile({ target: { files: [importFile.value] } } as unknown as Event);
    }
    return importPreview.value.length > 0;
  }
  if (!importClassId.value.trim()) {
    importError.value = "请输入完整班级号";
    return false;
  }
  importBusy.value = true;
  try {
    const response = await fetch("/api/courses/class", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ classId: importClassId.value.trim() }),
    });
    const payload = await response.json() as { courses?: Array<Partial<ImportedCourse>>; error?: string };
    if (!response.ok || !payload.courses) throw new Error(payload.error || "班级课表查询失败");
    setImportPreview(normalizeImportedCourses(payload.courses));
    return true;
  } catch (error) {
    importError.value = error instanceof Error ? error.message : "班级课表查询失败";
    return false;
  } finally {
    importBusy.value = false;
  }
}

async function advanceImport(): Promise<void> {
  if (importStep.value === 1) {
    if (!await loadImportPreview()) return;
    importStep.value += 1;
    return;
  }
  if (importStep.value === 2) {
    importStep.value = 3;
    return;
  }
  if (courses.value.length && importStrategy.value === "replace") courses.value = [];
  let nextId = Math.max(0, ...courses.value.map((course) => course.id)) + 1;
  const selectedCourses = selectedImportCourses.value;
  for (const imported of selectedCourses) {
    const existing = courses.value.find((course) => course.name === imported.name
      && course.weekday === imported.weekday
      && course.startSection === imported.startSection
      && course.endSection === imported.endSection);
    if (existing) Object.assign(existing, imported);
    else courses.value.push({ ...imported, id: nextId++, reminderMinutes: preferences.value.courseReminder, color: colorForCourse(imported.name, courses.value) });
  }
  courseImportOpen.value = false;
  showToast(`课表导入完成，共写入 ${selectedCourses.length} 门课程`);
}

function changeWeek(offset: number): void {
  selectedWeek.value = Math.max(1, Math.min(MAX_ACADEMIC_WEEK, selectedWeek.value + offset));
  pendingCourseSlot.value = null;
}

function goToCurrentWeek(): void {
  selectedWeek.value = Math.max(1, Math.min(MAX_ACADEMIC_WEEK, currentAcademicWeek.value));
  pendingCourseSlot.value = null;
}

function updateSelectedWeek(event: Event): void {
  const value = Number((event.target as HTMLInputElement).value);
  if (!Number.isFinite(value)) return;
  selectedWeek.value = Math.max(1, Math.min(MAX_ACADEMIC_WEEK, Math.trunc(value)));
  pendingCourseSlot.value = null;
}

function handleScheduleSlotClick(weekday: number, startSection: number): void {
  if (pendingCourseSlot.value?.weekday === weekday && pendingCourseSlot.value.startSection === startSection) {
    openCourseAdd(weekday, startSection);
    return;
  }
  pendingCourseSlot.value = { weekday, startSection };
}

function openCourseAdd(weekday = 1, startSection = 1): void {
  const base = blankCourse();
  courseForm.value = {
    ...base,
    weekday,
    startSection,
    endSection: startSection,
    ...courseTimes(startSection, startSection),
  };
  pendingCourseSlot.value = null;
  courseAddOpen.value = true;
}

function createCourse(): void {
  const name = courseForm.value.name.trim();
  const start = Number(courseForm.value.startSection);
  const end = Number(courseForm.value.endSection);
  if (!name || !Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > 20) {
    showToast("请检查课程名和节次");
    return;
  }
  let weeks: string;
  try {
    weeks = normalizeWeeks(courseForm.value.weeks);
  } catch {
    showToast("周次只支持数字、横杠和中英文逗号，例如 1-2，4-10");
    return;
  }
  const id = Math.max(0, ...courses.value.map((course) => course.id)) + 1;
  courses.value.push({
    ...courseForm.value,
    id,
    name,
    teacher: courseForm.value.teacher.trim() || "未填写",
    location: courseForm.value.location.trim() || "待定",
    startSection: start,
    endSection: end,
    weeks,
    reminderMinutes: Math.max(0, Math.min(10080, Number(courseForm.value.reminderMinutes) || 0)),
    color: colorForCourse(name, courses.value),
    ...courseTimes(start, end),
  });
  courseAddOpen.value = false;
  showToast("课程已添加");
}

function startCourseEdit(): void {
  if (!selectedCourse.value) return;
  const { id: _id, ...editable } = selectedCourse.value;
  courseForm.value = { ...editable };
  courseEditing.value = true;
  courseDeleteConfirming.value = false;
}

function deleteSelectedCourse(): void {
  if (!selectedCourse.value) return;
  if (!courseDeleteConfirming.value) {
    courseDeleteConfirming.value = true;
    if (courseDeleteConfirmTimer !== undefined) window.clearTimeout(courseDeleteConfirmTimer);
    courseDeleteConfirmTimer = window.setTimeout(() => { courseDeleteConfirming.value = false; }, 7000);
    return;
  }
  const deletedId = selectedCourse.value.id;
  courses.value = courses.value.filter((course) => course.id !== deletedId);
  selectedCourse.value = null;
  courseEditing.value = false;
  courseDeleteConfirming.value = false;
  if (courseDeleteConfirmTimer !== undefined) window.clearTimeout(courseDeleteConfirmTimer);
  showToast("课程已删除");
}

function saveCourse(): void {
  if (!selectedCourse.value) return;
  const name = courseForm.value.name.trim();
  const start = Number(courseForm.value.startSection);
  const end = Number(courseForm.value.endSection);
  if (!name || !Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > 20) {
    showToast("请检查课程名和节次");
    return;
  }
  let weeks: string;
  try {
    weeks = normalizeWeeks(courseForm.value.weeks);
  } catch {
    showToast("周次只支持数字、横杠和中英文逗号，例如 1-2，4-10");
    return;
  }
  const otherCourses = courses.value.filter((course) => course.id !== selectedCourse.value!.id);
  const reminder = Math.max(0, Math.min(10080, Number(courseForm.value.reminderMinutes) || 0));
  Object.assign(selectedCourse.value, {
    ...courseForm.value,
    name,
    teacher: courseForm.value.teacher.trim() || "未填写",
    location: courseForm.value.location.trim() || "待定",
    startSection: start,
    endSection: end,
    weeks,
    reminderMinutes: reminder,
    color: name === selectedCourse.value.name ? selectedCourse.value.color : colorForCourse(name, otherCourses),
    ...courseTimes(start, end),
  });
  courseEditing.value = false;
  showToast("课程修改已保存");
}

async function openCampusItem(item: CampusItem): Promise<void> {
  item.read = true;
  selectedCampusItem.value = item;
  campusSummaryError.value = "";
  if (item.kind !== "notice" || item.summary.trim()) return;
  campusSummaryBusy.value = true;
  try {
    const response = await fetch("/api/campus/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: item.id, title: item.title, url: item.url }),
    });
    const payload = await response.json() as { summary?: string; error?: string };
    if (!response.ok || !payload.summary) throw new Error(payload.error || "AI 通知总结生成失败");
    item.summary = payload.summary;
  } catch (error) {
    campusSummaryError.value = error instanceof Error ? error.message : "AI 通知总结生成失败";
  } finally {
    campusSummaryBusy.value = false;
  }
}

function toggleCampusSubscription(item: CampusItem): void {
  item.subscribed = !item.subscribed;
  showToast(item.subscribed ? "已订阅，后续更新会通知你" : "已取消订阅");
}

async function saveElectricityBinding(): Promise<void> {
  const dormitory = electricityDormitoryDraft.value.trim().replace(/[\s‐‑‒–—―-]+/g, "").toUpperCase();
  if (!/^(?:S[2-6]|D[12]|[ABCE])\d{3}$/.test(dormitory) && !/^学(?:\d{1,2}|一|二|三|四|五|六|七|八|九|十)\d{3}$/.test(dormitory)) {
    electricityError.value = "请输入楼宇和宿舍号，例如 A410、S2-410、学8 321 或 学八321";
    return;
  }
  electricityDormitory.value = dormitory;
  electricityDormitoryDraft.value = dormitory;
  electricityEditing.value = false;
  electricityResult.value = null;
  await queryElectricity();
}

async function queryElectricity(silent = false, dormitoryOverride?: string, throwOnError = false): Promise<ElectricityResult | null> {
  if (electricityBusy.value || !(dormitoryOverride?.trim() || electricityDormitory.value)) return null;
  electricityBusy.value = true;
  electricityError.value = "";
  try {
    const dormitory = dormitoryOverride?.trim() || electricityDormitory.value;
    const response = await fetch("/api/electricity/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dormitory }),
    });
    const payload = await response.json() as (Partial<ElectricityResult> & { error?: string });
    if (!response.ok || typeof payload.balance !== "number" || !["元", "度"].includes(payload.unit ?? "") || !payload.updatedAt || !payload.queriedAt || !payload.sourceUrl) {
      throw new Error(payload.error || "电费余额查询失败");
    }
    electricityResult.value = {
      dormitory: payload.dormitory || dormitory,
      balance: payload.balance,
      unit: payload.unit as ElectricityResult["unit"],
      updatedAt: payload.updatedAt,
      queriedAt: payload.queriedAt,
      sourceUrl: payload.sourceUrl,
    };
    if (payload.balance < 10) addLowElectricityNotification(payload.balance, payload.unit as ElectricityResult["unit"], dormitory);
    else if (!silent) showToast("电费余额已更新");
    return electricityResult.value;
  } catch (error) {
    electricityError.value = error instanceof Error ? error.message : "电费余额查询失败";
    if (throwOnError) throw error;
    return null;
  } finally {
    electricityBusy.value = false;
  }
}

function addLowElectricityNotification(balance: number, unit: ElectricityResult["unit"], dormitory = electricityDormitory.value): void {
  const today = new Date().toISOString().slice(0, 10);
  const body = `${dormitory} 当前${unit === "元" ? "余额" : "剩余电量"} ${balance.toFixed(2)} ${unit}，请及时充值。`;
  const notificationTitle = unit === "元" ? "电费余额不足" : "剩余电量不足";
  const alreadyAdded = notifications.value.some((item) => item.title === notificationTitle
    && item.body.startsWith(`${dormitory} `)
    && item.createdAt.slice(0, 10) === today);
  if (alreadyAdded) return;
  notifications.value.unshift({
    id: Date.now(),
    title: notificationTitle,
    body,
    createdAt: new Date().toISOString(),
    type: "campus",
    read: false,
  });
  emitReminder(notificationTitle, body);
  showToast(`${notificationTitle} 10 ${unit}，已加入消息提醒`);
}

function editElectricityBinding(): void {
  electricityDormitoryDraft.value = electricityDormitory.value;
  electricityEditing.value = true;
  electricityError.value = "";
}

async function loadCampusData(): Promise<void> {
  if (campusBusy.value) return;
  campusBusy.value = true;
  campusError.value = "";
  try {
    const response = await fetch("/api/campus");
    const payload = await response.json() as { items?: CampusItem[]; errors?: string[]; statuses?: CampusSourceStatus[]; updatedAt?: string; error?: string };
    campusStatuses.value = payload.statuses ?? [];
    if (!payload.items) throw new Error(payload.error || "校园数据加载失败");
    const localState = new Map(campusItems.value.map((item) => [`${item.kind}:${item.id}`, item]));
    const readableItems = payload.items.filter(isCampusItemReadable);
    campusItems.value = readableItems.map((item) => {
      const previous = localState.get(`${item.kind}:${item.id}`);
      return { ...item, read: previous?.read ?? false, subscribed: previous?.subscribed ?? false };
    });
    portalVisibleCount.value = 10;
    campusUpdatedAt.value = payload.updatedAt ?? new Date().toISOString();
    const dropped = payload.items.length - readableItems.length;
    campusError.value = [...(payload.errors ?? []), ...(payload.error && !(payload.errors ?? []).includes(payload.error) ? [payload.error] : []), ...(dropped ? [`已忽略 ${dropped} 条编码异常的旧缓存`] : [])].join("；");
  } catch (error) {
    campusError.value = error instanceof Error ? error.message : "校园数据加载失败";
    campusStatuses.value = [];
  } finally {
    campusBusy.value = false;
  }
}

function newAssistantConversation(): void {
  if (activeConversationIsBlank.value) {
    showToast("当前已是空白对话，请先发送一条消息");
    return;
  }
  const conversation = createAssistantConversation();
  assistantConversations.value.unshift(conversation);
  activeConversationId.value = conversation.id;
  assistantInput.value = "";
  assistantAttachments.value = [];
  assistantDeleteConfirmId.value = null;
}

function selectAssistantConversation(id: string): void {
  if (assistantBusy.value || id === activeConversationId.value) return;
  activeConversationId.value = id;
  assistantInput.value = "";
  assistantAttachments.value = [];
  assistantDeleteConfirmId.value = null;
}

function deleteAssistantConversation(id: string): void {
  if (assistantBusy.value) return;
  const conversation = assistantConversations.value.find((item) => item.id === id);
  if (!conversation) return;
  if (!isAssistantConversationBlank(conversation) && assistantDeleteConfirmId.value !== id) {
    assistantDeleteConfirmId.value = id;
    if (assistantDeleteConfirmTimer !== undefined) window.clearTimeout(assistantDeleteConfirmTimer);
    assistantDeleteConfirmTimer = window.setTimeout(() => { assistantDeleteConfirmId.value = null; }, 7000);
    return;
  }
  assistantDeleteConfirmId.value = null;
  if (assistantDeleteConfirmTimer !== undefined) window.clearTimeout(assistantDeleteConfirmTimer);
  assistantConversations.value = assistantConversations.value.filter((item) => item.id !== id);
  if (!assistantConversations.value.length) assistantConversations.value = [createAssistantConversation()];
  if (activeConversationId.value === id) activeConversationId.value = assistantConversations.value[0]!.id;
}

function isAssistantConversationBlank(conversation: AssistantConversation): boolean {
  return !conversation.messages.some((message) => message.role === "user");
}

function resizeAssistantComposer(): void {
  const textarea = assistantTextarea.value;
  if (!textarea) return;
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(160, Math.max(38, textarea.scrollHeight))}px`;
  textarea.style.overflowY = textarea.scrollHeight > 160 ? "auto" : "hidden";
}

function startSidebarResize(event: PointerEvent): void {
  if (window.innerWidth <= 980) return;
  event.preventDefault();
  const onMove = (moveEvent: PointerEvent) => {
    sidebarWidth.value = Math.max(190, Math.min(320, moveEvent.clientX));
  };
  const onEnd = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onEnd);
    document.body.classList.remove("resizing-sidebar");
    sidebarResizeCleanup = undefined;
  };
  sidebarResizeCleanup?.();
  sidebarResizeCleanup = onEnd;
  document.body.classList.add("resizing-sidebar");
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onEnd, { once: true });
}

function resizeSidebarWithKeyboard(event: KeyboardEvent): void {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  sidebarWidth.value = Math.max(190, Math.min(320, sidebarWidth.value + (event.key === "ArrowRight" ? 10 : -10)));
}

function openAssistantFilePicker(): void {
  assistantFileInput.value?.click();
}

async function selectAssistantFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const files = [...(input.files ?? [])];
  input.value = "";
  const allowed = assistantRuntime.value?.allowedFileTypes ?? [];
  for (const file of files) {
    if (assistantAttachments.value.length >= MAX_ASSISTANT_ATTACHMENTS) {
      showToast(`每条消息最多上传 ${MAX_ASSISTANT_ATTACHMENTS} 张图片`);
      break;
    }
    if (!allowed.includes(file.type)) {
      showToast("当前模型仅支持 PNG、JPG 和 WebP 图片");
      continue;
    }
    if (file.size > MAX_ASSISTANT_FILE_SIZE) {
      showToast("单张图片不能超过 1 MB");
      continue;
    }
    const dataUrl = await fileToDataUrl(file);
    if (!isImageDataUrl(dataUrl)) {
      showToast("无法读取这张图片");
      continue;
    }
    assistantAttachments.value.push({
      id: `file-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: file.name,
      mimeType: file.type as AssistantAttachment["mimeType"],
      size: file.size,
      dataUrl,
    });
  }
}

function removeAssistantAttachment(id: string): void {
  assistantAttachments.value = assistantAttachments.value.filter((item) => item.id !== id);
}

function nextSuggestion(): void {
  suggestionIndex.value = (suggestionIndex.value + 1) % studySuggestions.value.length;
}

function markAllNotificationsRead(): void {
  notifications.value.forEach((item) => { item.read = true; });
  showToast("通知已全部标记为已读");
}

function formatReminder(minutes: number | null): string {
  if (minutes === null) return "不提醒";
  if (minutes >= 60 && minutes % 60 === 0) return `提前 ${minutes / 60} 小时`;
  return `提前 ${minutes} 分钟`;
}

async function sendAssistant(prompt = assistantInput.value): Promise<void> {
  const text = prompt.trim();
  if ((!text && !assistantAttachments.value.length) || assistantBusy.value) return;
  assistantInput.value = "";
  const attachments = assistantAttachments.value.map((item) => ({ ...item }));
  const conversation = activeConversation.value;
  const needsGeneratedTitle = conversation.title === "新对话" && !conversation.messages.some((message) => message.role === "user");
  assistantAttachments.value = [];
  assistantMessages.value.push({ id: Date.now(), role: "user", content: text || "请分析这张图片。", createdAt: new Date().toISOString(), ...(attachments.length ? { attachments } : {}) });
  activeConversation.value.updatedAt = new Date().toISOString();
  assistantBusy.value = true;
  assistantError.value = "";
  assistantToolStatus.value = "";
  try {
    const messageWindow = preferences.value.memoryEnabled ? assistantMessages.value.slice(-12) : assistantMessages.value.slice(-1);
    const protocolMessages: Array<Record<string, unknown>> = messageWindow.map(({ role, content, attachments: messageAttachments }) => ({
      role, content, ...(messageAttachments?.length ? { attachments: messageAttachments } : {}),
    }));
    let result: AssistantToolResponse = {};
    for (let round = 0; round < 5; round += 1) {
      result = await requestAssistantCompletion(protocolMessages);
      const toolCalls = result.toolCalls ?? [];
      if (!toolCalls.length) break;
      protocolMessages.push({
        role: "assistant",
        content: result.reply || null,
        tool_calls: toolCalls,
      });
      for (const call of toolCalls) {
        assistantToolStatus.value = assistantToolLabel(call.function.name);
        const args = parseToolArguments(call.function.arguments);
        const toolResult = await executeAssistantTool(call.function.name, args);
        protocolMessages.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(toolResult, ensureJsonReplacer) });
      }
    }
    if (result.toolCalls?.length) throw new Error("工具调用轮数超过限制，请把操作拆成两步重试");
    const reply = result.reply?.trim();
    if (!reply) throw new Error("AI 服务没有返回正文");
    conversation.messages.push({ id: Date.now() + 1, role: "assistant", content: reply, createdAt: new Date().toISOString() });
    conversation.updatedAt = new Date().toISOString();
    assistantMode.value = "online";
    if (needsGeneratedTitle) void generateAssistantConversationTitle(conversation);
  } catch (error) {
    assistantMode.value = "error";
    assistantError.value = error instanceof Error ? error.message : "AI 服务暂时不可用";
    assistantMessages.value.push({ id: Date.now() + 1, role: "assistant", content: `暂时无法连接在线 AI：${assistantError.value}。请稍后重试。`, createdAt: new Date().toISOString() });
  } finally {
    assistantToolStatus.value = "";
    assistantBusy.value = false;
  }
}

function assistantToolLabel(name: string): string {
  const labels: Record<string, string> = {
    course_list: "正在查询课表…", course_edit: "正在更新课程…", course_add: "正在添加课程…",
    ddl_list: "正在查询 DDL…", ddl_show: "正在读取 DDL…", ddl_add: "正在添加 DDL…", ddl_edit: "正在编辑 DDL…",
    ddl_remind: "正在设置提醒…", ddl_done: "正在更新 DDL 状态…", campus_query: "正在查询校园通知…", electricity_query: "正在查询电费…",
  };
  return labels[name] ?? "正在执行操作…";
}

function assistantContext(): Record<string, unknown> {
  const context: Record<string, unknown> = {};
  if (preferences.value.memoryEnabled) context.profile = { name: profileName.value };
  if (preferences.value.analyticsEnabled) {
    Object.assign(context, {
      courses: courses.value.map(({ id, name, weekday, startSection, endSection, location, teacher, weeks, reminderMinutes }) => ({ id, name, weekday, startSection, endSection, location, teacher, weeks, reminderMinutes })),
      tasks: todoTasks.value.map(({ id, title, course, dueAt, reminderMinutes }) => ({ id, title, course, dueAt, reminderMinutes })),
      campus: campusItems.value.slice(0, 50).map(({ id, kind, category, title, summary, publishedAt, campus, eventTime, read }) => ({ id, kind, category, title, summary, publishedAt, campus, eventTime, read })),
      notifications: notifications.value.slice(0, 50),
      electricity: electricityResult.value,
    });
  }
  return context;
}

async function requestAssistantCompletion(messages: Array<Record<string, unknown>>): Promise<AssistantToolResponse> {
  const response = await fetch("/api/assistant/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      stream: false,
      thinking: assistantRuntime.value?.thinkingSupported ? assistantThinkingEnabled.value : false,
      tools: assistantTools,
      messages,
      context: assistantContext(),
    }),
  });
  const payload = await response.json() as AssistantToolResponse;
  if (!response.ok) throw new Error(payload.error || "AI 服务暂时不可用");
  return payload;
}

function parseToolArguments(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function ensureJsonReplacer(_key: string, value: unknown): unknown {
  return value === undefined ? null : value;
}

async function executeAssistantTool(name: string, args: Record<string, unknown>): Promise<AssistantToolResult> {
  try {
    if (name === "course_list") {
      const weekday = args.weekday == null ? null : Number(args.weekday);
      const rows = courses.value.filter((course) => weekday == null || course.weekday === weekday);
      return { success: true, courses: rows.map((course) => ({ ...course })) };
    }
    if (name === "course_edit") {
      const id = Number(args.course_id);
      const course = courses.value.find((item) => item.id === id);
      if (!course) return { success: false, error: "课程不存在" };
      const weekday = args.weekday == null ? course.weekday : Number(args.weekday);
      const startSection = args.start_section == null ? course.startSection : Number(args.start_section);
      const endSection = args.end_section == null ? course.endSection : Number(args.end_section);
      if (!Number.isInteger(weekday) || weekday < 1 || weekday > 7 || !Number.isInteger(startSection) || !Number.isInteger(endSection) || endSection < startSection) return { success: false, error: "星期或节次范围无效" };
      Object.assign(course, {
        name: args.name == null ? course.name : String(args.name).trim(),
        teacher: args.teacher == null ? course.teacher : String(args.teacher).trim(),
        location: args.location == null ? course.location : String(args.location).trim(),
        weekday, startSection, endSection,
        weeks: args.weeks == null ? course.weeks : normalizeWeeks(String(args.weeks)),
        reminderMinutes: args.reminder_minutes == null ? course.reminderMinutes : Number(args.reminder_minutes),
        ...courseTimes(startSection, endSection),
      });
      return { success: true, course: { ...course } };
    }
    if (name === "course_add") {
      const nameValue = String(args.name ?? "").trim();
      const weekday = Number(args.weekday);
      const startSection = Number(args.start_section);
      const endSection = Number(args.end_section);
      if (!nameValue || !Number.isInteger(weekday) || weekday < 1 || weekday > 7 || !Number.isInteger(startSection) || !Number.isInteger(endSection) || endSection < startSection) return { success: false, error: "课程名称、星期或节次无效" };
      const course: Course = {
        id: Math.max(0, ...courses.value.map((item) => item.id)) + 1,
        name: nameValue,
        teacher: String(args.teacher ?? "").trim(), location: String(args.location ?? "").trim(), weekday,
        startSection, endSection, weeks: normalizeWeeks(String(args.weeks ?? "1-16")),
        reminderMinutes: args.reminder_minutes == null ? preferences.value.courseReminder : Number(args.reminder_minutes),
        color: colorForCourse(nameValue, courses.value),
        ...courseTimes(startSection, endSection),
      };
      courses.value.push(course);
      return { success: true, course: { ...course } };
    }
    if (name === "ddl_list") {
      const status = String(args.status ?? "todo");
      const rows = tasks.value.filter((task) => status === "all" || task.status === status);
      return { success: true, items: rows.map((task) => ({ ...task })) };
    }
    if (name === "ddl_show") {
      const task = tasks.value.find((item) => item.id === Number(args.ddl_id));
      return task ? { success: true, ddl: { ...task } } : { success: false, error: "DDL 不存在" };
    }
    if (name === "ddl_add") {
      const title = String(args.content ?? "").trim();
      const dueAt = parseAssistantDeadline(String(args.deadline ?? ""));
      if (!title || !dueAt || new Date(dueAt).getTime() <= Date.now()) return { success: false, error: "DDL 内容为空或截止时间无效" };
      const hasReminder = Object.prototype.hasOwnProperty.call(args, "reminder_minutes");
      const requestedReminder = !hasReminder ? preferences.value.defaultTaskReminder : args.reminder_minutes == null ? null : Number(args.reminder_minutes);
      const reminderMinutes = !hasReminder && new Date(dueAt).getTime() - Date.now() <= preferences.value.defaultTaskReminder * 60_000 ? 0 : requestedReminder;
      const normalizedReminder = reminderMinutes == null ? null : Number.isFinite(reminderMinutes) ? Math.max(0, Math.min(10080, reminderMinutes)) : 0;
      const task: StudyTask = { id: Math.max(0, ...tasks.value.map((item) => item.id)) + 1, title, course: "个人计划", dueAt, reminderMinutes: normalizedReminder, remindDuringQuiet: false, status: "todo", createdAt: new Date().toISOString() };
      tasks.value.push(task);
      return { success: true, ddl: { ...task } };
    }
    if (name === "ddl_edit") {
      const task = tasks.value.find((item) => item.id === Number(args.ddl_id) && item.status === "todo");
      if (!task) return { success: false, error: "DDL 不存在或已完成" };
      if (args.content != null && !String(args.content).trim()) return { success: false, error: "DDL 内容不能为空" };
      if (args.deadline != null) {
        const dueAt = parseAssistantDeadline(String(args.deadline));
        if (!dueAt || new Date(dueAt).getTime() <= Date.now()) return { success: false, error: "截止时间无效" };
        task.dueAt = dueAt;
      }
      if (args.content != null) task.title = String(args.content).trim();
      if (args.reminder_minutes !== undefined) task.reminderMinutes = args.reminder_minutes == null ? null : Math.max(0, Math.min(10080, Number(args.reminder_minutes)));
      return { success: true, ddl: { ...task } };
    }
    if (name === "ddl_remind") {
      const task = tasks.value.find((item) => item.id === Number(args.ddl_id) && item.status === "todo");
      if (!task) return { success: false, error: "DDL 不存在或已完成" };
      task.reminderMinutes = args.reminder_minutes == null ? null : Math.max(0, Math.min(10080, Number(args.reminder_minutes)));
      return { success: true, ddl: { ...task } };
    }
    if (name === "ddl_done") {
      const task = tasks.value.find((item) => item.id === Number(args.ddl_id));
      if (!task) return { success: false, error: "DDL 不存在" };
      task.status = "done";
      return { success: true, ddl: { ...task } };
    }
    if (name === "campus_query") {
      await loadCampusData();
      const kind = String(args.kind ?? "all");
      const query = String(args.query ?? "").trim().toLowerCase();
      const limit = Math.max(1, Math.min(20, Number(args.limit) || 10));
      const items = campusItems.value.filter((item) => (kind === "all" || item.kind === kind) && (!query || `${item.title} ${item.summary} ${item.category}`.toLowerCase().includes(query))).slice(0, limit);
      return { success: true, items, statuses: campusStatuses.value };
    }
    if (name === "electricity_query") {
      const dormitory = String(args.dormitory ?? electricityDormitory.value).trim();
      if (!dormitory) return { success: false, error: "请提供宿舍号，例如学8 321 或 S2-410" };
      const result = await queryElectricity(true, dormitory, true);
      return result ? { success: true, electricity: result } : { success: false, error: electricityError.value || "电费查询失败" };
    }
    return { success: false, error: `未知工具：${name}` };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : "工具执行失败" };
  }
}

function parseAssistantDeadline(value: string): string | null {
  const text = value.trim().replace(/：/g, ":");
  const now = new Date();
  const relative = /^(\d+)\s*(分钟|分|小时|天)后$/.exec(text);
  if (relative) {
    const amount = Number(relative[1]);
    const unit = relative[2];
    now.setTime(now.getTime() + amount * (unit === "小时" ? 3600000 : unit === "天" ? 86400000 : 60000));
    return now.toISOString();
  }
  const iso = new Date(text);
  if (!Number.isNaN(iso.getTime())) return iso.toISOString();
  const clockMatch = /^(\d{1,2}):(\d{2})$/.exec(text);
  if (clockMatch) {
    now.setHours(Number(clockMatch[1]), Number(clockMatch[2]), 0, 0);
    if (now.getTime() <= Date.now()) now.setDate(now.getDate() + 1);
    return now.toISOString();
  }
  const dayMatch = /^(今天|明天|后天)\s*(上午|下午|晚上)?\s*(\d{1,2})(?::|点|时)?(\d{0,2})?$/.exec(text);
  if (dayMatch) {
    let hour = Number(dayMatch[3]);
    const minute = Number(dayMatch[4] || 0);
    if (["下午", "晚上"].includes(dayMatch[2] || "") && hour < 12) hour += 12;
    now.setDate(now.getDate() + ({ 今天: 0, 明天: 1, 后天: 2 }[dayMatch[1]!] ?? 0));
    now.setHours(hour, minute, 0, 0);
    return now.toISOString();
  }
  return null;
}

async function generateAssistantConversationTitle(conversation: AssistantConversation): Promise<void> {
  try {
    const response = await fetch("/api/assistant/title", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: conversation.messages.slice(0, 3).map(({ role, content }) => ({ role, content })),
      }),
    });
    const payload = await response.json() as { title?: string };
    if (response.ok && payload.title) conversation.title = payload.title;
  } catch {
    // A title is optional; the completed conversation remains usable when summarization is unavailable.
  }
}

function runAssistantAction(message: AssistantMessage): void {
  const action = message.action;
  if (!action || action.completed) return;
  if (action.type === "navigate") {
    navigate(String(action.payload.page) as PageId);
    return;
  }
  if (action.type === "create-task") {
    tasks.value.push({
      id: Math.max(0, ...tasks.value.map((task) => task.id)) + 1,
      title: String(action.payload.title),
      course: "个人计划",
      dueAt: String(action.payload.dueAt),
      reminderMinutes: preferences.value.defaultTaskReminder,
      remindDuringQuiet: false,
      status: "todo",
      createdAt: new Date().toISOString(),
    });
    action.completed = true;
    showToast("任务已由助手添加");
  }
}
</script>

<template>
  <div class="app-shell" :style="{ '--sidebar-width': `${sidebarWidth}px` }">
    <aside class="sidebar">
      <button class="brand" type="button" aria-label="返回今天" @click="navigate('today')">
        <span class="brand-mark">邮</span>
        <span><strong>邮学伴</strong><small>北邮人的学习与生活助手</small></span>
      </button>
      <nav class="side-nav" aria-label="主导航">
        <button v-for="item in navItems" :key="item.id" type="button" :class="{ active: currentPage === item.id }" @click="navigate(item.id)">
          <IconGlyph :name="item.icon" /> <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-spacer" />
      <div class="profile-button sidebar-profile"><span class="avatar"><img v-if="profileAvatar" :src="profileAvatar" alt="" /><template v-else>{{ profileInitial }}</template></span><span class="profile-text">{{ profileName }}<small>北邮学生</small></span></div>
      <button class="sidebar-status" type="button" @click="navigate('notifications')">
        <span class="status-dot" /><span><strong>提醒</strong><small>{{ unreadCount }} 条未读通知</small></span>
      </button>
      <button class="sidebar-settings" type="button" :class="{ active: currentPage === 'settings' }" @click="navigate('settings')"><IconGlyph name="settings" />设置</button>
      <button class="sidebar-resizer" type="button" role="separator" aria-orientation="vertical" aria-label="调节左侧菜单栏宽度" :aria-valuenow="sidebarWidth" aria-valuemin="190" aria-valuemax="320" @pointerdown="startSidebarResize" @keydown="resizeSidebarWithKeyboard" />
    </aside>

    <div class="app-main">
      <main class="page-container">
        <section v-if="currentPage === 'today'" class="page page-today">
          <header class="page-heading today-heading"><div><span class="eyebrow">第 {{ currentAcademicWeek }} 周</span><h1>{{ greeting }}，{{ profileName || '同学' }}。</h1><p>先把今天的安排理清楚。</p></div><time class="today-clock"><strong>{{ timeHeading }}</strong><span>{{ dateHeading }}</span></time></header>
          <div class="today-layout">
            <div class="content-stack">
              <article class="surface course-overview">
                <div class="surface-heading"><h2>{{ nextCourseState }}</h2><button class="text-button" type="button" @click="navigate('courses')">查看周课表 <IconGlyph name="arrow-right" :size="15" /></button></div>
                <div v-if="nextCourse" class="next-course-card">
                  <div class="time-block"><strong>{{ nextCourse.startTime }}</strong><span>第 {{ nextCourse.startSection }}–{{ nextCourse.endSection }} 节</span></div>
                  <div class="next-course-main"><strong>{{ nextCourse.name }}</strong><span>{{ nextCourse.location }} · {{ nextCourse.teacher }}</span></div>
                  <span class="countdown">{{ currentCourse ? `正在上课 · ${nextCourse.endTime} 下课` : '稍后开始' }}</span>
                </div>
                <div v-else class="empty-state compact"><IconGlyph name="courses" /><strong>今天没有后续课程</strong><span>可以继续处理任务或安排复习。</span></div>
                <div class="day-timeline">
                  <div v-for="course in todayCourses" :key="course.id" class="timeline-row">
                    <time>{{ course.startTime }}</time><span class="timeline-line" /><button type="button" @click="selectedCourse = course"><strong>{{ course.name }}</strong><small>{{ course.location }} · {{ course.endTime }} 下课</small></button>
                  </div>
                </div>
              </article>
              <article class="surface">
                <div class="surface-heading"><h2>近期任务</h2><button class="text-button" type="button" @click="navigate('tasks')">查看全部 <IconGlyph name="arrow-right" :size="15" /></button></div>
                <div class="compact-task-list">
                  <div v-for="task in todoTasks.slice(0, 4)" :key="task.id" class="compact-task">
                    <button class="task-check" type="button" :aria-label="`完成 ${task.title}`" @click="toggleTask(task)"><IconGlyph name="check" :size="14" /></button>
                    <button class="task-summary" type="button" @click="navigate('tasks')"><strong>{{ task.title }}</strong><small>{{ task.course }} · {{ formatReminder(task.reminderMinutes) }}</small></button>
                    <time :class="{ overdue: new Date(task.dueAt).getTime() < Date.now() }">{{ relativeDue(task.dueAt) }}</time>
                  </div>
                  <div v-if="!todoTasks.length" class="empty-state compact"><IconGlyph name="tasks" /><strong>今天没有待办</strong><span>可以安心安排学习或休息。</span></div>
                </div>
              </article>
            </div>
            <div class="content-stack side-column">
              <article class="surface">
                <div class="surface-heading"><h2>校园动态</h2><button class="text-button" type="button" @click="navigate('campus')">进入校园 <IconGlyph name="arrow-right" :size="15" /></button></div>
                <button v-for="item in campusItems.slice(0, 3)" :key="item.id" class="news-row" type="button" @click="openCampusItem(item)"><span v-if="!item.read" class="unread-dot" /><strong>{{ item.title }}</strong><small>{{ item.source }} · {{ formatDateTime(item.publishedAt) }}</small></button>
              </article>
              <article class="surface suggestion-card"><div class="surface-heading"><h2>现在做什么</h2><span>结合当前安排推荐</span></div><p>{{ currentSuggestion }}</p><button class="text-button" type="button" @click="nextSuggestion">换一个建议</button></article>
            </div>
          </div>
          <div class="quick-ask"><IconGlyph name="assistant" /><input v-model="assistantInput" aria-label="询问学习助手" placeholder="问助手：帮我安排今晚，或查最近的奖学金通知" @keyup.enter="navigate('assistant'); sendAssistant()"><button type="button" @click="navigate('assistant'); sendAssistant()">发送</button></div>
        </section>

        <section v-else-if="currentPage === 'tasks'" class="page">
          <header class="page-heading split"><div><span class="eyebrow">个人事务</span><h1>任务与 DDL</h1><p>按截止时间安排，不让重要事项被聊天记录淹没。</p></div><button class="primary-button" type="button" @click="openTaskModal()"><IconGlyph name="plus" />添加任务</button></header>
          <div class="toolbar"><div class="segmented"><button v-for="filter in [{id:'todo',label:`待完成 ${todoTasks.length}`},{id:'all',label:`全部 ${tasks.length}`},{id:'done',label:`已完成 ${tasks.filter(t=>t.status==='done').length}`} ]" :key="filter.id" type="button" :class="{ active: taskFilter === filter.id }" @click="taskFilter = filter.id as typeof taskFilter">{{ filter.label }}</button></div><label class="search-field"><IconGlyph name="search" /><input v-model="taskSearch" placeholder="搜索任务或课程" /></label></div>
          <div class="task-list surface">
            <article v-for="task in filteredTasks" :key="task.id" class="task-row" :class="{ completed: task.status === 'done' }">
              <button class="task-check" :class="{ checked: task.status === 'done' }" type="button" :aria-label="task.status === 'done' ? '恢复任务' : '完成任务'" @click="toggleTask(task)"><IconGlyph name="check" :size="14" /></button>
              <div class="task-body"><strong>{{ task.title }}</strong><span><b>{{ task.course }}</b><span class="dot-separator">·</span><IconGlyph name="bell" :size="13" /> {{ formatReminder(task.reminderMinutes) }}<template v-if="task.remindDuringQuiet"><span class="dot-separator">·</span>静默时段仍提醒</template></span></div>
              <div class="task-due"><span :class="{ overdue: new Date(task.dueAt).getTime() < Date.now() && task.status === 'todo' }">{{ formatDateTime(task.dueAt) }}</span><small>{{ task.status === 'done' ? '已完成' : relativeDue(task.dueAt) }}</small></div>
              <button class="row-action danger" :class="{ confirming: deleteConfirmId === task.id }" type="button" :aria-label="deleteConfirmId === task.id ? '确认删除任务' : '删除任务'" @click="deleteTask(task)"><span v-if="deleteConfirmId === task.id">确认删除</span><IconGlyph v-else name="trash" /></button>
            </article>
            <div v-if="!filteredTasks.length" class="empty-state"><IconGlyph name="search" :size="28" /><strong>没有找到任务</strong><span>换个关键词，或新建一项任务。</span></div>
          </div>
        </section>

        <section v-else-if="currentPage === 'courses'" class="page">
          <header class="page-heading split"><div><span class="eyebrow">当前是第 {{ currentAcademicWeek }} 周</span><h1 v-if="selectedWeek === currentAcademicWeek">本周课程</h1><h1 v-else>第 <input class="week-number-input" type="number" min="1" :max="MAX_ACADEMIC_WEEK" :value="selectedWeek" aria-label="查看第几周课程" @input="updateSelectedWeek" /> 周课程</h1><p>点击课程查看周次、地点、教师和提醒设置。</p></div><button class="primary-button" type="button" @click="openImport"><IconGlyph name="upload" />导入课表</button></header>
          <div class="toolbar course-toolbar"><div class="week-switcher"><button class="icon-button" type="button" aria-label="上一周" :disabled="selectedWeek <= 1" @click="changeWeek(-1)"><IconGlyph name="chevron-left" /></button><button class="secondary-button active week-current-button" type="button" @click="goToCurrentWeek">{{ selectedWeek === currentAcademicWeek ? '本周' : `返回第 ${currentAcademicWeek} 周` }}</button><button class="icon-button" type="button" aria-label="下一周" :disabled="selectedWeek >= MAX_ACADEMIC_WEEK" @click="changeWeek(1)"><IconGlyph name="chevron-right" /></button></div><span class="sync-status"><span class="status-dot" />第 {{ selectedWeek }} 周</span></div>
          <div class="schedule-wrap surface">
            <div class="schedule-grid">
              <div class="schedule-corner" :style="{ gridColumn: '1', gridRow: '1' }" /><div v-for="(day, dayIndex) in weekDates" :key="day.label" class="day-header" :style="{ gridColumn: String(dayIndex + 2), gridRow: '1' }"><strong>{{ day.label }}</strong><span>{{ formatWeekDate(day.date) }}</span></div>
              <template v-for="row in sectionRows" :key="row.key">
                <div class="section-label" :style="{ gridColumn: '1', gridRow: String(row.key + 1) }"><strong>{{ row.label }}</strong><span>{{ row.startTime }}</span><span>{{ row.endTime }}</span></div>
                <button v-for="day in 7" :key="`${row.key}-${day}`" class="schedule-slot" :class="{ selected: pendingCourseSlot?.weekday === day && pendingCourseSlot.startSection === row.key }" :style="{ gridColumn: String(day + 1), gridRow: String(row.key + 1) }" type="button" :aria-label="`${weekdays[day - 1]}第${row.key}节空白课程区域`" @click="handleScheduleSlotClick(day, row.key)"><IconGlyph v-if="pendingCourseSlot?.weekday === day && pendingCourseSlot.startSection === row.key" name="plus" :size="18" /></button>
              </template>
              <button v-for="course in visibleCourses" :key="course.id" class="course-cell" :class="[`course-${course.color}`, { compact: course.endSection === course.startSection }]" :style="courseGridPosition(course)" type="button" @click="selectedCourse = course; courseEditing = false"><strong>{{ course.name }}</strong><span>{{ course.location }}</span><small>{{ course.teacher }}</small></button>
            </div>
          </div>
          <div class="mobile-course-list surface"><article v-for="course in visibleCourses" :key="course.id"><time>{{ weekdays[course.weekday - 1] ?? `周${course.weekday}` }}<br>{{ formatWeekDate(weekDates[course.weekday - 1]!.date) }} · {{ course.startTime }}–{{ course.endTime }}</time><span :class="`course-marker course-${course.color}`" /><button type="button" @click="selectedCourse = course; courseEditing = false"><strong>{{ course.name }}</strong><small>第 {{ course.startSection }}–{{ course.endSection }} 节 · {{ course.location }} · {{ course.teacher }}</small></button></article><div v-if="!visibleCourses.length" class="empty-state compact"><strong>这一周没有课程</strong><span>仍可使用上方按钮继续切换周次，或导入你的真实课表。</span></div></div>
        </section>

        <section v-else-if="currentPage === 'campus'" class="page">
          <header class="page-heading split"><div><span class="eyebrow">真实校园服务</span><h1>校园</h1><p>只读查询信息门户通知与第二课堂活动。<span v-if="campusUpdatedAt">上次刷新：{{ formatDateTime(campusUpdatedAt) }}</span></p></div><button class="secondary-button" type="button" :disabled="campusBusy" @click="loadCampusData"><IconGlyph name="refresh" />{{ campusBusy ? '正在刷新' : '刷新' }}</button></header>
          <nav class="campus-service-links" aria-label="北邮校园系统快捷入口"><a v-for="service in campusServices" :key="service.name" :href="service.url" target="_blank" rel="noopener noreferrer"><span><strong>{{ service.name }}</strong><small>{{ service.description }}</small></span><IconGlyph name="external" :size="17" /></a></nav>
          <div v-if="campusStatuses.length" class="campus-statuses" aria-label="校园数据来源状态"><span v-for="status in campusStatuses" :key="status.source" :class="`mode-${status.mode}`"><i /> <strong>{{ status.label }}</strong>{{ status.message }}</span></div>
          <div class="toolbar"><div class="segmented"><button type="button" :class="{ active: campusTab === 'notice' }" @click="campusTab = 'notice'">信息门户</button><button type="button" :class="{ active: campusTab === 'activity' }" @click="campusTab = 'activity'">第二课堂</button></div><label class="search-field"><IconGlyph name="search" /><input v-model="campusSearch" placeholder="搜索标题、类别或内容" /></label></div>
          <p v-if="campusError" class="service-warning" role="status">{{ campusError }}<span v-if="campusItems.length">已保留成功读取的数据。</span></p>
          <div class="campus-grid">
            <article v-for="item in filteredCampusItems" :key="item.id" class="campus-card surface" :class="{ unread: !item.read }">
              <div class="campus-card-top"><span class="category-chip">{{ item.category }}</span><button class="subscribe-button" :class="{ subscribed: item.subscribed }" type="button" @click="toggleCampusSubscription(item)">{{ item.subscribed ? '已订阅' : '订阅' }}</button></div>
              <button class="campus-content" type="button" @click="openCampusItem(item)"><strong>{{ item.title }}</strong><p>{{ item.summary || (item.kind === 'notice' ? '点击生成 AI 通知总结。' : '点击查看活动详情。') }}</p><span v-if="item.campus"><IconGlyph name="map" :size="14" />{{ item.campus }}</span><span v-if="item.eventTime"><IconGlyph name="clock" :size="14" />{{ formatDateTime(item.eventTime) }}</span></button>
              <footer><span>{{ item.source }}</span><time>{{ formatDateTime(item.publishedAt) }}</time></footer>
            </article>
          </div>
          <div v-if="campusBusy && !campusItems.length" class="empty-state surface"><IconGlyph name="refresh" :size="28" /><strong>正在读取官方服务</strong><span>信息门户与第二课堂会分别返回状态。</span></div>
          <div v-else-if="!filteredCampusItems.length" class="empty-state surface"><IconGlyph :name="activityIsEmptyOnline ? 'campus' : 'search'" :size="28" /><strong>{{ activityIsEmptyOnline ? '当前暂无活动' : campusError ? '当前来源没有可显示的数据' : '没有匹配的信息' }}</strong><span>{{ activityIsEmptyOnline ? '第二课堂当前没有进行中的活动。' : campusError ? '请根据上方提示更新会话或稍后重试。' : '尝试缩短关键词或切换栏目。' }}</span></div>
          <div v-if="campusTab === 'notice' && !campusSearch.trim() && portalItemCount" class="campus-load-more"><button v-if="canLoadMorePortalItems" class="secondary-button" type="button" @click="portalVisibleCount = Math.min(50, portalVisibleCount + 10)">获取更多通知</button><a v-else class="secondary-button" href="http://my.bupt.edu.cn/" target="_blank" rel="noopener noreferrer">请前往官网查看更多通知</a></div>
        </section>

        <section v-else-if="currentPage === 'electricity'" class="page electricity-page">
          <header class="page-heading"><span class="eyebrow">校园生活</span><h1>查电费</h1><p>绑定宿舍后，每次打开邮学伴会自动查询一次；余额不足 10 元或剩余总电量不足 10 度时会加入消息提醒。</p></header>
          <article v-if="electricityEditing" class="surface electricity-bind-card">
            <div><span class="electricity-icon"><IconGlyph name="electricity" :size="26" /></span><h2>{{ electricityDormitory ? '修改宿舍号' : '初次查询先绑定宿舍号' }}</h2><p>只需填写楼宇和宿舍号，中间可使用横杠、空格或不加分隔符。S2–S6 自动识别为沙河雁南园，A、B、C、D1、D2、E 自动识别为沙河雁北园，“学n”楼自动识别为西土城，n 可写数字或汉字一至十；宿舍号第一位即楼层。</p></div>
            <form @submit.prevent="saveElectricityBinding"><label>楼宇宿舍号<input v-model="electricityDormitoryDraft" maxlength="16" autocomplete="off" placeholder="例如 A410、S2-410、学8 321、学八321" /></label><p v-if="electricityError" class="form-error" role="alert">{{ electricityError }}</p><footer><button v-if="electricityDormitory" class="secondary-button" type="button" @click="electricityEditing = false; electricityError = ''">取消</button><button class="primary-button" type="submit" :disabled="electricityBusy">{{ electricityBusy ? '正在查询…' : '绑定并查询' }}</button></footer></form>
          </article>
          <article v-else class="surface electricity-result-card" :class="{ low: electricityResult && electricityResult.balance < 10 }">
            <div class="surface-heading"><div><span class="eyebrow">已绑定宿舍</span><h2>{{ electricityDormitory }}</h2></div><button class="text-button" type="button" @click="editElectricityBinding">修改</button></div>
            <div v-if="electricityResult" class="balance-display"><small>{{ electricityResult.unit === '元' ? '当前余额' : '剩余总电量（含赠送电量）' }}</small><strong>{{ electricityResult.balance.toFixed(2) }}<b> {{ electricityResult.unit }}</b></strong><span v-if="electricityResult.balance < 10">{{ electricityResult.unit === '元' ? '余额' : '剩余总电量' }}不足 10 {{ electricityResult.unit }}，请及时充值</span><span v-else>{{ electricityResult.unit === '元' ? '余额' : '剩余总电量' }}充足</span><div class="balance-times"><time>电费更新于 {{ formatDateTime(electricityResult.updatedAt) }}</time><time>本次查询于 {{ formatDateTime(electricityResult.queriedAt) }}</time></div></div>
            <div v-else-if="electricityBusy" class="electricity-loading"><IconGlyph name="refresh" :size="26" /><strong>正在查询电费余额</strong></div>
            <p v-if="electricityError" class="service-warning" role="alert">{{ electricityError }}</p>
            <footer><button class="secondary-button" type="button" :disabled="electricityBusy" @click="queryElectricity()"><IconGlyph name="refresh" />{{ electricityBusy ? '正在查询' : '重新查询' }}</button><a class="primary-button" href="https://app.bupt.edu.cn/buptdf/wap/default/chong" target="_blank" rel="noopener noreferrer"><IconGlyph name="external" />前往官方页面</a></footer>
          </article>
        </section>

        <section v-else-if="currentPage === 'assistant'" class="page assistant-page">
          <header class="page-heading"><span class="eyebrow">{{ assistantMode === 'online' ? '在线 AI' : assistantMode === 'error' ? '连接失败' : '学习问答' }}</span><h1>学习助手</h1><p>提问课程知识、上传题目图片，或让助手结合课表和任务规划学习。</p><div v-if="assistantRuntime" class="assistant-runtime" aria-label="当前助手配置"><span><small>模型</small><strong>{{ assistantModelLabel }}</strong></span><span v-if="assistantRuntime.thinkingSupported"><small>思考</small><strong>{{ assistantThinkingEnabled ? '已开启' : '已关闭' }}</strong></span><span v-if="assistantRuntime.webSearchEnabled !== undefined"><small>联网搜索</small><strong>{{ assistantRuntime.webSearchEnabled ? '已开启' : '已关闭' }}</strong></span></div></header>
          <div class="assistant-workspace">
            <div class="assistant-chat-column">
              <div class="quick-prompts"><button v-for="prompt in ['解释这道题的思路','我今天有什么课？','列出三天内的 DDL','帮我制定复习计划']" :key="prompt" type="button" @click="sendAssistant(prompt)">{{ prompt }}</button></div>
              <div class="chat-panel surface" aria-live="polite">
                <div v-for="message in assistantMessages" :key="message.id" class="message" :class="message.role">
                  <span class="message-avatar"><template v-if="message.role === 'assistant'">邮</template><img v-else-if="profileAvatar" :src="profileAvatar" alt="" /><template v-else>{{ profileInitial }}</template></span>
                  <div class="message-content"><div v-if="message.attachments?.length" class="message-attachments"><img v-for="attachment in message.attachments" :key="attachment.id" :src="attachment.dataUrl" :alt="attachment.name" /></div><div v-if="message.role === 'assistant'" class="markdown-body" v-html="renderAssistantContent(message.content)" /><p v-else>{{ message.content }}</p><button v-if="message.action" class="inline-action" :disabled="message.action.completed" type="button" @click="runAssistantAction(message)"><IconGlyph :name="message.action.completed ? 'check' : 'arrow-right'" :size="15" />{{ message.action.completed ? '已完成' : message.action.label }}</button></div>
                </div>
                <div v-if="assistantBusy && assistantMessages[assistantMessages.length - 1]?.role !== 'assistant'" class="message assistant"><span class="message-avatar">邮</span><div class="message-content typing"><span /><span /><span /><small v-if="assistantToolStatus">{{ assistantToolStatus }}</small></div></div>
              </div>
              <div v-if="assistantAttachments.length" class="assistant-attachment-tray"><span v-for="attachment in assistantAttachments" :key="attachment.id"><img :src="attachment.dataUrl" :alt="attachment.name" /><small>{{ attachment.name }}</small><button type="button" aria-label="移除附件" @click="removeAssistantAttachment(attachment.id)"><IconGlyph name="close" :size="13" /></button></span></div>
              <form class="assistant-composer" @submit.prevent="sendAssistant()"><input ref="assistantFileInput" type="file" hidden multiple :accept="assistantRuntime?.allowedFileTypes?.join(',')" @change="selectAssistantFiles" /><button class="composer-tool" type="button" :disabled="!assistantRuntime?.allowedFileTypes?.length" aria-label="上传图片" title="上传当前模型支持的图片" @click="openAssistantFilePicker"><IconGlyph name="plus" /></button><textarea ref="assistantTextarea" v-model="assistantInput" rows="1" placeholder="给学习助手发送信息" @input="resizeAssistantComposer" @keydown.enter.exact.prevent="sendAssistant()" /><button v-if="assistantRuntime?.thinkingSupported" class="thinking-toggle" :class="{ active: assistantThinkingEnabled }" type="button" :aria-pressed="assistantThinkingEnabled" @click="assistantThinkingEnabled = !assistantThinkingEnabled"><IconGlyph name="assistant" :size="16" /><span>{{ assistantThinkingEnabled ? '思考' : '快速' }}</span></button><button class="composer-send" type="submit" :disabled="assistantBusy || (!assistantInput.trim() && !assistantAttachments.length)" aria-label="发送"><IconGlyph name="send" /></button></form>
              <p class="assistant-note">{{ assistantMode === 'error' ? `在线 AI 暂不可用：${assistantError}` : '支持 PNG、JPG、WebP 图片；回答仅供学习参考，请自行核对关键结论。' }}</p>
            </div>
            <aside class="conversation-sidebar surface"><header><strong>对话</strong><button class="icon-button" type="button" :disabled="activeConversationIsBlank" :aria-label="activeConversationIsBlank ? '当前已是空白对话' : '新建对话'" @click="newAssistantConversation"><IconGlyph name="plus" /></button></header><div><div v-for="conversation in assistantConversations" :key="conversation.id" class="conversation-item" :class="{ active: conversation.id === activeConversationId }"><button class="conversation-select" type="button" @click="selectAssistantConversation(conversation.id)"><strong>{{ conversation.title }}</strong><small>{{ formatDateTime(conversation.updatedAt) }}</small></button><button class="conversation-delete" :class="{ confirming: assistantDeleteConfirmId === conversation.id }" type="button" :aria-label="assistantDeleteConfirmId === conversation.id ? '确认删除对话' : '删除对话'" @click="deleteAssistantConversation(conversation.id)"><span v-if="assistantDeleteConfirmId === conversation.id">确认删除</span><IconGlyph v-else name="trash" :size="14" /></button></div></div></aside>
          </div>
        </section>

        <section v-else-if="currentPage === 'notifications'" class="page narrow-page">
          <header class="page-heading split"><div><span class="eyebrow">消息中心</span><h1>通知</h1><p>课程、DDL 和校园订阅都集中在这里。</p></div><button class="secondary-button" type="button" @click="markAllNotificationsRead">全部已读</button></header>
          <div class="notification-list surface"><button v-for="item in notifications" :key="item.id" type="button" :class="{ unread: !item.read }" @click="item.read = true"><span class="notification-icon" :class="`type-${item.type}`"><IconGlyph :name="item.type === 'course' ? 'courses' : item.type === 'task' ? 'tasks' : 'campus'" /></span><span><strong>{{ item.title }}</strong><small>{{ item.body }}</small><time>{{ formatDateTime(item.createdAt) }}</time></span><span v-if="!item.read" class="unread-dot" /></button></div>
        </section>

        <section v-else class="page narrow-page settings-page">
          <header class="page-heading"><span class="eyebrow">个人偏好</span><h1>设置</h1><p>管理提醒、显示和隐私，不需要修改配置文件。</p></header>
          <article class="settings-section surface profile-settings"><div><h2>个人资料</h2><p>昵称会用于问候；头像可从本地上传，图片只保存在当前浏览器。</p></div><div class="profile-editor"><span class="avatar avatar-preview"><img v-if="profileDraftAvatar" :src="profileDraftAvatar" alt="头像预览" /><template v-else>{{ profileDraftName.trim().slice(0, 1) || '邮' }}</template></span><div class="profile-fields"><label>昵称<input v-model="profileDraftName" maxlength="20" placeholder="该怎么称呼你" @input="profileEditError = ''" /></label><div class="avatar-upload-actions"><label class="secondary-button file-button"><IconGlyph name="upload" :size="16" />上传头像<input type="file" accept="image/png,image/jpeg,image/webp" @change="selectAvatarFile" /></label><button v-if="profileDraftAvatar" class="text-button" type="button" @click="clearAvatarDraft">移除头像</button><small>PNG、JPG 或 WebP，不超过 2 MB</small></div><p v-if="profileEditError" class="inline-error" role="alert">{{ profileEditError }}</p></div><button class="secondary-button" type="button" @click="saveProfile">保存资料</button></div></article>
          <article class="settings-section surface"><div><h2>外观</h2><p>选择适合当前设备的显示模式。</p></div><div class="segmented"><button v-for="option in [{id:'system',label:'跟随系统'},{id:'light',label:'浅色'},{id:'dark',label:'深色'}]" :key="option.id" type="button" :class="{ active: preferences.theme === option.id }" @click="preferences.theme = option.id as Preferences['theme']">{{ option.label }}</button></div></article>
          <article class="settings-section surface"><div><h2>默认提醒</h2><p>任务可选择分钟、小时或天；0 表示到点提醒，最长提前 7 天。</p></div><label>任务提前<div class="reminder-control"><input v-model.number="defaultTaskReminderValue" type="number" min="0" :max="defaultTaskReminderUnit === 'days' ? 7 : defaultTaskReminderUnit === 'hours' ? 168 : 10080" step="1" /><select v-model="defaultTaskReminderUnit" aria-label="任务提醒单位"><option value="minutes">分钟</option><option value="hours">小时</option><option value="days">天</option></select></div></label><label>课程提前<div class="number-with-unit"><input v-model.number="preferences.courseReminder" type="number" min="0" max="10080" step="1" /><span>分钟</span></div></label></article>
          <article class="settings-section surface course-settings"><div><h2>课程表</h2><p>清空当前课表中的全部课程，操作需要再次点击确认。</p></div><button class="danger-button" :class="{ confirming: courseClearConfirming }" type="button" @click="clearCourses">{{ courseClearConfirming ? '再次点击确认清空' : '清空课表' }}</button></article>
          <article class="settings-section surface"><div><h2>学期课表</h2><p>第 1 周周一，用于计算周次和每天的日期。</p></div><label>学期开始<input v-model="preferences.semesterStart" type="date" /></label></article>
          <article class="settings-section surface"><div><h2>静默时段</h2><p>默认不弹出提醒；只有任务中勾选“静默时段仍提醒”的事项例外。</p></div><label>开始<input v-model="preferences.quietStart" type="time" /></label><label>结束<input v-model="preferences.quietEnd" type="time" /></label></article>
          <article class="settings-section surface privacy-settings"><div><h2>隐私</h2><p>控制助手如何使用你的数据。</p></div><div class="switch-row"><span><strong>浏览器通知</strong><small>提醒时播放声音，并在页面打开时显示 Windows 系统通知</small></span><input v-model="preferences.browserNotifications" type="checkbox" role="switch" aria-label="浏览器通知" @change="handleBrowserNotificationsChange" /></div><div class="switch-row"><span><strong>个性化记忆</strong><small>允许助手参考当前对话的历史消息与称呼</small></span><input v-model="preferences.memoryEnabled" type="checkbox" role="switch" aria-label="个性化记忆" /></div><div class="switch-row"><span><strong>学习数据分析</strong><small>允许助手和“现在做什么”分析本地课程、任务与学习节奏</small></span><input v-model="preferences.analyticsEnabled" type="checkbox" role="switch" aria-label="学习数据分析" /></div></article>
          <article class="settings-section surface danger-zone"><div><h2>重置个人信息</h2><p>清除本浏览器中的昵称、头像、任务、课表、设置、已读与订阅状态。</p></div><button class="danger-button" :class="{ confirming: resetConfirming }" type="button" @click="resetAllPersonalData">{{ resetConfirming ? '确认永久重置' : '重置所有个人信息' }}</button></article>
        </section>
      </main>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航"><button v-for="item in navItems" :key="item.id" type="button" :class="{ active: currentPage === item.id }" @click="navigate(item.id)"><IconGlyph :name="item.icon" /><span>{{ item.label }}</span></button><button type="button" :class="{ active: currentPage === 'notifications' }" @click="navigate('notifications')"><IconGlyph name="bell" /><span>通知</span></button><button type="button" :class="{ active: currentPage === 'settings' }" @click="navigate('settings')"><IconGlyph name="settings" /><span>设置</span></button></nav>

    <div v-if="taskModalOpen" class="modal-backdrop" @click.self="taskModalOpen = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="task-modal-title"><header><div><span class="eyebrow">新建</span><h2 id="task-modal-title">添加任务</h2></div><button class="icon-button" type="button" aria-label="关闭" @click="taskModalOpen = false"><IconGlyph name="close" /></button></header><form @submit.prevent="createTask"><label>任务内容<input v-model="taskForm.title" autofocus placeholder="例如：完成软件工程需求分析" /></label><div class="form-grid"><label>课程或分类<input v-model="taskForm.course" placeholder="个人计划" /></label><label>截止时间<input v-model="taskForm.dueAt" type="datetime-local" /></label></div><label>提前提醒（分钟）<input v-model.number="taskForm.reminderMinutes" type="number" min="0" max="10080" step="1" placeholder="0 表示到点提醒" /></label><label class="switch-row modal-switch"><span><strong>静默时段仍提醒</strong><small>仅为确实不能错过的任务开启</small></span><input v-model="taskForm.remindDuringQuiet" type="checkbox" role="switch" /></label><footer><button class="secondary-button" type="button" @click="taskModalOpen = false">取消</button><button class="primary-button" type="submit">添加任务</button></footer></form></section>
    </div>

    <div v-if="courseAddOpen" class="modal-backdrop" @click.self="courseAddOpen = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="course-add-modal-title"><header><div><span class="eyebrow">新建课程</span><h2 id="course-add-modal-title">添加课程</h2></div><button class="icon-button" type="button" aria-label="关闭" @click="courseAddOpen = false"><IconGlyph name="close" /></button></header><form class="course-edit-form" @submit.prevent="createCourse"><label>课程名<input v-model="courseForm.name" autofocus placeholder="例如：高等数学" /></label><div class="form-grid"><label>教师<input v-model="courseForm.teacher" placeholder="未填写" /></label><label>地点<input v-model="courseForm.location" placeholder="待定" /></label></div><div class="form-grid"><label>星期<select v-model.number="courseForm.weekday"><option v-for="(day,index) in weekdayOptions" :key="day" :value="index + 1">周{{ day }}</option></select></label><label>周次<input v-model="courseForm.weeks" placeholder="1-2，4-10" inputmode="numeric" /></label></div><div class="form-grid"><label>开始节次<input v-model.number="courseForm.startSection" type="number" min="1" max="20" /></label><label>结束节次<input v-model.number="courseForm.endSection" type="number" min="1" max="20" /></label></div><label>提前提醒（分钟）<input v-model.number="courseForm.reminderMinutes" type="number" min="0" max="10080" step="1" /></label><footer><button class="secondary-button" type="button" @click="courseAddOpen = false">取消</button><button class="primary-button" type="submit">添加课程</button></footer></form></section>
    </div>

    <div v-if="courseImportOpen" class="modal-backdrop" @click.self="courseImportOpen = false">
      <section class="modal import-modal" role="dialog" aria-modal="true" aria-labelledby="import-modal-title">
        <header><div><span class="eyebrow">步骤 {{ importStep }} / 3</span><h2 id="import-modal-title">导入课表</h2></div><button class="icon-button" type="button" aria-label="关闭" @click="courseImportOpen = false"><IconGlyph name="close" /></button></header>
        <div class="step-indicator"><span v-for="step in 3" :key="step" :class="{ active: step <= importStep }" /></div>
        <div v-if="importStep === 1" class="import-body">
          <div class="import-options"><button type="button" :class="{ active: importMode === 'class' }" @click="importMode = 'class'; importError = ''"><IconGlyph name="book" :size="24" /><strong>按班级导入</strong><span>使用已配置的教务系统会话读取</span></button><button type="button" :class="{ active: importMode === 'file' }" @click="importMode = 'file'; importError = ''"><IconGlyph name="upload" :size="24" /><strong>上传课表文件</strong><span>浏览器本地解析 XLS/XLSX/CSV</span></button></div>
          <label v-if="importMode === 'class'">班级号<input v-model="importClassId" placeholder="请输入完整班级号" /></label>
          <label v-else class="file-drop"><IconGlyph name="upload" :size="26" /><strong>{{ importFile?.name || '选择课表文件' }}</strong><span>{{ importPreview.length ? `已识别 ${importPreview.length} 门课程` : '文件只在本机解析，不会上传到第三方' }}</span><input type="file" accept=".xls,.xlsx,.csv" @change="selectImportFile" /></label>
          <p v-if="importError" class="form-error" role="alert">{{ importError }}</p>
        </div>
        <div v-else-if="importStep === 2" class="import-preview"><div class="preview-stat"><strong>{{ importPreview.length }}</strong><span>识别课程</span></div><div class="preview-stat"><strong>{{ selectedImportCourses.length }}</strong><span>已勾选</span></div><div class="preview-stat warning"><strong>{{ selectedImportCourses.filter(item => courses.some(course => course.name === item.name && course.weekday === item.weekday && course.startSection === item.startSection)).length }}</strong><span>将更新</span></div><div class="import-course-list"><label v-for="(item, index) in importPreview" :key="`${item.name}-${item.weekday}-${item.startSection}-${index}`" class="import-course-item"><span><b>{{ item.name }}</b>{{ weekdays[item.weekday - 1] ?? `周${item.weekday}` }} 第 {{ item.startSection }}–{{ item.endSection }} 节</span><input v-model="importSelections[index]" type="checkbox" :aria-label="`选择导入${item.name}`" /></label></div></div>
        <div v-else class="import-finish"><span class="success-icon"><IconGlyph name="check" :size="28" /></span><h3>预览完成</h3><template v-if="courses.length"><p>当前已有 {{ courses.length }} 门课程。请选择新课表的处理方式：</p><div class="import-strategy" role="radiogroup" aria-label="新课表处理方式"><label :class="{ active: importStrategy === 'replace' }"><input v-model="importStrategy" type="radio" value="replace" /><span><strong>替换原课表</strong><small>清空现有课程后写入新课表</small></span></label><label :class="{ active: importStrategy === 'merge' }"><input v-model="importStrategy" type="radio" value="merge" /><span><strong>合并课表</strong><small>保留原课程并更新重复课程</small></span></label></div></template><p v-if="selectedImportCourses.length">确认后会把已勾选的 {{ selectedImportCourses.length }} 门课程写入你的课表。</p><p v-else>请至少勾选一门课程后再确认导入。</p></div>
        <footer><button class="secondary-button" type="button" :disabled="importBusy" @click="importStep === 1 ? courseImportOpen = false : importStep--">{{ importStep === 1 ? '取消' : '上一步' }}</button><button class="primary-button" type="button" :disabled="importBusy || (importStep === 3 && !selectedImportCourses.length)" @click="advanceImport">{{ importBusy ? '正在读取…' : importStep === 3 ? `确认导入 ${selectedImportCourses.length} 门` : '下一步' }}</button></footer>
      </section>
    </div>

    <div v-if="selectedCourse" class="drawer-backdrop" @click.self="selectedCourse = null">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="课程详情">
        <header><span class="course-detail-mark" :class="`course-${selectedCourse.color}`" /><button class="icon-button" type="button" aria-label="关闭" @click="selectedCourse = null"><IconGlyph name="close" /></button></header>
        <template v-if="!courseEditing"><span class="eyebrow">{{ weekdays[selectedCourse.weekday - 1] ?? `周${selectedCourse.weekday}` }} · 第 {{ selectedCourse.startSection }}–{{ selectedCourse.endSection }} 节</span><h2>{{ selectedCourse.name }}</h2><div class="detail-list"><div><IconGlyph name="clock" /><span><small>上课时间</small><strong>{{ selectedCourse.startTime }}–{{ selectedCourse.endTime }}</strong></span></div><div><IconGlyph name="map" /><span><small>地点</small><strong>{{ selectedCourse.location }}</strong></span></div><div><IconGlyph name="book" /><span><small>教师与周次</small><strong>{{ selectedCourse.teacher }} · {{ selectedCourse.weeks }}</strong></span></div><div><IconGlyph name="bell" /><span><small>提醒</small><strong>{{ formatReminder(selectedCourse.reminderMinutes) }}</strong></span></div></div><button class="primary-button full" type="button" @click="startCourseEdit">编辑课程</button></template>
        <form v-else class="course-edit-form" @submit.prevent="saveCourse"><span class="eyebrow">编辑课程</span><label>课程名<input v-model="courseForm.name" autofocus /></label><div class="form-grid"><label>教师<input v-model="courseForm.teacher" /></label><label>地点<input v-model="courseForm.location" /></label></div><div class="form-grid"><label>星期<select v-model.number="courseForm.weekday"><option v-for="(day,index) in weekdayOptions" :key="day" :value="index + 1">{{ day }}</option></select></label><label>周次<input v-model="courseForm.weeks" placeholder="1-2，4-10" inputmode="numeric" /></label></div><div class="form-grid"><label>开始节次<input v-model.number="courseForm.startSection" type="number" min="1" max="20" /></label><label>结束节次<input v-model.number="courseForm.endSection" type="number" min="1" max="20" /></label></div><label>提前提醒（分钟）<input v-model.number="courseForm.reminderMinutes" type="number" min="0" max="10080" step="1" /></label><button class="danger-button course-delete-button" :class="{ confirming: courseDeleteConfirming }" type="button" @click="deleteSelectedCourse">{{ courseDeleteConfirming ? '确认删除课程' : '删除课程' }}</button><footer><button class="secondary-button" type="button" @click="courseEditing = false; courseDeleteConfirming = false">取消</button><button class="primary-button" type="submit">保存修改</button></footer></form>
      </aside>
    </div>

    <div v-if="selectedCampusItem" class="modal-backdrop" @click.self="selectedCampusItem = null"><section class="modal campus-detail" role="dialog" aria-modal="true" aria-label="校园信息详情"><header><span class="category-chip">{{ selectedCampusItem.category }}</span><button class="icon-button" type="button" aria-label="关闭" @click="selectedCampusItem = null"><IconGlyph name="close" /></button></header><h2>{{ selectedCampusItem.title }}</h2><div v-if="campusSummaryBusy" class="summary-loading"><IconGlyph name="assistant" /><span>AI 正在阅读官方通知并生成总结…</span></div><p v-else-if="selectedCampusItem.summary">{{ selectedCampusItem.summary }}</p><p v-else-if="campusSummaryError" class="form-error" role="alert">{{ campusSummaryError }}</p><p v-else>该条目暂时没有可显示的简介。</p><dl><div><dt>来源</dt><dd>{{ selectedCampusItem.source }}</dd></div><div><dt>发布时间</dt><dd>{{ formatDateTime(selectedCampusItem.publishedAt) }}</dd></div><div v-if="selectedCampusItem.eventTime"><dt>活动时间</dt><dd>{{ formatDateTime(selectedCampusItem.eventTime) }}</dd></div></dl><footer><button class="secondary-button" type="button" @click="toggleCampusSubscription(selectedCampusItem)">{{ selectedCampusItem.subscribed ? '取消订阅' : '订阅更新' }}</button><a class="primary-button" :href="selectedCampusItem.url" target="_blank" rel="noopener noreferrer"><IconGlyph name="external" />查看原文</a></footer></section></div>

    <div v-if="!profileName" class="welcome-screen"><div ref="welcomeOrbsContainer" class="welcome-orbs" aria-hidden="true"><span v-for="orb in welcomeOrbs" :key="orb.id" :style="{ width: `${orb.radius * 2}px`, height: `${orb.radius * 2}px`, '--orb-hue': String(orb.hue), transform: `translate3d(${orb.x - orb.radius}px, ${orb.y - orb.radius}px, 0)` }" /></div><section class="welcome-card" role="dialog" aria-modal="true" aria-labelledby="welcome-title"><span class="brand-mark">邮</span><span class="eyebrow">北邮人的学习与生活助手</span><h1 id="welcome-title">欢迎使用邮学伴</h1><p>课程、任务、校园信息和 AI 助手都在这里。开始前，想先知道该怎么称呼你。</p><form @submit.prevent="completeWelcome"><label for="welcome-name">你的称呼</label><input id="welcome-name" v-model="welcomeName" autofocus maxlength="20" placeholder="例如：小林、林同学" @input="welcomeError = ''" /><small v-if="welcomeError" class="form-error" role="alert">{{ welcomeError }}</small><button class="primary-button" type="submit">开始使用</button></form><small>称呼只保存在这台设备的浏览器中，可随时清除。</small></section></div>

    <Transition name="toast"><div v-if="toast" class="toast" role="status"><IconGlyph name="check" />{{ toast }}</div></Transition>
  </div>
</template>
