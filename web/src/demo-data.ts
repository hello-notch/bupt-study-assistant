import type { AppNotification, CampusItem, Course, StudyTask } from "./types";

const isoAt = (offsetDays: number, hour: number, minute = 0): string => {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  date.setHours(hour, minute, 0, 0);
  return date.toISOString();
};

export const demoTasks: StudyTask[] = [
  { id: 1, title: "提交软件工程需求分析", course: "软件工程", dueAt: isoAt(0, 20), reminderMinutes: 120, status: "todo", createdAt: isoAt(-4, 16) },
  { id: 2, title: "完成通信原理习题 2", course: "通信原理", dueAt: isoAt(1, 23), reminderMinutes: null, status: "todo", createdAt: isoAt(-3, 19) },
  { id: 3, title: "复习高数第三章", course: "个人计划", dueAt: isoAt(3, 19, 30), reminderMinutes: 30, status: "todo", createdAt: isoAt(-1, 21) },
  { id: 4, title: "提交大学物理实验报告", course: "大学物理实验", dueAt: isoAt(7, 18), reminderMinutes: 60, status: "todo", createdAt: isoAt(-2, 14) },
  { id: 5, title: "整理第一周课堂笔记", course: "个人计划", dueAt: isoAt(-1, 21), reminderMinutes: null, status: "done", createdAt: isoAt(-5, 10) },
];

export const demoCourses: Course[] = [
  { id: 1, name: "高等数学", teacher: "刘老师", location: "教二楼 301", weekday: 1, startSection: 1, endSection: 2, startTime: "08:00", endTime: "09:35", weeks: "1–16 周", reminderMinutes: 20, color: "blue" },
  { id: 2, name: "大学物理实验", teacher: "王老师", location: "教四楼 305", weekday: 2, startSection: 1, endSection: 2, startTime: "08:00", endTime: "09:35", weeks: "1–16 周", reminderMinutes: 20, color: "violet" },
  { id: 3, name: "软件工程", teacher: "张老师", location: "教三楼 217", weekday: 2, startSection: 3, endSection: 4, startTime: "10:10", endTime: "11:45", weeks: "1–16 周", reminderMinutes: 20, color: "blue" },
  { id: 4, name: "通信原理", teacher: "陈老师", location: "教二楼 401", weekday: 2, startSection: 5, endSection: 6, startTime: "14:00", endTime: "15:35", weeks: "1–16 周", reminderMinutes: 20, color: "green" },
  { id: 5, name: "通信原理", teacher: "陈老师", location: "教二楼 401", weekday: 3, startSection: 3, endSection: 4, startTime: "10:10", endTime: "11:45", weeks: "1–16 周", reminderMinutes: 20, color: "green" },
  { id: 6, name: "体育", teacher: "赵老师", location: "操场", weekday: 4, startSection: 5, endSection: 6, startTime: "14:00", endTime: "15:35", weeks: "1–16 周", reminderMinutes: 30, color: "orange" },
  { id: 7, name: "软件工程", teacher: "张老师", location: "教三楼 217", weekday: 5, startSection: 3, endSection: 4, startTime: "10:10", endTime: "11:45", weeks: "1–16 周", reminderMinutes: 20, color: "blue" },
];

export const demoCampusItems: CampusItem[] = [
  { id: "n1", url: "https://jwc.bupt.edu.cn/", kind: "notice", category: "教务通知", title: "关于秋季学期本科生选课安排的通知", summary: "查看选课轮次、开放时间、容量限制与注意事项。演示条目将打开教务处官网，接入校园数据源后会保存具体原文地址。", source: "教务处", publishedAt: isoAt(0, 8, 10), subscribed: true, read: false },
  { id: "n2", url: "https://xsc.bupt.edu.cn/", kind: "notice", category: "奖助学金", title: "关于开展本学年国家奖学金评审工作的通知", summary: "包含申请条件、材料清单和学院提交截止时间。演示条目将打开学生工作处官网。", source: "学生工作处", publishedAt: isoAt(-1, 15), subscribed: true, read: false },
  { id: "n3", url: "https://lib.bupt.edu.cn/", kind: "notice", category: "校园服务", title: "图书馆新学期开放时间调整", summary: "各阅览区开放时间与自习座位预约说明。演示条目将打开图书馆官网。", source: "图书馆", publishedAt: isoAt(-2, 9), subscribed: false, read: true },
  { id: "a1", url: "https://dekt.bupt.edu.cn/", kind: "activity", category: "学术讲座", title: "“人工智能与未来网络”系列讲座", summary: "面向全校学生开放，参与可获得第二课堂学分。演示条目将打开第二课堂官网。", source: "第二课堂", publishedAt: isoAt(-1, 10), campus: "西土城", eventTime: isoAt(4, 19), subscribed: true, read: false },
  { id: "a2", url: "https://dekt.bupt.edu.cn/", kind: "activity", category: "志愿服务", title: "迎新志愿服务招募", summary: "协助新生报到与校园引导，名额有限。演示条目将打开第二课堂官网。", source: "第二课堂", publishedAt: isoAt(-2, 12), campus: "沙河", eventTime: isoAt(6, 8), subscribed: false, read: true },
];

export const demoNotifications: AppNotification[] = [
  { id: 1, title: "DDL 将于今晚截止", body: "“提交软件工程需求分析”将在 20:00 截止。", createdAt: isoAt(0, 9), type: "task", read: false },
  { id: 2, title: "下一节课提醒", body: "软件工程，10:10，教三楼 217。", createdAt: isoAt(0, 9, 50), type: "course", read: false },
  { id: 3, title: "订阅有新内容", body: "教务处发布了新的选课安排通知。", createdAt: isoAt(0, 8, 12), type: "campus", read: true },
];
