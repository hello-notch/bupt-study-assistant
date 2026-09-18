const pending = new Map();
let sequence = 0;

function call(operation, payload = {}, signal) {
  if (signal?.aborted) return Promise.reject(signal.reason);
  const id = String(++sequence);
  return new Promise((resolve, reject) => {
    const abort = (reason) => {
      pending.delete(id);
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      if (operation === "fetch") NativeRuntime.call(`cancel-${id}`, "cancelFetch", JSON.stringify({ id }));
      reject(reason);
    };
    const onAbort = () => abort(signal.reason);
    const timer = setTimeout(() => {
      abort(new Error("设备操作超时，请重试"));
    }, operation === "fetch" ? 130_000 : 40_000);
    signal?.addEventListener("abort", onAbort, { once: true });
    pending.set(id, { resolve, reject, timer, cleanup: () => signal?.removeEventListener("abort", onAbort) });
    NativeRuntime.call(id, operation, JSON.stringify(payload));
  });
}

globalThis.__nativeResult = (id, result, error) => {
  const item = pending.get(id);
  if (!item) return;
  pending.delete(id);
  clearTimeout(item.timer);
  item.cleanup();
  if (error) item.reject(new Error(error));
  else item.resolve(result);
};

class BrowserWindow {
  constructor(options = {}, signal) {
    this.signal = signal;
    if (signal?.aborted) throw signal.reason;
    this.id = NativeRuntime.createWindow();
    this.destroyed = false;
    this.listeners = new Map();
    this.lastUrl = "";
    this.webContents = {
      setUserAgent() {},
      getURL: () => NativeRuntime.windowUrl(this.id),
      isLoadingMainFrame: () => false,
      executeJavaScript: (script) => call("evaluate", { window: this.id, script }, this.signal),
      on: (name, listener) => {
        const entries = this.listeners.get(name) || new Set();
        entries.add(listener);
        this.listeners.set(name, entries);
      },
      off: (name, listener) => this.listeners.get(name)?.delete(listener),
    };
    this.timer = setInterval(() => {
      const url = this.webContents.getURL();
      if (url === this.lastUrl) return;
      this.lastUrl = url;
      for (const listener of this.listeners.get("did-navigate") || []) listener({}, url);
    }, 150);
    this.onAbort = () => this.destroy();
    signal?.addEventListener("abort", this.onAbort, { once: true });
  }
  loadURL(url) { return call("navigate", { window: this.id, url }, this.signal); }
  show() { return call("showWindow", { window: this.id }); }
  isDestroyed() { return this.destroyed; }
  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    this.signal?.removeEventListener("abort", this.onAbort);
    clearInterval(this.timer);
    void call("destroyWindow", { window: this.id }).catch(() => {});
  }
}

async function nativeFetch(input, init = {}) {
  if (init.signal?.aborted) throw init.signal.reason;
  const headers = Object.fromEntries(new Headers(init.headers).entries());
  const result = await call("fetch", {
    url: String(input), method: init.method || "GET", headers,
    body: init.body == null ? null : String(init.body),
  }, init.signal);
  const bytes = Uint8Array.from(atob(result.body), (c) => c.charCodeAt(0));
  const response = new Response([204, 205, 304].includes(result.status) ? null : bytes, {
    status: result.status, headers: result.headers,
  });
  Object.defineProperty(response, "url", { value: result.url });
  return response;
}

module.exports = { call, BrowserWindow, nativeFetch };
