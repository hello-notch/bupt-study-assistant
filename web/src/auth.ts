export interface LocalRuntimeResult {
  status: number;
  body: unknown;
}

declare global {
  interface Window {
    youxuebanRuntime?: {
      request(route: string, init?: { method?: string; body?: string }, signal?: AbortSignal): Promise<LocalRuntimeResult>;
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
    const signal = init.signal;
    if (signal?.aborted) throw signal.reason;
    const request = window.youxuebanRuntime.request(route, {
      method: init.method ?? "GET",
      body: typeof init.body === "string" ? init.body : undefined,
    }, signal ?? undefined);
    let onAbort: (() => void) | undefined;
    let result: LocalRuntimeResult;
    try {
      result = await (signal ? Promise.race([request, new Promise<never>((_, reject) => {
        onAbort = () => reject(signal.reason);
        signal.addEventListener("abort", onAbort, { once: true });
      })]) : request);
    } finally {
      if (signal && onAbort) signal.removeEventListener("abort", onAbort);
    }
    return new Response(JSON.stringify(result.body ?? {}), {
      status: result.status,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }
  return fetch(route, init);
}
