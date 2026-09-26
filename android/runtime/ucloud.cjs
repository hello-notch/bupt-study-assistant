const shared = require("../../client/ucloud.cjs");

function sessionScript() {
  return `(() => {
    if (location.hostname !== 'ucloud.bupt.edu.cn') return null;
    const cookies = Object.fromEntries(document.cookie.split(';').map(part => {
      const index = part.indexOf('=');
      let value = part.slice(index + 1);
      try { value = decodeURIComponent(value); } catch {}
      return [part.slice(0, index).trim().replace(/^iClass-/, ''), value];
    }));
    if (!cookies.token) return null;
    let user = {};
    try { user = JSON.parse(cookies['user-info'] || '{}') || {}; } catch {}
    if (!user.id || !user.account) {
      try {
        // Current uCloud pages no longer persist the user-info cookie.
        // Claims identify the session only; the upstream API validates the token.
        const encoded = cookies.token.replace(/^bearer\\s+/i, '').split('.')[1]
          .replace(/-/g, '+').replace(/_/g, '/');
        const bytes = Uint8Array.from(atob(encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=')), c => c.charCodeAt(0));
        const claims = JSON.parse(new TextDecoder().decode(bytes));
        user = { id: claims.user_id, account: claims.account };
      } catch { return null; }
    }
    if (!['string', 'number'].includes(typeof user.id) || !String(user.id) ||
        typeof user.account !== 'string' || !user.account) return null;
    return { token: cookies.token, userId: String(user.id), account: user.account, identity: cookies.identity || '' };
  })()`;
}

function courseNameFallback(detail) {
  return typeof detail?.courseName === "string" && detail.courseName.trim()
    ? detail.courseName.trim() : "课程名称未提供";
}

async function paged(load) {
  const rows = [];
  for (let current = 1; current <= 20; current++) {
    const page = await load(current);
    if (!Array.isArray(page?.records) || !Number.isInteger(Number(page.total)) || Number(page.total) < 0)
      throw new Error("教学云课程作业列表格式已变化");
    rows.push(...page.records);
    if (rows.length >= Number(page.total)) return rows;
    if (!page.records.length) break;
  }
  throw new Error("教学云课程作业列表不完整");
}

function createCourseResolver() {
  let index;
  return async (detail, row, request, auth) => {
    if (detail?.courseName?.trim()) return detail.courseName.trim();
    if (!index) index = (async () => {
      const sites = await paged(current => request(`/ykt-site/site/list/student/current?size=100&current=${current}`));
      const names = new Map();
      let next = 0;
      await Promise.all(Array.from({ length: Math.min(3, sites.length) }, async () => {
        while (next < sites.length) {
          const site = sites[next++];
          if (!site?.id || !site.siteName?.trim()) throw new Error("教学云课程名称缺失");
          // The official read-only list uses POST. Match assignment IDs, never teaching-class names.
          const assignments = await paged(current => request("/ykt-site/work/student/list", {
            method: "POST", body: JSON.stringify({ siteId: site.id, userId: auth.userId,
              keyword: "", chapterId: "", nodeId: "", current, size: 100,
              studentAssignmentStatus: "", status: "", sortColumn: "", sortType: null }),
          }));
          for (const item of assignments) {
            if (!item?.id) throw new Error("教学云课程作业缺少编号");
            const key = String(item.id);
            const previous = names.get(key);
            if (previous && previous.siteId !== String(site.id)) throw new Error("教学云作业所属课程不唯一");
            names.set(key, { name: site.siteName.trim(), siteId: String(site.id) });
          }
        }
      }));
      return names;
    })();
    return (await index).get(String(row.activityId)) || courseNameFallback(detail);
  };
}

module.exports = {
  loadUcloudAssignments: options => shared.loadUcloudAssignments({ ...options, readSessionScript: sessionScript, courseNameFallback: createCourseResolver() }),
  __test: { sessionScript, courseNameFallback, createCourseResolver },
};
