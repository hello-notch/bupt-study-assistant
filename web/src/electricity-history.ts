import type { ElectricitySnapshot } from "./types";

export function chinaDate(value: string | number): string {
  const text = typeof value === "string" ? value.trim().replace(" ", "T") : value;
  const timestamp = typeof text === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(text) ? `${text}+08:00` : text;
  const date = new Date(timestamp);
  return Number.isFinite(date.getTime()) ? new Date(date.getTime() + 8 * 3600_000).toISOString().slice(0, 10) : "";
}

export function saveSnapshot(history: ElectricitySnapshot[], snapshot: ElectricitySnapshot): ElectricitySnapshot[] {
  const matches = (item: ElectricitySnapshot) => item.date === snapshot.date && item.unit === snapshot.unit
    && item.dormitory === snapshot.dormitory && item.accountKey === snapshot.accountKey;
  const previous = history.find(matches);
  if (previous?.balance === snapshot.balance) return history;
  return [...history.filter(item => !matches(item)), snapshot]
    .sort((a, b) => a.date.localeCompare(b.date)).slice(-120);
}

export function hasSnapshotForDate(history: ElectricitySnapshot[], date: string, dormitory: string,
  accountKey: string, unit?: "元" | "度"): boolean {
  return history.some(item => item.date === date && item.dormitory === dormitory
    && item.accountKey === accountKey && (!unit || item.unit === unit));
}

export function usageChart(history: ElectricitySnapshot[], dormitory: string, accountKey: string, unit: "元" | "度", now = Date.now()) {
  const today = chinaDate(now);
  const dates = Array.from({ length: 8 }, (_, index) =>
    new Date(Date.parse(`${today}T00:00:00Z`) - (7 - index) * 86400_000).toISOString().slice(0, 10));
  const rows = new Map(history.filter(item => item.dormitory === dormitory && item.accountKey === accountKey && item.unit === unit)
    .map(item => [item.date, item]));
  const points = dates.slice(1).map((date, index) => {
    const previous = rows.get(dates[index]!);
    const current = rows.get(date);
    const difference = previous && current ? previous.balance - current.balance : null;
    const usage = difference !== null && difference >= 0 ? Math.round(difference * 100) / 100 : null;
    return { date, usage, reason: difference !== null && difference < 0 ? "充值或余额调整" : "缺少记录", x: 40 + index * 92 };
  });
  const max = Math.max(1, ...points.map(point => point.usage ?? 0));
  const segments: string[] = [];
  let segment: string[] = [];
  for (const point of points) {
    if (point.usage === null) {
      if (segment.length) segments.push(segment.join(" "));
      segment = [];
    } else segment.push(`${point.x},${166 - point.usage / max * 130}`);
  }
  if (segment.length) segments.push(segment.join(" "));
  return { unit, points, max, segments, hasData: points.some(point => point.usage !== null) };
}
