<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import IconGlyph from "./components/IconGlyph.vue";
import { courseTimes, normalizeImportedCourses, parseCourseFile, type ImportedCourse } from "./course-import";
import { demoCampusItems, demoCourses, demoNotifications, demoTasks } from "./demo-data";
import type {
  AssistantMessage,
  CampusItem,
  Course,
  PageId,
  Preferences,
  StudyTask,
} from "./types";

const STORAGE_KEY = "youxueban-demo-state-v1";
const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const sectionRows = [
  { key: 1, label: "1–2", time: "08:00" },
  { key: 3, label: "3–4", time: "09:50" },
  { key: 5, label: "5–6", time: "11:30" },
  { key: 7, label: "7–8", time: "14:20" },
  { key: 9, label: "9–10", time: "16:10" },
  { key: 11, label: "11–12", time: "18:30" },
  { key: 13, label: "13–14", time: "20:10" },
];
const navItems: Array<{ id: PageId; label: string; icon: string }> = [
  { id: "today", label: "今天", icon: "today" },
  { id: "tasks", label: "任务", icon: "tasks" },
  { id: "courses", label: "课程", icon: "courses" },
  { id: "campus", label: "校园", icon: "campus" },
  { id: "assistant", label: "助手", icon: "assistant" },
];

const defaultPreferences: Preferences = {
  theme: "system",
  courseReminder: 20,
  defaultTaskReminder: 60,
  quietStart: "23:00",
  quietEnd: "07:00",
  browserNotifications: true,
  memoryEnabled: true,
  analyticsEnabled: true,
};

const saved = (() => {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<{
      tasks: StudyTask[];
      courses: Course[];
      campusItems: CampusItem[];
      notifications: typeof demoNotifications;
      preferences: Preferences;
    }>;
  } catch {
    return {};
  }
})();

const currentPage = ref<PageId>("today");
const tasks = ref<StudyTask[]>(saved.tasks ?? demoTasks);
const courses = ref<Course[]>(saved.courses ?? demoCourses);
const campusItems = ref<CampusItem[]>((saved.campusItems ?? demoCampusItems).map((item) => ({
  ...item,
  url: item.url || campusSourceUrl(item.source),
})));
const notifications = ref(saved.notifications ?? demoNotifications);
const preferences = ref<Preferences>({ ...defaultPreferences, ...saved.preferences });
const toast = ref("");
const taskModalOpen = ref(false);
const courseImportOpen = ref(false);
const importStep = ref(1);
const importMode = ref<"class" | "file">("class");
const importClassId = ref("");
const importFile = ref<File | null>(null);
const importPreview = ref<ImportedCourse[]>([]);
const importError = ref("");
const importBusy = ref(false);
const selectedCourse = ref<Course | null>(null);
const courseEditing = ref(false);
const courseForm = ref<Omit<Course, "id">>({ ...demoCourses[0]! });
const selectedCampusItem = ref<CampusItem | null>(null);
const taskFilter = ref<"todo" | "all" | "done">("todo");
const taskSearch = ref("");
const campusTab = ref<"notice" | "activity">("notice");
const campusSearch = ref("");
const assistantInput = ref("");
const assistantBusy = ref(false);
const assistantMode = ref<"unknown" | "online" | "local">("unknown");
const deleteConfirmId = ref<number | null>(null);
const taskForm = ref({ title: "", course: "", dueAt: "", reminderMinutes: 60 });
const assistantMessages = ref<AssistantMessage[]>([
  {
    id: 1,
    role: "assistant",
    content: "早上好。我可以帮你查课程、整理 DDL、搜索校园通知，也可以直接用自然语言新增任务。",
    createdAt: new Date().toISOString(),
  },
]);

const now = new Date();
const todayWeekday = now.getDay() || 7;
const dateHeading = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
}).format(now);
const pageTitle = computed(() => ({
  today: "今天",
  tasks: "任务",
  courses: "课程",
  campus: "校园",
  assistant: "学习助手",
  notifications: "通知中心",
  settings: "设置",
})[currentPage.value]);
const unreadCount = computed(() => notifications.value.filter((item) => !item.read).length);
const todoTasks = computed(() => tasks.value.filter((task) => task.status === "todo").sort((a, b) => a.dueAt.localeCompare(b.dueAt)));
const todayCourses = computed(() => courses.value.filter((course) => course.weekday === todayWeekday).sort((a, b) => a.startSection - b.startSection));
const nextCourse = computed(() => todayCourses.value[0] ?? courses.value[0] ?? null);
const filteredTasks = computed(() => {
  const query = taskSearch.value.trim().toLowerCase();
  return tasks.value
    .filter((task) => taskFilter.value === "all" || task.status === taskFilter.value)
    .filter((task) => !query || `${task.title} ${task.course}`.toLowerCase().includes(query))
    .sort((a, b) => a.dueAt.localeCompare(b.dueAt));
});
const filteredCampusItems = computed(() => {
  const query = campusSearch.value.trim().toLowerCase();
  return campusItems.value
    .filter((item) => item.kind === campusTab.value)
    .filter((item) => !query || `${item.title} ${item.summary} ${item.category}`.toLowerCase().includes(query));
});

watch([tasks, courses, campusItems, notifications, preferences], () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    tasks: tasks.value,
    courses: courses.value,
    campusItems: campusItems.value,
    notifications: notifications.value,
    preferences: preferences.value,
  }));
}, { deep: true });

watch(() => preferences.value.theme, applyTheme, { immediate: true });

onMounted(() => {
  const hash = location.hash.replace("#/", "") as PageId;
  if ([...navItems.map((item) => item.id), "notifications", "settings"].includes(hash)) currentPage.value = hash;
});

function applyTheme(): void {
  const theme = preferences.value.theme;
  document.documentElement.dataset.theme = theme === "system" ? "" : theme;
}

function campusSourceUrl(source: string): string {
  if (source.includes("教务")) return "https://jwc.bupt.edu.cn/";
  if (source.includes("学生工作")) return "https://xsc.bupt.edu.cn/";
  if (source.includes("图书馆")) return "https://lib.bupt.edu.cn/";
  if (source.includes("第二课堂")) return "https://dekt.bupt.edu.cn/";
  return "https://www.bupt.edu.cn/";
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
    status: "todo",
    createdAt: new Date().toISOString(),
  });
  taskModalOpen.value = false;
  showToast("任务已添加");
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

function courseAt(day: number, section: number): Course | undefined {
  return courses.value.find((course) => course.weekday === day && course.startSection === section);
}

function openImport(): void {
  importStep.value = 1;
  importFile.value = null;
  importPreview.value = [];
  importError.value = "";
  courseImportOpen.value = true;
}

async function selectImportFile(event: Event): Promise<void> {
  importFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  importPreview.value = [];
  importError.value = "";
  if (!importFile.value) return;
  importBusy.value = true;
  try {
    importPreview.value = await parseCourseFile(importFile.value);
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
    importPreview.value = normalizeImportedCourses(payload.courses);
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
  const colors: Course["color"][] = ["blue", "violet", "green", "orange"];
  let nextId = Math.max(0, ...courses.value.map((course) => course.id)) + 1;
  for (const [index, imported] of importPreview.value.entries()) {
    const existing = courses.value.find((course) => course.name === imported.name
      && course.weekday === imported.weekday
      && course.startSection === imported.startSection
      && course.endSection === imported.endSection);
    if (existing) Object.assign(existing, imported);
    else courses.value.push({ ...imported, id: nextId++, reminderMinutes: preferences.value.courseReminder, color: colors[index % colors.length]! });
  }
  courseImportOpen.value = false;
  showToast(`课表导入完成，共写入 ${importPreview.value.length} 门课程`);
}

function startCourseEdit(): void {
  if (!selectedCourse.value) return;
  const { id: _id, ...editable } = selectedCourse.value;
  courseForm.value = { ...editable };
  courseEditing.value = true;
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
  const reminder = Math.max(0, Math.min(10080, Number(courseForm.value.reminderMinutes) || 0));
  Object.assign(selectedCourse.value, {
    ...courseForm.value,
    name,
    teacher: courseForm.value.teacher.trim() || "未填写",
    location: courseForm.value.location.trim() || "待定",
    startSection: start,
    endSection: end,
    reminderMinutes: reminder,
    ...courseTimes(start, end),
  });
  courseEditing.value = false;
  showToast("课程修改已保存");
}

function openCampusItem(item: CampusItem): void {
  item.read = true;
  selectedCampusItem.value = item;
}

function toggleCampusSubscription(item: CampusItem): void {
  item.subscribed = !item.subscribed;
  showToast(item.subscribed ? "已订阅，后续更新会通知你" : "已取消订阅");
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
  if (!text || assistantBusy.value) return;
  assistantInput.value = "";
  assistantMessages.value.push({ id: Date.now(), role: "user", content: text, createdAt: new Date().toISOString() });
  assistantBusy.value = true;
  try {
    const response = await fetch("/api/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: assistantMessages.value.slice(-12).map(({ role, content }) => ({ role, content })),
        context: {
          courses: courses.value.map(({ name, weekday, startSection, endSection, location, teacher, weeks }) => ({ name, weekday, startSection, endSection, location, teacher, weeks })),
          tasks: todoTasks.value.map(({ title, course, dueAt }) => ({ title, course, dueAt })),
          campus: campusItems.value.slice(0, 12).map(({ category, title, summary, publishedAt }) => ({ category, title, summary, publishedAt })),
        },
      }),
    });
    const payload = await response.json() as { reply?: string };
    if (!response.ok || !payload.reply) throw new Error("online-unavailable");
    assistantMode.value = "online";
    assistantMessages.value.push({ id: Date.now() + 1, role: "assistant", content: payload.reply, createdAt: new Date().toISOString() });
  } catch {
    assistantMode.value = "local";
    await new Promise((resolve) => window.setTimeout(resolve, 260));
    assistantMessages.value.push(buildAssistantReply(text));
  } finally {
    assistantBusy.value = false;
  }
}

function buildAssistantReply(text: string): AssistantMessage {
  const normalized = text.toLowerCase();
  const base = { id: Date.now() + 1, role: "assistant" as const, createdAt: new Date().toISOString() };
  const weekdayNames: Record<string, number> = { 周一: 1, 星期一: 1, 周二: 2, 星期二: 2, 周三: 3, 星期三: 3, 周四: 4, 星期四: 4, 周五: 5, 星期五: 5, 周六: 6, 星期六: 6, 周日: 7, 星期日: 7, 星期天: 7 };
  const requestedDay = Object.entries(weekdayNames).find(([name]) => text.includes(name))?.[1];
  if (text.includes("课") || text.includes("课程") || text.includes("课表")) {
    const day = text.includes("明天") ? ((new Date().getDay() || 7) % 7) + 1 : requestedDay ?? (text.includes("今天") ? todayWeekday : null);
    const matching = day ? courses.value.filter((course) => course.weekday === day).sort((a, b) => a.startSection - b.startSection) : courses.value.slice().sort((a, b) => a.weekday - b.weekday || a.startSection - b.startSection);
    const content = matching.length
      ? `${day ? weekdays[day - 1] ?? `星期${day}` : "本周"}有 ${matching.length} 条课程安排：\n${matching.slice(0, 8).map((course) => `${weekdays[course.weekday - 1] ?? `星期${course.weekday}`} ${course.startTime} ${course.name}，${course.location}`).join("\n")}`
      : "这一天没有课程，可以安排自习或处理近期 DDL。";
    return { ...base, content, action: { type: "navigate", label: "查看完整课表", payload: { page: "courses" } } };
  }
  const wantsCreate = /(添加|新增|记一下|提醒我|创建)/.test(text) && /(截止|到期|提交|报告|作业|任务|复习)/.test(text);
  if (normalized.includes("ddl") || text.includes("任务") || text.includes("作业") || wantsCreate) {
    if (wantsCreate) {
      const title = text.replace(/(帮我|请|添加|新增|一个|ddl|DDL|任务|记一下|提醒我|创建|明天|明晚|后天|今晚|今天|周[一二三四五六日天]|星期[一二三四五六日天]|截止|到期|在|前)/g, " ").replace(/\s+/g, " ").trim() || "新的学习任务";
      const due = new Date();
      if (text.includes("后天")) due.setDate(due.getDate() + 2);
      else if (text.includes("明天") || text.includes("明晚")) due.setDate(due.getDate() + 1);
      else if (requestedDay) due.setDate(due.getDate() + ((requestedDay - (due.getDay() || 7) + 7) % 7 || 7));
      const explicitHour = /(\d{1,2})\s*[点时]/.exec(text)?.[1];
      due.setHours(explicitHour ? Math.min(23, Number(explicitHour)) : text.includes("上午") ? 10 : 20, 0, 0, 0);
      return {
        ...base,
        content: `我理解为：新增“${title}”，截止时间 ${formatDateTime(due.toISOString())}。确认后再写入任务列表。`,
        action: { type: "create-task", label: "确认添加任务", payload: { title, dueAt: due.toISOString() } },
      };
    }
    const items = todoTasks.value.slice(0, 4);
    return {
      ...base,
      content: items.length
        ? `你有 ${todoTasks.value.length} 项待完成任务，最近的是：\n${items.map((task) => `${formatDateTime(task.dueAt)} · ${task.title}`).join("\n")}`
        : "目前没有待完成任务。",
      action: { type: "navigate", label: "进入任务页", payload: { page: "tasks" } },
    };
  }
  if (text.includes("通知") || text.includes("讲座") || text.includes("活动") || text.includes("奖学金")) {
    const keyword = text.includes("讲座") ? "讲座" : text.includes("奖学金") ? "奖学金" : "";
    const matches = campusItems.value.filter((item) => !keyword || `${item.category}${item.title}${item.summary}`.includes(keyword)).slice(0, 3);
    return {
      ...base,
      content: `找到 ${matches.length} 条相关校园信息：\n${matches.map((item) => `${item.category} · ${item.title}`).join("\n")}`,
      action: { type: "navigate", label: "查看校园信息", payload: { page: "campus" } },
    };
  }
  if (/(安排|计划|规划|怎么学|复习)/.test(text)) {
    const nearest = todoTasks.value[0];
    return { ...base, content: nearest
      ? `可以。建议先处理最临近的“${nearest.title}”（${formatDateTime(nearest.dueAt)} 截止），把它拆成“明确要求—完成主体—检查提交”三段；每段专注 25–40 分钟，中间休息 5 分钟。你也可以告诉我今晚可用多久，我再细化。`
      : "可以。先告诉我可用时长和目标，我会按“必须完成、最好完成、有余力再做”三层帮你排计划。目前任务列表里没有待办。" };
  }
  if (/(考试|不会|难|焦虑|来不及)/.test(text)) {
    return { ...base, content: `我理解你在担心“${text.slice(0, 36)}”。先别一次解决全部：列出最不确定的 3 个知识点，选一个做 20 分钟例题，再用 5 分钟写下卡住的位置。告诉我具体课程或题型，我可以继续帮你拆解。` };
  }
  if (/^(你好|您好|嗨|hello|hi)/i.test(text)) {
    return { ...base, content: `你好！现在有 ${todoTasks.value.length} 项待完成任务、${courses.value.length} 条课程安排。你可以直接告诉我想查什么，或者让我帮你拆解一项学习计划。` };
  }
  return { ...base, content: `我收到了：“${text.slice(0, 60)}”。当前是本地助手模式，我能结合本页的课程、任务和校园数据继续处理；如果这是一个学习目标，请补充截止时间或可用时长，我会给出具体安排。配置后端 AI 凭据后，也可以直接进行开放式问答。` };
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
      status: "todo",
      createdAt: new Date().toISOString(),
    });
    action.completed = true;
    showToast("任务已由助手添加");
  }
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <button class="brand" type="button" aria-label="返回今天" @click="navigate('today')">
        <span class="brand-mark">邮</span>
        <span><strong>邮学伴</strong><small>北邮人的学习助手</small></span>
      </button>
      <nav class="side-nav" aria-label="主导航">
        <button v-for="item in navItems" :key="item.id" type="button" :class="{ active: currentPage === item.id }" @click="navigate(item.id)">
          <IconGlyph :name="item.icon" /> <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-spacer" />
      <button class="sidebar-status" type="button" @click="navigate('notifications')">
        <span class="status-dot" /><span><strong>提醒服务正常</strong><small>{{ unreadCount }} 条未读通知</small></span>
      </button>
      <button class="sidebar-settings" type="button" :class="{ active: currentPage === 'settings' }" @click="navigate('settings')"><IconGlyph name="settings" />设置</button>
    </aside>

    <div class="app-main">
      <header class="topbar">
        <strong>{{ pageTitle }}</strong>
        <div class="top-actions">
          <button class="icon-button notification-button" type="button" aria-label="打开通知中心" @click="navigate('notifications')">
            <IconGlyph name="bell" /><span v-if="unreadCount" class="notification-count">{{ unreadCount }}</span>
          </button>
          <button class="profile-button" type="button" @click="navigate('settings')"><span class="avatar">林</span><span class="profile-text">林同学<small>本科生</small></span></button>
        </div>
      </header>

      <main class="page-container">
        <section v-if="currentPage === 'today'" class="page page-today">
          <header class="page-heading"><span class="eyebrow">{{ dateHeading }}</span><h1>早上好，先把今天安排清楚。</h1><p>第 1 周 · 西土城校区</p></header>
          <div class="today-layout">
            <div class="content-stack">
              <article class="surface course-overview">
                <div class="surface-heading"><h2>下一节课</h2><button class="text-button" type="button" @click="navigate('courses')">查看周课表 <IconGlyph name="arrow-right" :size="15" /></button></div>
                <div v-if="nextCourse" class="next-course-card">
                  <div class="time-block"><strong>{{ nextCourse.startTime }}</strong><span>第 {{ nextCourse.startSection }}–{{ nextCourse.endSection }} 节</span></div>
                  <div class="next-course-main"><strong>{{ nextCourse.name }}</strong><span>{{ nextCourse.location }} · {{ nextCourse.teacher }}</span></div>
                  <span class="countdown">今天的课程</span>
                </div>
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
              <article class="surface suggestion-card"><div class="surface-heading"><h2>现在做什么</h2><span>根据空闲时间推荐</span></div><p>离下节课还有一段时间，可以先整理“软件工程需求分析”的用例清单。</p><button class="text-button" type="button" @click="showToast('已经换了一条更轻松的建议')">换一个建议</button></article>
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
              <div class="task-body"><strong>{{ task.title }}</strong><span><b>{{ task.course }}</b><span class="dot-separator">·</span><IconGlyph name="bell" :size="13" /> {{ formatReminder(task.reminderMinutes) }}</span></div>
              <div class="task-due"><span :class="{ overdue: new Date(task.dueAt).getTime() < Date.now() && task.status === 'todo' }">{{ formatDateTime(task.dueAt) }}</span><small>{{ task.status === 'done' ? '已完成' : relativeDue(task.dueAt) }}</small></div>
              <button class="row-action danger" :class="{ confirming: deleteConfirmId === task.id }" type="button" :aria-label="deleteConfirmId === task.id ? '确认删除任务' : '删除任务'" @click="deleteTask(task)"><span v-if="deleteConfirmId === task.id">确认删除</span><IconGlyph v-else name="trash" /></button>
            </article>
            <div v-if="!filteredTasks.length" class="empty-state"><IconGlyph name="search" :size="28" /><strong>没有找到任务</strong><span>换个关键词，或新建一项任务。</span></div>
          </div>
        </section>

        <section v-else-if="currentPage === 'courses'" class="page">
          <header class="page-heading split"><div><span class="eyebrow">第 1 周</span><h1>本周课程</h1><p>点击课程查看周次、地点、教师和提醒设置。</p></div><button class="primary-button" type="button" @click="openImport"><IconGlyph name="upload" />导入课表</button></header>
          <div class="toolbar course-toolbar"><div class="week-switcher"><button class="icon-button" type="button" aria-label="上一周"><IconGlyph name="chevron-left" /></button><button class="secondary-button active" type="button">本周</button><button class="icon-button" type="button" aria-label="下一周"><IconGlyph name="chevron-right" /></button></div><span class="sync-status"><span class="status-dot" />课表已同步</span></div>
          <div class="schedule-wrap surface">
            <div class="schedule-grid">
              <div class="schedule-corner" /><div v-for="day in weekdays" :key="day" class="day-header">{{ day }}</div>
              <template v-for="row in sectionRows" :key="row.key">
                <div class="section-label"><strong>{{ row.label }}</strong><span>{{ row.time }}</span></div>
                <template v-for="day in 7" :key="`${row.key}-${day}`">
                  <button v-if="courseAt(day, row.key)" class="course-cell" :class="`course-${courseAt(day, row.key)?.color}`" type="button" @click="selectedCourse = courseAt(day, row.key) ?? null"><strong>{{ courseAt(day, row.key)?.name }}</strong><span>{{ courseAt(day, row.key)?.location }}</span><small>{{ courseAt(day, row.key)?.teacher }}</small></button>
                  <div v-else class="course-cell empty" />
                </template>
              </template>
            </div>
          </div>
          <div class="mobile-course-list surface"><article v-for="course in courses.slice().sort((a,b) => a.weekday-b.weekday || a.startSection-b.startSection)" :key="course.id"><time>{{ weekdays[course.weekday - 1] ?? `周${course.weekday}` }}<br>{{ course.startTime }}</time><span :class="`course-marker course-${course.color}`" /><button type="button" @click="selectedCourse = course; courseEditing = false"><strong>{{ course.name }}</strong><small>{{ course.location }} · {{ course.teacher }}</small></button></article></div>
        </section>

        <section v-else-if="currentPage === 'campus'" class="page">
          <header class="page-heading"><span class="eyebrow">校内信息</span><h1>校园</h1><p>统一查看信息门户通知与第二课堂活动。</p></header>
          <div class="toolbar"><div class="segmented"><button type="button" :class="{ active: campusTab === 'notice' }" @click="campusTab = 'notice'">校内通知</button><button type="button" :class="{ active: campusTab === 'activity' }" @click="campusTab = 'activity'">第二课堂</button></div><label class="search-field"><IconGlyph name="search" /><input v-model="campusSearch" placeholder="搜索标题、类别或内容" /></label></div>
          <div class="campus-grid">
            <article v-for="item in filteredCampusItems" :key="item.id" class="campus-card surface" :class="{ unread: !item.read }">
              <div class="campus-card-top"><span class="category-chip">{{ item.category }}</span><button class="subscribe-button" :class="{ subscribed: item.subscribed }" type="button" @click="toggleCampusSubscription(item)">{{ item.subscribed ? '已订阅' : '订阅' }}</button></div>
              <button class="campus-content" type="button" @click="openCampusItem(item)"><strong>{{ item.title }}</strong><p>{{ item.summary }}</p><span v-if="item.campus"><IconGlyph name="map" :size="14" />{{ item.campus }}校区</span><span v-if="item.eventTime"><IconGlyph name="clock" :size="14" />{{ formatDateTime(item.eventTime) }}</span></button>
              <footer><span>{{ item.source }}</span><time>{{ formatDateTime(item.publishedAt) }}</time></footer>
            </article>
          </div>
          <div v-if="!filteredCampusItems.length" class="empty-state surface"><IconGlyph name="search" :size="28" /><strong>没有匹配的信息</strong><span>尝试缩短关键词或切换栏目。</span></div>
        </section>

        <section v-else-if="currentPage === 'assistant'" class="page assistant-page">
          <header class="page-heading"><span class="eyebrow">AMADEUS · {{ assistantMode === 'online' ? '在线 AI' : assistantMode === 'local' ? '本地模式' : '自动连接' }}</span><h1>学习助手</h1><p>不用记命令，直接说出你要查询或完成的事情。</p></header>
          <div class="quick-prompts"><button v-for="prompt in ['我今天有什么课？','列出三天内的 DDL','最近有什么讲座？','帮我添加一个明晚截止的实验报告']" :key="prompt" type="button" @click="sendAssistant(prompt)">{{ prompt }}</button></div>
          <div class="chat-panel surface" aria-live="polite">
            <div v-for="message in assistantMessages" :key="message.id" class="message" :class="message.role">
              <span class="message-avatar">{{ message.role === 'assistant' ? 'A' : '林' }}</span>
              <div class="message-content"><p>{{ message.content }}</p><button v-if="message.action" class="inline-action" :disabled="message.action.completed" type="button" @click="runAssistantAction(message)"><IconGlyph :name="message.action.completed ? 'check' : 'arrow-right'" :size="15" />{{ message.action.completed ? '已完成' : message.action.label }}</button></div>
            </div>
            <div v-if="assistantBusy" class="message assistant"><span class="message-avatar">A</span><div class="message-content typing"><span /><span /><span /></div></div>
          </div>
          <form class="assistant-composer" @submit.prevent="sendAssistant()"><IconGlyph name="assistant" /><textarea v-model="assistantInput" rows="1" placeholder="例如：帮我添加一个周五晚上截止的课程报告" @keydown.enter.exact.prevent="sendAssistant()" /><button type="submit" :disabled="assistantBusy || !assistantInput.trim()" aria-label="发送"><IconGlyph name="send" /></button></form>
          <p class="assistant-note">{{ assistantMode === 'local' ? 'AI 服务未配置或暂不可用，已切换为可操作本页数据的本地助手。' : '涉及删除、覆盖或他人数据的操作会要求再次确认。' }}</p>
        </section>

        <section v-else-if="currentPage === 'notifications'" class="page narrow-page">
          <header class="page-heading split"><div><span class="eyebrow">消息中心</span><h1>通知</h1><p>课程、DDL 和校园订阅都集中在这里。</p></div><button class="secondary-button" type="button" @click="markAllNotificationsRead">全部已读</button></header>
          <div class="notification-list surface"><button v-for="item in notifications" :key="item.id" type="button" :class="{ unread: !item.read }" @click="item.read = true"><span class="notification-icon" :class="`type-${item.type}`"><IconGlyph :name="item.type === 'course' ? 'courses' : item.type === 'task' ? 'tasks' : 'campus'" /></span><span><strong>{{ item.title }}</strong><small>{{ item.body }}</small><time>{{ formatDateTime(item.createdAt) }}</time></span><span v-if="!item.read" class="unread-dot" /></button></div>
        </section>

        <section v-else class="page narrow-page settings-page">
          <header class="page-heading"><span class="eyebrow">个人偏好</span><h1>设置</h1><p>管理提醒、显示和隐私，不需要修改配置文件。</p></header>
          <article class="settings-section surface"><div><h2>外观</h2><p>选择适合当前设备的显示模式。</p></div><div class="segmented"><button v-for="option in [{id:'system',label:'跟随系统'},{id:'light',label:'浅色'},{id:'dark',label:'深色'}]" :key="option.id" type="button" :class="{ active: preferences.theme === option.id }" @click="preferences.theme = option.id as Preferences['theme']">{{ option.label }}</button></div></article>
          <article class="settings-section surface"><div><h2>默认提醒</h2><p>自由填写提前分钟数；0 表示到点提醒，最多 10080 分钟（7 天）。</p></div><label>任务提前<div class="number-with-unit"><input v-model.number="preferences.defaultTaskReminder" type="number" min="0" max="10080" step="1" /><span>分钟</span></div></label><label>课程提前<div class="number-with-unit"><input v-model.number="preferences.courseReminder" type="number" min="0" max="10080" step="1" /><span>分钟</span></div></label></article>
          <article class="settings-section surface"><div><h2>静默时段</h2><p>紧急 DDL 提醒仍会保留在通知中心。</p></div><label>开始<input v-model="preferences.quietStart" type="time" /></label><label>结束<input v-model="preferences.quietEnd" type="time" /></label></article>
          <article class="settings-section surface privacy-settings"><div><h2>隐私</h2><p>控制助手如何使用你的数据。</p></div><label class="switch-row"><span><strong>浏览器通知</strong><small>允许在页面关闭后接收提醒</small></span><input v-model="preferences.browserNotifications" type="checkbox" role="switch" /></label><label class="switch-row"><span><strong>个性化记忆</strong><small>使用已审核的长期偏好改善回答</small></span><input v-model="preferences.memoryEnabled" type="checkbox" role="switch" /></label><label class="switch-row"><span><strong>学习数据分析</strong><small>分析任务完成与学习节奏</small></span><input v-model="preferences.analyticsEnabled" type="checkbox" role="switch" /></label></article>
        </section>
      </main>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航"><button v-for="item in navItems" :key="item.id" type="button" :class="{ active: currentPage === item.id }" @click="navigate(item.id)"><IconGlyph :name="item.icon" /><span>{{ item.label }}</span></button></nav>

    <div v-if="taskModalOpen" class="modal-backdrop" @click.self="taskModalOpen = false">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="task-modal-title"><header><div><span class="eyebrow">新建</span><h2 id="task-modal-title">添加任务</h2></div><button class="icon-button" type="button" aria-label="关闭" @click="taskModalOpen = false"><IconGlyph name="close" /></button></header><form @submit.prevent="createTask"><label>任务内容<input v-model="taskForm.title" autofocus placeholder="例如：完成软件工程需求分析" /></label><div class="form-grid"><label>课程或分类<input v-model="taskForm.course" placeholder="个人计划" /></label><label>截止时间<input v-model="taskForm.dueAt" type="datetime-local" /></label></div><label>提前提醒（分钟）<input v-model.number="taskForm.reminderMinutes" type="number" min="0" max="10080" step="1" placeholder="0 表示到点提醒" /></label><footer><button class="secondary-button" type="button" @click="taskModalOpen = false">取消</button><button class="primary-button" type="submit">添加任务</button></footer></form></section>
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
        <div v-else-if="importStep === 2" class="import-preview"><div class="preview-stat"><strong>{{ importPreview.length }}</strong><span>识别课程</span></div><div class="preview-stat"><strong>{{ new Set(importPreview.map(item => item.weekday)).size }}</strong><span>有课日期</span></div><div class="preview-stat warning"><strong>{{ importPreview.filter(item => courses.some(course => course.name === item.name && course.weekday === item.weekday && course.startSection === item.startSection)).length }}</strong><span>将更新</span></div><div class="import-course-list"><span v-for="item in importPreview.slice(0, 8)" :key="`${item.name}-${item.weekday}-${item.startSection}`"><b>{{ item.name }}</b>{{ weekdays[item.weekday - 1] ?? `周${item.weekday}` }} 第 {{ item.startSection }}–{{ item.endSection }} 节</span></div></div>
        <div v-else class="import-finish"><span class="success-icon"><IconGlyph name="check" :size="28" /></span><h3>预览完成</h3><p>确认后会新增课程，并按“课程名 + 星期 + 节次”更新重复项。数据会保存在本浏览器中。</p></div>
        <footer><button class="secondary-button" type="button" :disabled="importBusy" @click="importStep === 1 ? courseImportOpen = false : importStep--">{{ importStep === 1 ? '取消' : '上一步' }}</button><button class="primary-button" type="button" :disabled="importBusy" @click="advanceImport">{{ importBusy ? '正在读取…' : importStep === 3 ? `确认导入 ${importPreview.length} 门` : '下一步' }}</button></footer>
      </section>
    </div>

    <div v-if="selectedCourse" class="drawer-backdrop" @click.self="selectedCourse = null">
      <aside class="drawer" role="dialog" aria-modal="true" aria-label="课程详情">
        <header><span class="course-detail-mark" :class="`course-${selectedCourse.color}`" /><button class="icon-button" type="button" aria-label="关闭" @click="selectedCourse = null"><IconGlyph name="close" /></button></header>
        <template v-if="!courseEditing"><span class="eyebrow">{{ weekdays[selectedCourse.weekday - 1] ?? `周${selectedCourse.weekday}` }} · 第 {{ selectedCourse.startSection }}–{{ selectedCourse.endSection }} 节</span><h2>{{ selectedCourse.name }}</h2><div class="detail-list"><div><IconGlyph name="clock" /><span><small>上课时间</small><strong>{{ selectedCourse.startTime }}–{{ selectedCourse.endTime }}</strong></span></div><div><IconGlyph name="map" /><span><small>地点</small><strong>{{ selectedCourse.location }}</strong></span></div><div><IconGlyph name="book" /><span><small>教师与周次</small><strong>{{ selectedCourse.teacher }} · {{ selectedCourse.weeks }}</strong></span></div><div><IconGlyph name="bell" /><span><small>提醒</small><strong>{{ formatReminder(selectedCourse.reminderMinutes) }}</strong></span></div></div><button class="primary-button full" type="button" @click="startCourseEdit">编辑课程</button></template>
        <form v-else class="course-edit-form" @submit.prevent="saveCourse"><span class="eyebrow">编辑课程</span><label>课程名<input v-model="courseForm.name" autofocus /></label><div class="form-grid"><label>教师<input v-model="courseForm.teacher" /></label><label>地点<input v-model="courseForm.location" /></label></div><div class="form-grid"><label>星期<select v-model.number="courseForm.weekday"><option v-for="(day,index) in weekdays" :key="day" :value="index + 1">{{ day }}</option></select></label><label>周次<input v-model="courseForm.weeks" placeholder="1-16 周" /></label></div><div class="form-grid"><label>开始节次<input v-model.number="courseForm.startSection" type="number" min="1" max="20" /></label><label>结束节次<input v-model.number="courseForm.endSection" type="number" min="1" max="20" /></label></div><label>提前提醒（分钟）<input v-model.number="courseForm.reminderMinutes" type="number" min="0" max="10080" step="1" /></label><footer><button class="secondary-button" type="button" @click="courseEditing = false">取消</button><button class="primary-button" type="submit">保存修改</button></footer></form>
      </aside>
    </div>

    <div v-if="selectedCampusItem" class="modal-backdrop" @click.self="selectedCampusItem = null"><section class="modal campus-detail" role="dialog" aria-modal="true" aria-label="校园信息详情"><header><span class="category-chip">{{ selectedCampusItem.category }}</span><button class="icon-button" type="button" aria-label="关闭" @click="selectedCampusItem = null"><IconGlyph name="close" /></button></header><h2>{{ selectedCampusItem.title }}</h2><p>{{ selectedCampusItem.summary }}</p><dl><div><dt>来源</dt><dd>{{ selectedCampusItem.source }}</dd></div><div><dt>发布时间</dt><dd>{{ formatDateTime(selectedCampusItem.publishedAt) }}</dd></div><div v-if="selectedCampusItem.eventTime"><dt>活动时间</dt><dd>{{ formatDateTime(selectedCampusItem.eventTime) }}</dd></div></dl><footer><button class="secondary-button" type="button" @click="toggleCampusSubscription(selectedCampusItem)">{{ selectedCampusItem.subscribed ? '取消订阅' : '订阅更新' }}</button><a class="primary-button" :href="selectedCampusItem.url" target="_blank" rel="noopener noreferrer"><IconGlyph name="external" />查看原文</a></footer></section></div>

    <Transition name="toast"><div v-if="toast" class="toast" role="status"><IconGlyph name="check" />{{ toast }}</div></Transition>
  </div>
</template>
