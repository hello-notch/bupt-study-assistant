# 邮学伴

邮学伴是一套面向北邮学生的学习与校园信息助手，也是 `new_bot` 的独立代码副本。项目保留原有 NoneBot 业务层，并新增不依赖 QQ 界面的 Web 前端。

当前前端已经完成可交互 MVP：

- “今天”聚合下一节课、当日课程、近期 DDL 与校园动态；
- 任务列表、搜索、状态切换、新增、完成、恢复和删除；
- 桌面周课表、移动端课程时间线、课程编辑，以及可实际解析 XLS/XLSX/CSV 的三步导入向导；
- 信息门户通知与第二课堂活动的列表、搜索、详情和订阅状态；
- 不要求输入命令的 Amadeus 助手：服务端 AI 可用时进行开放式对话，不可用时明确切换本地学习数据助手；
- 通知中心、浅色/深色模式、默认提醒、静默时段和隐私开关；
- 桌面侧边栏与移动端底部导航，最小支持 320px 宽度。

任务、课程、校园已读状态和设置当前使用 `localStorage` 持久化。Vite 本地服务提供两个仅服务端运行的薄接口：AI 对话会复用项目的 AI 路由与凭据文件，班级导入会使用已配置的教务系统会话。正式部署阶段仍应由 Web API / OneBot Bridge 接管持久化、鉴权和业务校验；界面不会向用户暴露 `/ddl`、`/course` 等兼容命令。

## 目录

```text
bupt_study_assistant/
├─ web/                         # Vue 3 + TypeScript 前端
│  ├─ src/App.vue               # 页面、交互和本地状态
│  ├─ src/course-import.ts       # XLS/XLSX/CSV 课表解析
│  ├─ src/styles.css            # 响应式设计系统
│  ├─ src/demo-data.ts          # 可替换的演示数据
│  ├─ src/types.ts              # 前后端共享 DTO 草案
│  └─ dev-api.ts                # 开发模式 AI 与教务代理（密钥不进入浏览器）
├─ src/amadeus_bot/             # 从 new_bot 保留的 NoneBot 业务代码
├─ tests/                       # 原有后端测试
├─ docs/web-frontend-design.md  # 产品、架构和接口方案
├─ docs/legacy-bot-readme.md    # 原机器人说明备份
└─ run-web.ps1                  # 本机前端启动入口
```

没有复制原项目的 `.env`、`secrets/`、用户数据库、日志、缓存或 `.venv`。这些内容包含运行状态或敏感信息，不应成为课程项目副本的一部分。

## 独立运行说明

本目录不依赖 `D:\Bots` 下的 `new_bot`、NapCat 或其他兄弟目录。复制或克隆整个 `bupt_study_assistant` 目录后即可独立安装与运行：

- 只使用网页、本地任务、文件课表导入和本地助手时，仅需要 Node.js 20+ 与 `pnpm install`；
- 启用在线 AI 或按班级导入时，在项目内根据 `.env.example` 创建自己的 `.env` 和 `secrets/`，不要复制到仓库；
- 运行保留的 NoneBot 后端时，需要 Python 3.12 和 `uv sync`，但网页基础功能不依赖 NoneBot 进程。

## 运行前端

依赖已经在当前工作区安装。Windows 下推荐双击 `run-web.cmd`，或者在终端运行：

```powershell
.\run-web.cmd
```

然后访问 <http://127.0.0.1:5173/>。

也可以显式使用 PowerShell 7，并按需指定端口：

```powershell
pwsh -NoLogo -NoProfile -File .\run-web.ps1 -Port 5173
```

如果系统提示 `running scripts is disabled on this system`，说明 Windows PowerShell 5.1 的执行策略阻止了 `.ps1`，不是前端代码错误。直接使用 `run-web.cmd` 即可，不需要修改系统执行策略。

在一台新电脑上首次安装：

```powershell
cd .\web
pnpm install
pnpm run dev
```

生产构建：

```powershell
cd .\web
pnpm run build
```

构建结果位于 `web/dist/`。

### AI 与班级课表接入

开发服务会读取项目根目录 `.env`，但不会把凭据注入浏览器：

- `AMADEUS_API_KEY_FILE`：现有 `apikey.txt` 路径；模型与供应商仍来自 `config/ai_routes.toml` 的 `tasks.chat`。
- `AMADEUS_JWGL_COOKIE_FILE`：教务系统 Cookie 请求头文件路径，用于“按班级导入”。

没有配置 AI 时，聊天页会明确显示“本地模式”，仍可查询当前课程、DDL、校园条目、生成学习安排和用自然语言创建任务。没有配置教务会话时，班级导入会显示具体错误，文件导入不受影响。

`demo-data.ts` 中的校园条目是注明为演示的内容，“查看原文”会打开相应官方来源网站；接入真实校园缓存后，前端直接使用后端保存的具体 `url`。

## 前端交互原则

- 页面主要使用按钮、表单、筛选器、日历和自然语言，不要求学生学习机器人命令；
- 写操作在提交前展示结构化结果，删除和覆盖操作要求确认；
- 第二课堂保持只读，不提供报名、签到和退选；
- 数据源错误、空结果和离线状态必须分别呈现；
- 后端接入时由服务层执行权限、时间解析、冲突检查和审计，浏览器只负责交互与展示。

## 后端说明

保留的 NoneBot 能力、校园凭据配置与机器人运行方式见 [原机器人说明](docs/legacy-bot-readme.md)。Web 版的架构、OneBot Bridge 最小兼容面、原生 API 草案和验收标准见 [前端设计方案](docs/web-frontend-design.md)。
