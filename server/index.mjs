import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { randomBytes, scryptSync, timingSafeEqual } from "node:crypto";

const root = resolve(import.meta.dirname, "..");
const host = process.env.YOUXUEBAN_SERVER_HOST || "127.0.0.1";
const port = Number(process.env.YOUXUEBAN_SERVER_PORT || 8787);
const dataDir = resolve(process.env.YOUXUEBAN_SERVER_DATA_DIR || join(import.meta.dirname, "data"));
const usersFile = join(dataDir, "users.json");
const campusCacheFile = process.env.YOUXUEBAN_CAMPUS_CACHE_FILE || join(dataDir, "campus.json");
const staticRoot = resolve(process.env.YOUXUEBAN_STATIC_ROOT || join(root, "web", "dist"));
const refreshTtl = 30 * 24 * 60 * 60 * 1000;
const sessions = new Map();

mkdirSync(dataDir, { recursive: true });

function json(response, status, value, extraHeaders = {}) {
  const body = JSON.stringify(value);
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extraHeaders });
  response.end(body);
  return true;
}

function corsHeaders(request) {
  const origin = request.headers.origin;
  const configured = process.env.YOUXUEBAN_ALLOWED_ORIGIN || "";
  const allowed = configured || (!origin || origin === "null" || /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/i.test(origin) ? origin : "");
  return allowed ? { "Access-Control-Allow-Origin": allowed, "Access-Control-Allow-Credentials": "true", Vary: "Origin" } : {};
}

async function readBody(request, maxBytes = 2_000_000) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > maxBytes) throw new Error("请求体过大");
    chunks.push(chunk);
  }
  if (!size) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function users() {
  if (!existsSync(usersFile)) return [];
  try {
    const value = JSON.parse(readFileSync(usersFile, "utf8"));
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function saveUsers(value) {
  mkdirSync(dirname(usersFile), { recursive: true });
  writeFileSync(usersFile, JSON.stringify(value, null, 2), { encoding: "utf8", mode: 0o600 });
}

function hashPassword(password) {
  const salt = randomBytes(16).toString("hex");
  const digest = scryptSync(password, salt, 32).toString("hex");
  return `scrypt$${salt}$${digest}`;
}

function verifyPassword(password, encoded) {
  const [, salt, expected] = String(encoded || "").split("$");
  if (!salt || !expected) return false;
  try {
    const actual = scryptSync(password, salt, 32);
    const target = Buffer.from(expected, "hex");
    return actual.length === target.length && timingSafeEqual(actual, target);
  } catch {
    return false;
  }
}

function publicUser(user) {
  return { id: user.id, nickname: user.nickname, createdAt: user.createdAt };
}

function cookieValue(request, name) {
  return request.headers.cookie?.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`))?.[1];
}

function issueSession(userId, rememberMe = false) {
  const accessToken = randomBytes(32).toString("base64url");
  const refreshToken = randomBytes(32).toString("base64url");
  sessions.set(accessToken, { userId, kind: "access", expiresAt: Date.now() + 15 * 60 * 1000, rememberMe });
  sessions.set(refreshToken, { userId, kind: "refresh", expiresAt: Date.now() + refreshTtl, rememberMe });
  return { accessToken, refreshToken };
}

function refreshCookie(value, maxAge) {
  const crossSite = Boolean(process.env.YOUXUEBAN_ALLOWED_ORIGIN) && !/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/i.test(process.env.YOUXUEBAN_ALLOWED_ORIGIN);
  return `youxueban_refresh=${value}; Path=/api/v1/auth; HttpOnly; ${crossSite ? "SameSite=None; Secure" : "SameSite=Lax"}${maxAge == null ? "" : `; Max-Age=${maxAge}`}`;
}

function authenticatedUser(request) {
  const token = request.headers.authorization?.match(/^Bearer\s+(.+)$/i)?.[1];
  const session = token ? sessions.get(token) : undefined;
  if (!session || session.kind !== "access" || session.expiresAt <= Date.now()) {
    if (token) sessions.delete(token);
    return undefined;
  }
  return users().find((item) => item.id === session.userId);
}

async function handleAuth(request, response, pathname) {
  const headers = corsHeaders(request);
  if (request.method === "OPTIONS") {
    response.writeHead(204, { ...headers, "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" });
    response.end();
    return true;
  }
  if (pathname === "/api/v1/auth/register" && request.method === "POST") {
    const body = await readBody(request);
    const nickname = String(body.nickname || "").trim();
    const password = String(body.password || "");
    const rememberMe = body.rememberMe === true;
    if (body.agreedToTerms !== true) return json(response, 400, { error: "注册前必须同意用户协议与隐私说明" }, headers);
    if (!nickname || nickname.length > 20) return json(response, 400, { error: "昵称长度应为 1 到 20 个字符" }, headers);
    if (password.length < 6 || password.length > 128) return json(response, 400, { error: "密码长度应为 6 到 128 个字符" }, headers);
    const list = users();
    if (list.some((item) => item.nickname === nickname)) return json(response, 409, { error: "该昵称已注册" }, headers);
    const user = { id: randomBytes(16).toString("hex"), nickname, passwordHash: hashPassword(password), createdAt: new Date().toISOString() };
    list.push(user);
    saveUsers(list);
    const session = issueSession(user.id, rememberMe);
    return json(response, 201, { user: publicUser(user), accessToken: session.accessToken }, { ...headers, "Set-Cookie": refreshCookie(session.refreshToken, rememberMe ? Math.floor(refreshTtl / 1000) : undefined) });
  }
  if (pathname === "/api/v1/auth/login" && request.method === "POST") {
    const body = await readBody(request);
    const user = users().find((item) => item.nickname === String(body.nickname || "").trim());
    if (!user || !verifyPassword(String(body.password || ""), user.passwordHash)) return json(response, 401, { error: "昵称或密码错误" }, headers);
    const rememberMe = body.rememberMe === true;
    const session = issueSession(user.id, rememberMe);
    return json(response, 200, { user: publicUser(user), accessToken: session.accessToken }, { ...headers, "Set-Cookie": refreshCookie(session.refreshToken, rememberMe ? Math.floor(refreshTtl / 1000) : undefined) });
  }
  if (pathname === "/api/v1/auth/password" && request.method === "POST") {
    const user = authenticatedUser(request);
    if (!user) return json(response, 401, { error: "登录已失效，请重新登录" }, headers);
    const body = await readBody(request);
    const currentPassword = String(body.currentPassword || "");
    const newPassword = String(body.newPassword || "");
    const confirmPassword = String(body.confirmPassword || "");
    if (!verifyPassword(currentPassword, user.passwordHash)) return json(response, 401, { error: "原密码错误" }, headers);
    if (newPassword.length < 6 || newPassword.length > 128) return json(response, 400, { error: "新密码长度应为 6 到 128 个字符" }, headers);
    if (newPassword !== confirmPassword) return json(response, 400, { error: "两次输入的新密码不一致" }, headers);
    if (newPassword === currentPassword) return json(response, 400, { error: "新密码不能与原密码相同" }, headers);
    const list = users();
    const target = list.find((item) => item.id === user.id);
    if (!target) return json(response, 404, { error: "账号不存在" }, headers);
    target.passwordHash = hashPassword(newPassword);
    saveUsers(list);
    for (const [token, session] of sessions) {
      if (session.userId === user.id) sessions.delete(token);
    }
    return json(response, 200, { ok: true }, { ...headers, "Set-Cookie": refreshCookie("", 0) });
  }
  if (pathname === "/api/v1/auth/me" && request.method === "GET") {
    const user = authenticatedUser(request);
    return user ? json(response, 200, { user: publicUser(user) }, headers) : json(response, 401, { error: "登录已失效" }, headers);
  }
  if (pathname === "/api/v1/auth/refresh" && request.method === "POST") {
    const token = cookieValue(request, "youxueban_refresh");
    const session = token ? sessions.get(token) : undefined;
    const user = session && session.kind === "refresh" && session.expiresAt > Date.now() ? users().find((item) => item.id === session.userId) : undefined;
    if (!user) return json(response, 401, { error: "登录已失效" }, { ...headers, "Set-Cookie": refreshCookie("", 0) });
    sessions.delete(token);
    const next = issueSession(user.id, session.rememberMe);
    return json(response, 200, { user: publicUser(user), accessToken: next.accessToken }, { ...headers, "Set-Cookie": refreshCookie(next.refreshToken, session.rememberMe ? Math.floor(refreshTtl / 1000) : undefined) });
  }
  if (pathname === "/api/v1/auth/logout" && request.method === "POST") {
    const token = cookieValue(request, "youxueban_refresh");
    if (token) sessions.delete(token);
    return json(response, 200, { ok: true }, { ...headers, "Set-Cookie": refreshCookie("", 0) });
  }
  return false;
}

function campusItems() {
  if (!existsSync(campusCacheFile)) return [];
  try {
    const value = JSON.parse(readFileSync(campusCacheFile, "utf8"));
    return Array.isArray(value) ? value : Array.isArray(value.items) ? value.items : [];
  } catch {
    return [];
  }
}

async function handleApi(request, response, pathname) {
  if (!pathname.startsWith("/api/")) return false;
  const headers = corsHeaders(request);
  if (!authenticatedUser(request)) return json(response, 401, { error: "请先登录邮学伴" }, headers);
  if (pathname === "/api/config" && request.method === "GET") {
    const model = process.env.YOUXUEBAN_MODEL_NAME || "";
    return json(response, 200, { assistant: model ? { provider: "server", model, thinkingSupported: process.env.YOUXUEBAN_THINKING_SUPPORTED === "true", allowedFileTypes: ["image/png", "image/jpeg", "image/webp"] } : undefined }, headers);
  }
  if (pathname === "/api/campus" && request.method === "GET") {
    const items = campusItems();
    const statuses = [{ source: "portal", label: "信息门户", mode: items.some((item) => item.kind === "notice") ? "cache" : "error", message: "由服务端缓存提供", itemCount: items.filter((item) => item.kind === "notice").length }, { source: "activity", label: "第二课堂", mode: items.some((item) => item.kind === "activity") ? "cache" : "error", message: "由服务端缓存提供", itemCount: items.filter((item) => item.kind === "activity").length }];
    return json(response, items.length ? 200 : 503, { items, statuses, updatedAt: new Date().toISOString(), ...(items.length ? {} : { error: "服务端尚未配置校园数据缓存" }) }, headers);
  }
  if (pathname === "/api/campus/summary" && request.method === "POST") return json(response, 503, { error: "服务端尚未配置校园通知总结" }, headers);
  if (pathname === "/api/courses/class" && request.method === "POST") return json(response, 503, { error: "服务端尚未配置教务课表数据源" }, headers);
  if (pathname === "/api/electricity/query" && request.method === "POST") return json(response, 503, { error: "服务端尚未配置电费数据源" }, headers);
  if ((pathname === "/api/assistant/chat" || pathname === "/api/assistant/title") && request.method === "POST") {
    const endpoint = process.env.YOUXUEBAN_MODEL_URL;
    const key = process.env.YOUXUEBAN_MODEL_API_KEY;
    const model = process.env.YOUXUEBAN_MODEL_NAME;
    if (!endpoint || !key || !model) return json(response, 503, { error: "服务端尚未配置模型服务" }, headers);
    const body = await readBody(request);
    const upstreamBody = pathname.endsWith("/title") ? { model, messages: body.messages || [], temperature: 0, max_tokens: 60 } : { ...body, model };
    const upstream = await fetch(`${endpoint.replace(/\/$/, "")}/chat/completions`, { method: "POST", headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" }, body: JSON.stringify(upstreamBody), signal: AbortSignal.timeout(45_000) });
    const payload = await upstream.json().catch(() => ({}));
    if (!upstream.ok) return json(response, 502, { error: `模型服务暂时不可用（HTTP ${upstream.status}）` }, headers);
    if (pathname.endsWith("/title")) {
      const title = String(payload.choices?.[0]?.message?.content || "").replace(/[\p{P}\p{S}\s]/gu, "").slice(0, 10);
      return title ? json(response, 200, { title }, headers) : json(response, 502, { error: "模型没有返回有效标题" }, headers);
    }
    const message = payload.choices?.[0]?.message || {};
    return json(response, 200, { ...(message.content ? { reply: String(message.content) } : {}), ...(message.tool_calls ? { toolCalls: message.tool_calls } : {}), usage: payload.usage, mode: "online", provider: "server", model }, headers);
  }
  return false;
}

function contentType(path) {
  return { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".svg": "image/svg+xml" }[extname(path).toLowerCase()] || "application/octet-stream";
}

function serveStatic(request, response, pathname) {
  const requested = pathname === "/" ? "/index.html" : pathname;
  const file = resolve(staticRoot, `.${normalize(requested)}`);
  if (!file.startsWith(staticRoot) || !existsSync(file)) return json(response, 404, { error: "资源不存在" });
  response.writeHead(200, { "Content-Type": contentType(file), "Cache-Control": extname(file) === ".html" ? "no-cache" : "public, max-age=31536000, immutable" });
  response.end(readFileSync(file));
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
  try {
    if (request.method === "OPTIONS") {
      response.writeHead(204, { ...corsHeaders(request), "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Allow-Methods": "GET, POST, OPTIONS" });
      response.end();
      return;
    }
    if (await handleAuth(request, response, url.pathname)) return;
    if (await handleApi(request, response, url.pathname)) return;
    if (request.method === "GET") return serveStatic(request, response, url.pathname);
    json(response, 404, { error: "接口不存在" });
  } catch (error) {
    json(response, 500, { error: error instanceof Error ? error.message : "服务端错误" }, corsHeaders(request));
  }
});

server.listen(port, host, () => console.log(`邮学伴服务端运行于 http://${host}:${port}`));
