export interface LocalRuntimeResult {
  status: number;
  body: unknown;
}

declare global {
  interface Window {
    youxuebanRuntime?: {
      request(route: string, init?: { method?: string; body?: string }): Promise<LocalRuntimeResult>;
      notify?(title: string, body: string): Promise<boolean>;
    };
  }
}

function apiUrl(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

/**
 * One API-shaped boundary for the UI. Packaged apps call their local native
 * runtime over IPC; Vite development uses the local-only development plugin.
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const route = apiUrl(path);
  if (window.youxuebanRuntime) {
    const result = await window.youxuebanRuntime.request(route, {
      method: init.method ?? "GET",
      body: typeof init.body === "string" ? init.body : undefined,
    });
    return new Response(JSON.stringify(result.body ?? {}), {
      status: result.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }
  return fetch(route, init);
}
