export interface AuthUser {
  id: string;
  nickname: string;
  createdAt?: string;
}

export interface SavedLogin {
  nickname: string;
  password: string;
}

declare global {
  interface Window {
    youxuebanCredentials?: {
      load(): Promise<SavedLogin | null>;
      save(value: SavedLogin): Promise<void>;
      clear(): Promise<void>;
    };
  }
}

interface AuthResponse {
  user?: AuthUser;
  accessToken?: string;
  error?: string;
}

const accessTokenKey = "youxueban-access-token";
export const autoLoginKey = "youxueban-auto-login";
const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const apiBaseUrl = configuredApiBaseUrl || (location.protocol === "file:" ? "http://127.0.0.1:8787" : "");
let accessToken = sessionStorage.getItem(accessTokenKey) ?? "";

export function getApiBaseUrl(): string {
  return apiBaseUrl;
}

export function getAccessToken(): string {
  return accessToken;
}

export function setAccessToken(value: string): void {
  accessToken = value;
  if (value) sessionStorage.setItem(accessTokenKey, value);
  else sessionStorage.removeItem(accessTokenKey);
}

function apiUrl(path: string): string {
  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

async function parseJson<T>(response: Response): Promise<T> {
  try {
    return await response.json() as T;
  } catch {
    return {} as T;
  }
}

export async function authRequest(path: string, body?: Record<string, unknown>): Promise<{ response: Response; payload: AuthResponse }> {
  const response = await fetch(apiUrl(path), {
    method: body ? "POST" : "GET",
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  return { response, payload: await parseJson<AuthResponse>(response) };
}

export async function restoreSession(): Promise<AuthUser | null> {
  let response = await fetch(apiUrl("/api/v1/auth/me"), {
    credentials: "include",
    headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
  });
  let payload = await parseJson<AuthResponse>(response);
  if (response.status === 401) {
    const renewed = await authRequest("/api/v1/auth/refresh", {});
    if (renewed.response.ok && renewed.payload.accessToken) {
      setAccessToken(renewed.payload.accessToken);
      response = await fetch(apiUrl("/api/v1/auth/me"), {
        credentials: "include",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      payload = await parseJson<AuthResponse>(response);
    }
  }
  if (!response.ok || !payload.user) {
    setAccessToken("");
    return null;
  }
  return payload.user;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const request = () => fetch(apiUrl(path), { ...init, credentials: "include", headers });
  let response = await request();
  if (response.status !== 401 || path.includes("/auth/")) return response;
  const renewed = await authRequest("/api/v1/auth/refresh", {});
  if (!renewed.response.ok || !renewed.payload.accessToken) {
    setAccessToken("");
    window.dispatchEvent(new CustomEvent("youxueban-auth-expired"));
    return response;
  }
  setAccessToken(renewed.payload.accessToken);
  headers.set("Authorization", `Bearer ${accessToken}`);
  response = await request();
  return response;
}

export async function logoutSession(): Promise<void> {
  try {
    await authRequest("/api/v1/auth/logout", {});
  } finally {
    setAccessToken("");
  }
}

export async function loadSavedLogin(): Promise<SavedLogin | null> {
  return window.youxuebanCredentials?.load() ?? null;
}

export async function saveLogin(value: SavedLogin): Promise<void> {
  if (!window.youxuebanCredentials) throw new Error("当前版本不支持安全保存密码");
  await window.youxuebanCredentials.save(value);
}

export async function clearSavedLogin(): Promise<void> {
  localStorage.removeItem(autoLoginKey);
  await window.youxuebanCredentials?.clear();
}
