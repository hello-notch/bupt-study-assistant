const ATTEMPTS = 5;
const DELAY_MS = 4_000;
const ATTEMPT_TIMEOUT_MS = 60_000;

function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, ms);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
  });
}

async function retryCampus(label, operation, signal, options = {}) {
  const delay = options.delay ?? DELAY_MS;
  const timeout = options.timeout ?? ATTEMPT_TIMEOUT_MS;
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    signal?.throwIfAborted();
    const controller = new AbortController();
    const abort = () => controller.abort(signal.reason);
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(() => controller.abort(new Error("本次读取超时")), timeout);
    let onAbort;
    try {
      return await Promise.race([
        operation(attempt, controller.signal),
        new Promise((_, reject) => {
          onAbort = () => reject(controller.signal.reason);
          controller.signal.addEventListener("abort", onAbort, { once: true });
          if (controller.signal.aborted) onAbort();
        }),
      ]);
    } catch (error) {
      signal?.throwIfAborted();
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      controller.signal.removeEventListener("abort", onAbort);
      controller.abort(new Error("本次操作已结束"));
    }
    if (attempt < ATTEMPTS) await pause(delay, signal);
  }
  // Do not expose raw upstream errors, which can contain tokens or personal data.
  throw new Error(`${label}自动刷新失败（已尝试 ${ATTEMPTS} 次），请检查校园网、账号密码或到官方页面完成验证码后重试`);
}

module.exports = { retryCampus, ATTEMPTS, DELAY_MS, ATTEMPT_TIMEOUT_MS };
