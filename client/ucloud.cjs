const UCLOUD_HOME = "https://ucloud.bupt.edu.cn/uclass/#/student/homePage";
const UCLOUD_LOGIN = "https://auth.bupt.edu.cn/authserver/login?service=http://ucloud.bupt.edu.cn/uclass";
const UCLOUD_API = "https://apiucloud.bupt.edu.cn";
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

class UcloudAuthError extends Error {}

function sessionScript() {
  return `(() => {
    if (location.hostname !== 'ucloud.bupt.edu.cn') return null;
    const cookies = Object.fromEntries(document.cookie.split(';').map(part => {
      const index = part.indexOf('=');
      let value = part.slice(index + 1);
      try { value = decodeURIComponent(value); } catch {}
      return [part.slice(0, index).trim().replace(/^iClass-/, ''), value];
    }));
    try {
      const user = JSON.parse(cookies['user-info'] || '{}');
      return cookies.token && user.id ? {
        token: cookies.token, userId: String(user.id), account: String(user.account || ''),
        identity: cookies.identity || ''
      } : null;
    } catch { return null; }
  })()`;
}

function loginScript(account, password, submit) {
  return `(() => {
    if (location.hostname !== 'auth.bupt.edu.cn') return null;
    const target = document.querySelector('#loginIframe')?.contentWindow || window;
    if (target.location.hostname !== 'auth.bupt.edu.cn') return null;
    const doc = target.document;
    const user = doc.querySelector('#username, input[name="学工号"], input[autocomplete="username"]');
    const pass = doc.querySelector('#password, input[type="password"]');
    if (!user || !pass) return null;
    const error = doc.querySelector('.error-message, #msg')?.textContent?.trim();
    if (!${submit}) return { error: Boolean(error) };
    const tabs = [...doc.querySelectorAll('a[href="javascript:;"]')];
    tabs[1]?.click();
    const set = (el, value) => {
      Object.getOwnPropertyDescriptor(target.HTMLInputElement.prototype, 'value').set.call(el, value);
      el.dispatchEvent(new target.Event('input', { bubbles: true }));
      el.dispatchEvent(new target.Event('change', { bubbles: true }));
    };
    set(user, ${JSON.stringify(account)});
    set(pass, ${JSON.stringify(password)});
    const captcha = doc.querySelector('#cptValue, .img-code');
    if (!captcha?.offsetParent)
      [...doc.querySelectorAll('input.submit-btn, button[type=submit]')].find(el => el.offsetParent)?.click();
    return { submitted: true };
  })()`;
}

async function readSession(window, campus, interactive, forceLogin = false, staleToken = "") {
  // CAS/SPA navigations need not finish all subresources to become usable.
  // Android can also drop an evaluate callback when its document redirects.
  const navigate = url => { void window.loadURL(url).catch(() => {}); };
  const evaluate = async script => {
    let timer;
    try {
      return await Promise.race([
        window.webContents.executeJavaScript(script),
        new Promise(resolve => { timer = setTimeout(() => resolve(null), 2500); }),
      ]);
    } catch { return null; }
    finally { clearTimeout(timer); }
  };
  navigate(forceLogin ? UCLOUD_LOGIN : UCLOUD_HOME);
  const started = Date.now();
  let loginStarted = forceLogin, submitted = false, reopened = false;
  while (Date.now() - started < (interactive ? 100_000 : 15_000)) {
    if (window.isDestroyed()) throw new UcloudAuthError("教学云登录已取消");
    const host = new URL(window.webContents.getURL()).hostname;
    if (host === "ucloud.bupt.edu.cn") {
      const value = await evaluate(sessionScript());
      if (value && value.token !== staleToken) {
        if (value.account !== campus.ssoAccount) throw new UcloudAuthError("教学云登录账号与绑定账号不一致，请重新绑定校园账号");
        return value;
      }
      // The CAS callback can stall after setting cookies. Reopen the home once.
      if (loginStarted && !reopened && Date.now() - started > 12_000) {
        reopened = true;
        navigate(UCLOUD_HOME);
      }
    }
    if (!interactive && host === "auth.bupt.edu.cn") break;
    if (interactive && host === "auth.bupt.edu.cn") {
      const state = await evaluate(loginScript(campus.ssoAccount, campus.ssoPassword, !submitted));
      if (state?.submitted) submitted = true;
      if (state?.error) throw new UcloudAuthError("教学云统一认证失败，请检查账号或完成验证码");
      if (!submitted || state?.submitted) void Promise.resolve(window.show()).catch(() => {});
      loginStarted = true;
    } else if (interactive && !loginStarted && Date.now() - started > 2500) {
      loginStarted = true;
      navigate(UCLOUD_LOGIN);
    }
    await pause(400);
  }
  throw new UcloudAuthError(interactive ? "教学云登录未完成，请在校内网重试并完成统一认证" : "教学云需要登录，请连接校内网后点击同步作业");
}

async function apiGet(path, auth, fetchImpl, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  const timer = setTimeout(() => controller.abort(new Error("教学云请求超时")), 25_000);
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) abort();
  try {
    const response = await fetchImpl(`${UCLOUD_API}${path}`, {
      headers: {
        Authorization: "Basic c3dvcmQ6c3dvcmRfc2VjcmV0",
        "Tenant-Id": "000000",
        "Blade-Auth": auth.token,
        ...(auth.identity ? { identity: auth.identity } : {}),
        "Cache-Control": "no-cache",
      },
      redirect: "error",
      signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403) throw new UcloudAuthError("教学云会话已过期，请重新同步");
    if (!response.ok) throw new Error(`教学云请求失败（HTTP ${response.status}）`);
    let payload;
    try { payload = await response.json(); } catch { throw new Error("教学云响应不是有效数据，请确认校内网连接"); }
    if ([401, 403].includes(Number(payload?.code))) throw new UcloudAuthError("教学云会话已过期，请重新同步");
    if (Number(payload?.code) !== 200 || payload?.success === false || payload.data == null)
      throw new Error("教学云返回业务错误，本次未更新作业");
    return payload.data;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

function undoneRows(data) {
  if (!data || !Array.isArray(data.undoneList)) throw new Error("教学云待办格式已变化，本次未更新作业");
  if (data.undoneList.some(row => !row || ![1, 2, 3, 4, 5].includes(Number(row.type))))
    throw new Error("教学云待办类别无法识别，本次未更新作业");
  // The official endpoint returns the complete list; paging happens in the UI.
  if (data.undoneNum != null && Number(data.undoneNum) !== data.undoneList.length)
    throw new Error("教学云待办列表不完整，本次未更新作业");
  const rows = data.undoneList.filter(row => Number(row?.type) === 3);
  if (rows.some(row => !row.activityId || !String(row.activityName || "").trim()))
    throw new Error("教学云作业缺少标识或标题，本次未更新作业");
  return [...new Map(rows.map(row => [String(row.activityId), row])).values()];
}

function deadline(value) {
  if (value == null || value === "") return "";
  let date;
  if (typeof value === "number") date = new Date(value < 1e12 ? value * 1000 : value);
  else {
    let text = String(value).trim().replace(" ", "T");
    // Campus timestamps without a zone are China time, not the device timezone.
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(text)) text += "+08:00";
    date = new Date(text);
  }
  if (Number.isNaN(date.getTime())) throw new Error("教学云作业截止时间格式无法识别，本次未更新作业");
  return date.toISOString();
}

function assignmentItem(row, detail, courseName) {
  if (!detail || typeof detail.assignmentContent !== "string" || !String(detail.assignmentTitle || "").trim() || !courseName)
    throw new Error("教学云作业详情或课程名缺失，本次未更新作业");
  if (detail.assignmentContent.length > 200_000) throw new Error("教学云作业正文过大，本次未更新作业");
  const params = new URLSearchParams({
    activeTabName: "first", assignmentId: String(row.activityId),
    assignmentType: String(detail.assignmentType ?? row.assignmentType ?? 0),
  });
  return {
    sourceId: String(row.activityId),
    courseId: String(detail.siteId || row.siteId || ""),
    course: String(courseName).trim(),
    title: `[作业][${String(courseName).trim()}]${detail.assignmentTitle.trim()}`,
    contentHtml: detail.assignmentContent,
    dueAt: deadline(detail.assignmentEndTime ?? row.endTime),
    url: `https://ucloud.bupt.edu.cn/uclass/course.html#/student/assignmentDetails_fullpage?${params}`,
  };
}

async function fetchAssignments(auth, fetchImpl = fetch, signal) {
  const get = path => apiGet(path, auth, fetchImpl, signal);
  const data = await get(`/ykt-site/site/student/undone?userId=${encodeURIComponent(auth.userId)}`);
  const rows = undoneRows(data);
  const courses = new Map();
  const items = [];
  // A failed detail prevents reconciliation, so no unfinished item is marked submitted.
  for (const row of rows) {
    const detail = await get(`/ykt-site/work/detail?assignmentId=${encodeURIComponent(row.activityId)}`);
    const siteId = detail.siteId || row.siteId;
    let name = detail.siteName || row.siteName;
    if (!name && siteId) {
      if (!courses.has(String(siteId))) {
        const site = await get(`/ykt-site/site/detail?id=${encodeURIComponent(siteId)}`);
        courses.set(String(siteId), site?.siteName);
      }
      name = courses.get(String(siteId));
    }
    items.push(assignmentItem(row, detail, name));
  }
  return items;
}

async function loadUcloudAssignments({ window, campus, interactive = false }) {
  try {
    let auth = await readSession(window, campus, interactive);
    try { return await fetchAssignments(auth, fetch, window.signal); }
    catch (error) {
      if (!(error instanceof UcloudAuthError) || !interactive) throw error;
      auth = await readSession(window, campus, true, true, auth.token);
      return await fetchAssignments(auth, fetch, window.signal);
    }
  } finally { if (!window.isDestroyed()) window.destroy(); }
}

module.exports = { loadUcloudAssignments, __test: { sessionScript, undoneRows, deadline, assignmentItem, fetchAssignments } };
