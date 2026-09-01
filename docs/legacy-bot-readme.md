# Amadeus QQ Bot

新版机器人采用 NapCat + NoneBot 2 + OneBot V11。设计方案中的本期功能已经全部接入；明确暂缓的重启/关闭、MATLAB，以及需要开发者提供有效校园登录会话的在线抓取除外。

## 当前能力

- SQLite 权限、功能开关、忽略规则、审计和推荐池。
- 统一命令注册表与按权限过滤的帮助图片。
- 大段文本图片渲染及内容寻址缓存。
- 分任务 AI 路由、供应商回退和 token/延迟统计。
- `help`/`/help`、角色聊天、主动接话、视觉描述缓存、wife、贴表情、戳一戳和安全 Markdown。
- DDL、课程表（班级/CSV/XLSX/手动）、推荐池与 DDL 临时候选、真实私聊提醒调度。
- 群统计、群总结、语录、跨群用户记忆、隐私退出及开发者记忆处理申请。
- 信息门户、第二课堂只读查询/订阅/每日推送、数据源健康状态和管理员导入降级方案。
- 权限成员管理、功能开关、日志诊断、备份/保留策略、健康和 AI 配额命令。
- AI 可代表当前请求者调用 DDL、课程、校园查询/订阅、统计上下文、wife、戳一次和贴一次表情等白名单工具；SUPERUSER 工具不进入 AI 注册表。

## 本地启动

项目通过 `pyproject.toml` 的 `tool.nonebot.plugin_dirs` 让 nb-cli 自动发现插件，因而可直接运行：

```powershell
nb run
```

仓库上级目录的 `run.bat` 会同时启动 NapCat 和该 NoneBot 项目。长期运行默认不启用
`--reload`；开发时可手动使用 `nb run --reload`。

也可以使用项目打包入口：

```powershell
uv sync --extra dev
Copy-Item -LiteralPath .env.example -Destination .env
uv run amadeus-bot
```

帮助图片只使用与项目 Playwright 版本匹配的 Chromium，不会调用系统 Edge 或 Chrome。首次部署需要执行 `uv run playwright install chromium`。

NapCat 的 OneBot V11 反向 WebSocket 地址应指向 NoneBot 配置的地址。API key 默认从受保护且被 Git 忽略的 `secrets/apikey.txt` 读取。

启动时会显式加载项目 `.env`，使 NoneBot 配置和使用 `os.getenv` 的业务服务读取同一组值；操作系统中已经存在的环境变量优先。

暂不阻塞基础运行的后续验收事项见 [`docs/deferred-issues.md`](docs/deferred-issues.md)。
模型、帮助、推荐池、数据库和日志的可编辑位置见
[`docs/customization.md`](docs/customization.md)。

## 额外配置

- `AMADEUS_PORTAL_COOKIE_FILE`：信息门户专用受保护 Cookie 请求头文件路径。
- `AMADEUS_ACTIVITY_TOKEN_FILE` 与 `AMADEUS_ACTIVITY_LIST_ENDPOINT`：第二课堂只读 Bearer token 文件和已确认的站内列表 API。不能确定接口时可由 SUPERUSER 回复 JSON/CSV 使用 `/activity import-file`。
- `AMADEUS_JWGL_COOKIE_FILE`：教务系统专用受保护 Cookie 请求头文件路径。原始请求头会保留同名 Cookie 的顺序，例如教务系统可能同时发送两个不同 Path 的 `JSESSIONID`。
- `AMADEUS_SEMESTER_START=YYYY-MM-DD`：本学期第 1 周周一，用于课程提醒。
- `AMADEUS_CAMPUS_PUSH_HOUR=8`：校园每日推送小时。

这些文件只保存可失效的短期会话副本，不保存账号密码，也不得提交；登录失效后由开发者刷新。配置脚本会尝试把 `secrets/` 的 Windows ACL 限制为当前用户和 SYSTEM。
机器人默认每 300 秒访问一次信息门户和教务系统以保持闲置会话，并检查第二课堂；可用 `AMADEUS_CAMPUS_REFRESH_SECONDS` 调整（最低 60 秒）。首次失败和恢复时会私聊 `SUPERUSER`，不会把凭据写入消息或日志。
若配置 `AMADEUS_PASSWORD_FILE`，会话失效时机器人会使用 Playwright Chromium 打开真实登录页，读取文件第一行账号和第二行密码完成登录，更新原始 Cookie 请求头并重试一次。凭据内容不会写入日志；遇到验证码或登录策略变化时停止重试并报告失败。

信息门户的统一认证目前会向无头 Chromium 的登录 iframe 返回 HTTP 400，因此门户续登默认使用 `AMADEUS_PORTAL_BROWSER_HEADLESS=false`：仅在门户会话失效时短暂出现 Playwright Chromium 窗口，登录完成后自动关闭。第二课堂直接登录要求网页验证时也会使用同样的临时浏览器流程，默认 `AMADEUS_ACTIVITY_BROWSER_HEADLESS=false`；获取新 token 后立即关闭。教务续登仍默认无头运行。三者都只使用 Playwright 安装的 Chromium，不调用系统 Edge 或 Chrome。

### 配置校园登录凭据

不要把 Cookie 或 token 发到聊天，也不要把它们直接写入 `.env`。运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\configure_campus_secrets.py
```

脚本使用隐藏输入，将凭据保存到已被 Git 忽略的 `secrets/`，并输出一行不含凭据的 `.env` 路径配置。

- 信息门户：在已登录的 `my.bupt.edu.cn` 页面打开开发者工具 → Network，刷新页面，选择发往 `my.bupt.edu.cn` 而不是 CAS 登录页的请求，在 Request Headers 中复制完整 `Cookie` 值，选择脚本选项 1。
- 教务系统：在已登录的 `jwgl.bupt.edu.cn/jsxsd` 页面以同样方式复制请求的完整 `Cookie` 值，选择选项 2。
- 第二课堂：在已登录的 `dekt.bupt.edu.cn` 页面打开 Network，筛选 `api/v1`，选择加载活动列表的 GET 请求，复制 `Authorization: Bearer ...` 的值，选择选项 3。同时把该请求 URL 中域名后的只读路径写成 `AMADEUS_ACTIVITY_LIST_ENDPOINT=/api/v1/...`。

信息门户和教务 Cookie 到期后可重新运行脚本覆盖对应文件。第二课堂 token 缺失或到期时，如果已配置 `AMADEUS_PASSWORD_FILE`，机器人会通过官方网站的登录页自动续签并原子更新 token 文件；遇到交互验证码或登录策略变化时停止重试并报告失败，也可重新运行脚本手工更新。机器人只读取这些凭据进行查询，不实现报名、签到或退选请求。

## 安全约束

- `apikey.txt`、`.env*`、`data/` 和 `logs/` 禁止提交。
- SUPERUSER 命令不会注册为 AI 工具。
- AI 的 MEMBER 委托能力只对显式白名单工具和当前请求生效。
- 第二课堂只读查询与推送，永不自动报名、签到或退选。
