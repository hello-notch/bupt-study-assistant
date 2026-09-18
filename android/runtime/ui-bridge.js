(() => {
  if (!window.AndroidUI) return;
  const pending = new Map();
  let sequence = 0;
  window.__androidReply = (id, result) => {
    const item = pending.get(id);
    if (!item) return;
    pending.delete(id);
    clearTimeout(item.timer);
    item.resolve(result);
  };
  window.youxuebanRuntime = {
    request(route, init = {}, signal) {
      const id = String(++sequence);
      return new Promise((resolve, reject) => {
        if (signal?.aborted) { reject(signal.reason); return; }
        const abort = () => {
          pending.delete(id);
          clearTimeout(timer);
          AndroidUI.cancel(id);
          reject(signal.reason);
        };
        const timer = setTimeout(() => {
          pending.delete(id);
          signal?.removeEventListener("abort", abort);
          AndroidUI.cancel(id);
          resolve({ status: 504, body: { error: "设备请求超时，请检查网络后重试" } });
        }, 240_000);
        signal?.addEventListener("abort", abort, { once: true });
        pending.set(id, { resolve: result => { signal?.removeEventListener("abort", abort); resolve(result); }, timer });
        AndroidUI.request(id, String(route), JSON.stringify(init));
      });
    },
    notify: async (title, body) => AndroidUI.notify(String(title), String(body)),
  };
})();
