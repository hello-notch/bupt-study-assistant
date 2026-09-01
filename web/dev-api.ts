import { existsSync, readFileSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

type JsonObject = Record<string, unknown>;

export function localWebApi(): Plugin {
  const projectRoot = resolve(process.cwd(), "..");
  const env = { ...readEnvFile(resolve(projectRoot, ".env")), ...process.env };

  return {
    name: "youxueban-local-web-api",
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        if (request.method === "POST" && request.url === "/api/assistant/chat") {
          await handleAssistant(request, response, projectRoot, env);
          return;
        }
        if (request.method === "POST" && request.url === "/api/courses/class") {
          await handleClassImport(request, response, projectRoot, env);
          return;
        }
        next();
      });
    },
  };
}

async function handleAssistant(
  request: IncomingMessage,
  response: ServerResponse,
  projectRoot: string,
  env: NodeJS.ProcessEnv,
): Promise<void> {
  try {
    const body = await readJson(request);
    const messages = Array.isArray(body.messages) ? body.messages.slice(-12) : [];
    if (!messages.length) return sendJson(response, 400, { error: "消息不能为空" });

    const routePath = resolveSecretPath(projectRoot, env.AMADEUS_AI_ROUTES_FILE || "config/ai_routes.toml");
    const keyPath = resolveSecretPath(projectRoot, env.AMADEUS_API_KEY_FILE || "secrets/apikey.txt");
    const routeText = existsSync(routePath) ? readFileSync(routePath, "utf8") : "";
    const primary = /^primary\s*=\s*"([^"]+)"/m.exec(section(routeText, "tasks.chat"))?.[1];
    if (!primary) return sendJson(response, 503, { error: "未配置聊天模型" });
    const [providerName, model] = primary.split("/", 2);
    const providerSection = section(routeText, `providers.${providerName}`);
    const credentialHost = /^credential_host\s*=\s*"([^"]+)"/m.exec(providerSection)?.[1];
    const apiPrefix = /^api_prefix\s*=\s*"([^"]*)"/m.exec(providerSection)?.[1] ?? "";
    const credential = credentialHost ? readCredentials(keyPath).get(credentialHost) : undefined;
    if (!credential || !model) return sendJson(response, 503, { error: "AI 凭据未配置，本次将使用本地助手" });

    const context = typeof body.context === "object" && body.context ? body.context : {};
    const system = [
      "你是‘邮学伴’，北邮学生的学习助手。请用简洁自然的中文回答。",
      "你可以根据下方网页状态回答课程、DDL 和校园信息问题，但不要声称已经执行未实际执行的操作。",
      "如果用户想新增任务，提醒他可直接说清任务、截止时间，网页会给出确认按钮。",
      `当前网页数据：${JSON.stringify(context).slice(0, 12000)}`,
    ].join("\n");
    const endpoint = `${credential.url.replace(/\/$/, "")}/${apiPrefix.replace(/^\/+|\/+$/g, "")}`.replace(/\/$/, "");
    const upstream = await fetch(`${endpoint}/chat/completions`, {
      method: "POST",
      headers: { Authorization: `Bearer ${credential.key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [{ role: "system", content: system }, ...messages],
        temperature: 0.65,
        max_tokens: 900,
      }),
      signal: AbortSignal.timeout(45_000),
    });
    if (!upstream.ok) return sendJson(response, 502, { error: `AI 服务暂时不可用（HTTP ${upstream.status}）` });
    const payload = await upstream.json() as JsonObject;
    const choices = Array.isArray(payload.choices) ? payload.choices : [];
    const first = choices[0] as JsonObject | undefined;
    const reply = ((first?.message as JsonObject | undefined)?.content as string | undefined)?.trim();
    if (!reply) return sendJson(response, 502, { error: "AI 服务没有返回正文" });
    sendJson(response, 200, { reply, mode: "online" });
  } catch (error) {
    sendJson(response, 500, { error: safeError(error) });
  }
}

async function handleClassImport(
  request: IncomingMessage,
  response: ServerResponse,
  projectRoot: string,
  env: NodeJS.ProcessEnv,
): Promise<void> {
  try {
    const body = await readJson(request);
    const classId = String(body.classId ?? "").trim();
    if (!/^[A-Za-z0-9_-]{4,32}$/.test(classId)) return sendJson(response, 400, { error: "请输入有效的完整班级号" });
    const cookieSetting = env.AMADEUS_JWGL_COOKIE_FILE;
    if (!cookieSetting) return sendJson(response, 503, { error: "尚未配置教务系统会话，请改用文件导入或在 .env 设置 AMADEUS_JWGL_COOKIE_FILE" });
    const cookiePath = resolveSecretPath(projectRoot, cookieSetting);
    if (!existsSync(cookiePath)) return sendJson(response, 503, { error: "教务系统会话文件不存在，请重新配置后再试" });
    const cookie = readCookieHeader(cookiePath);
    const form = new URLSearchParams({ skbj: classId, skbjid: "" });
    if (body.term) form.set("xnxqh", String(body.term));
    const upstream = await fetch("https://jwgl.bupt.edu.cn/jsxsd/kbcx/kbxx_xzb_ifr", {
      method: "POST",
      redirect: "follow",
      headers: { Cookie: cookie, "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
      signal: AbortSignal.timeout(25_000),
    });
    const html = await upstream.text();
    if (!upstream.ok) return sendJson(response, 502, { error: `教务系统返回 HTTP ${upstream.status}` });
    if (/用户登录|请输入账号|<title>登录<\/title>/i.test(html)) return sendJson(response, 401, { error: "教务系统登录已失效，请更新会话后重试" });
    if (html.includes("非法访问")) return sendJson(response, 502, { error: "教务系统拒绝了本次班级课表查询" });
    const courses = parseClassSchedule(html, classId);
    if (!courses.length) return sendJson(response, 404, { error: "没有解析到课程，请检查班级号或当前学期" });
    sendJson(response, 200, { courses });
  } catch (error) {
    sendJson(response, 500, { error: safeError(error) });
  }
}

function parseClassSchedule(html: string, classId: string): JsonObject[] {
  const rows = [...html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)].map((match) => match[1]);
  const target = rows.find((row) => row.includes("kbcontent1") && stripHtml(row).includes(classId)) ?? "";
  const cells = [...target.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map((match) => match[1]);
  if (cells.length < 8) return [];
  const scheduleCells = cells.slice(1);
  const sectionCount = Math.floor(scheduleCells.length / 7);
  const merged = new Map<string, JsonObject>();
  scheduleCells.slice(0, sectionCount * 7).forEach((cell, index) => {
    const weekday = Math.floor(index / sectionCount) + 1;
    const currentSection = index % sectionCount + 1;
    const blocks = [...cell.matchAll(/<div[^>]*class=["'][^"']*kbcontent1[^"']*["'][^>]*>([\s\S]*?)<\/div>/gi)];
    for (const block of blocks) {
      const lines = htmlLines(block[1]);
      const weekIndex = lines.findIndex((line) => /^\([^)]+周\)$/.test(line));
      if (weekIndex < 2 || weekIndex + 1 >= lines.length) continue;
      const teacher = lines[weekIndex - 1];
      const name = lines.slice(0, weekIndex - 1).filter((line) => line !== classId).join(" ").replace(new RegExp(`${escapeRegExp(classId)}$`), "").trim();
      const weeks = lines[weekIndex].slice(1, -2).replace(/[~～]/g, "-");
      const location = lines[weekIndex + 1];
      if (!name) continue;
      const key = `${name}|${teacher}|${weeks}|${location}|${weekday}`;
      const existing = merged.get(key);
      if (existing) existing.endSection = Math.max(Number(existing.endSection), currentSection);
      else merged.set(key, { name, teacher, location, weekday, startSection: currentSection, endSection: currentSection, weeks });
    }
  });
  return [...merged.values()];
}

function readEnvFile(path: string): NodeJS.ProcessEnv {
  if (!existsSync(path)) return {};
  const result: NodeJS.ProcessEnv = {};
  for (const raw of readFileSync(path, "utf8").split(/\r?\n/)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/.exec(raw);
    if (!match || raw.trimStart().startsWith("#")) continue;
    result[match[1]] = match[2].replace(/^(['"])(.*)\1$/, "$2");
  }
  return result;
}

function readCredentials(path: string): Map<string, { key: string; url: string }> {
  const result = new Map<string, { key: string; url: string }>();
  if (!existsSync(path)) return result;
  let pendingKey = "";
  for (const raw of readFileSync(path, "utf8").split(/\r?\n/)) {
    const match = /^\s*([^:=]+)\s*[:=]\s*(.*)$/.exec(raw);
    if (!match) continue;
    if (match[1].trim().toLowerCase() === "apikey") pendingKey = match[2].trim();
    if (match[1].trim().toLowerCase() === "url" && pendingKey) {
      const url = match[2].trim();
      result.set(new URL(url).host, { key: pendingKey, url });
      pendingKey = "";
    }
  }
  return result;
}

function readCookieHeader(path: string): string {
  const raw = readFileSync(path, "utf8").trim();
  try {
    const payload = JSON.parse(raw) as JsonObject;
    return Object.entries(payload).map(([key, value]) => `${key}=${String(value)}`).join("; ");
  } catch {
    const oneLine = raw.replace(/^cookie:\s*/i, "");
    if (/\r|\n/.test(oneLine)) throw new Error("Cookie 文件必须是单行请求头或 JSON 对象");
    return oneLine;
  }
}

function resolveSecretPath(projectRoot: string, value: string): string {
  return isAbsolute(value) ? value : resolve(projectRoot, value);
}

function section(text: string, name: string): string {
  return new RegExp(`\\[${name.replace(".", "\\.")}\\]([\\s\\S]*?)(?=\\n\\[|$)`).exec(text)?.[1] ?? "";
}

function stripHtml(value: string): string {
  return decodeEntities(value.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
}

function htmlLines(value: string): string[] {
  return decodeEntities(value.replace(/<br\s*\/?\s*>/gi, "\n").replace(/<[^>]+>/g, ""))
    .split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function decodeEntities(value: string): string {
  return value.replace(/&nbsp;/gi, " ").replace(/&amp;/gi, "&").replace(/&lt;/gi, "<").replace(/&gt;/gi, ">").replace(/&quot;/gi, '"').replace(/&#39;/gi, "'");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function readJson(request: IncomingMessage): Promise<JsonObject> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.from(chunk);
    size += buffer.length;
    if (size > 256_000) throw new Error("请求内容过大");
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}") as JsonObject;
}

function sendJson(response: ServerResponse, status: number, body: JsonObject): void {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify(body));
}

function safeError(error: unknown): string {
  if (error instanceof Error && error.name === "TimeoutError") return "上游服务请求超时";
  return error instanceof Error ? error.message.replace(/Bearer\s+\S+/gi, "Bearer [hidden]") : "未知错误";
}
