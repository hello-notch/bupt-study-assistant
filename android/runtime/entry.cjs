const { call, BrowserWindow, nativeFetch } = require("./platform.cjs");
const { createLocalRuntime } = require("../../client/local-runtime.cjs");

globalThis.fetch = nativeFetch;
globalThis.Buffer = { from: (value) => new Uint8Array(value) };
globalThis.process = { versions: { chrome: "130.0.0.0" } };
function makeRuntime(signal) { return createLocalRuntime({
  app: { getPath: () => "private" },
  BrowserWindow: class extends BrowserWindow {
    constructor(options) { super(options, signal); }
  },
  // Native file operations encrypt every stored value with Android Keystore.
  safeStorage: { isEncryptionAvailable: () => true, encryptString: (value) => value, decryptString: (value) => value },
  session: { fromPartition: () => ({ clearStorageData: () => call("clearSessions") }) },
}); }

const requests = new Map();
globalThis.__cancelRequest = (id) => requests.get(id)?.abort(new Error("操作已取消"));
globalThis.__request = async (id, route, init) => {
  const controller = new AbortController();
  requests.set(id, controller);
  const timer = setTimeout(() => controller.abort(new Error("请求超时，请检查网络后重试")), route === "/api/courses/mine" ? 65_000 : 180_000);
  try {
    const result = await Promise.race([
      makeRuntime(controller.signal).request(route, init),
      new Promise((_, reject) => controller.signal.addEventListener("abort", () => reject(controller.signal.reason), { once: true })),
    ]);
    NativeRuntime.reply(id, JSON.stringify(result));
  } catch (error) {
    NativeRuntime.reply(id, JSON.stringify({ status: controller.signal.aborted ? 408 : 500, body: { error: controller.signal.aborted ? error.message : "设备内运行时操作失败，请重试" } }));
  } finally {
    clearTimeout(timer);
    requests.delete(id);
  }
};
NativeRuntime.ready();
