# 邮学伴

邮学伴是面向北邮学生的学习与校园信息助手，也是原机器人项目的独立备份。课程项目以 Vue 3 + TypeScript 网页作为完整软件界面；保留的 NoneBot 业务代码可在课程结束后继续用于 QQ 机器人模式。

## 当前功能

- 首次打开使用独立动画欢迎页询问称呼，不预置任务、课程、通知或校园演示条目；
- “今天”显示实时日期与时间、当日课程、近期任务、真实校园动态和可轮换学习建议；
- 任务支持创建、搜索、完成、恢复、删除、提前提醒，以及“静默时段仍提醒”；
- 课表支持 XLS/XLSX/CSV、本班教务查询、导入预览、替换/合并确认、周次切换和每天日期，并按北邮第 1–14 小节时间统一校正导入、编辑和展示结果；
- 校园页只读查询真实信息门户和第二课堂，信息门户通知可生成 AI 总结并以每次 10 条、最多 50 条分页展示；第二课堂分别呈现成功空结果、鉴权失败、网络失败与缓存状态；
- 查电费只需输入楼宇与宿舍号（如 `A410`、`S2-410`、`学8 321` 或 `学八321`），楼宇与宿舍号之间可使用横杠、空格或不加分隔符；“学n”中的 n 支持数字和汉字一至十。查询会自动补全校区、园区和楼层，西土城结果为剩余电量与剩余赠送电量之和，同时显示官方电费更新时间与本次查询时间；
- 学习助手使用 `DeepSeek-V4-Flash-Vision-Exp`，支持学习问答、课程/DDL/校园通知/电费工具调用、Markdown 与 LaTeX、按会话保存记录、非空会话二次确认删除、输入框自动增高、快速/思考模式切换，以及模型允许的 PNG/JPG/WebP 图片输入；对话区在视口内独立滚动并持续显示输入框，会话切换带滑块和内容淡入过渡；界面显示当前上下文 token 用量，接近路由配置的模型上限时停止发送并提示新建对话；首次回答后由 `deepseek-v4-flash` 生成 10 字内会话标题，API Key 只由服务端读取；
- 设置支持昵称与头像修改、个人信息二次确认重置、浅色/深色、学期起始日、任务提醒的分钟/小时/天单位和静默时段；关闭个性化记忆后助手不再接收历史消息与称呼，关闭学习数据分析后助手不再隐式接收本地课程、任务、校园和通知数据，首页也改用通用建议。

任务、课程、称呼、宿舍号、已读状态、助手对话和设置使用浏览器 `localStorage` 保存。API Key、教务 Cookie、门户 Cookie、第二课堂 token 和电费系统 Cookie 只由 Vite 服务端代理读取，不进入浏览器存储。助手图片单张限制为 1 MB、每条消息最多 2 张，以避免浏览器本地存储被快速占满。

## 目录

```text
bupt_study_assistant/
├─ web/
│  ├─ src/App.vue                 # 页面与交互
│  ├─ src/course-import.ts        # 真实课表文件解析
│  ├─ src/styles.css              # 响应式设计
│  ├─ src/types.ts                # 前端数据结构
│  └─ dev-api.ts                  # AI、教务与校园服务端代理
├─ scripts/read_web_campus_cache.py # 真实校园缓存读取
├─ src/                           # 保留的 NoneBot 业务层
├─ config/ai_routes.toml          # AI 路由
├─ docs/web-frontend-design.md    # 产品与架构方案
├─ .env.example                   # 无凭据配置模板
├─ run-web.cmd
└─ run-web.ps1
```

项目运行时不依赖 `D:\Bots\new_bot` 或 NapCat。当前工作区的 `.env`、`secrets/` 和 `data/` 已复制到本项目并由 Git 忽略；迁移到新电脑时需单独安全迁移这些本地文件。

## 启动

Windows 推荐在项目根目录运行：

```powershell
.\run-web.cmd
```

默认打开 <http://127.0.0.1:5173/>。也可指定端口：

```powershell
pwsh -NoLogo -NoProfile -File .\run-web.ps1 -Port 5174
```

首次安装前端依赖：

```powershell
cd .\web
pnpm install
```

首次进入会显示邮学伴账号登录页。注册前必须同意用户协议与隐私说明。桌面客户端可使用 Windows 系统加密安全保存账号密码，并分别控制“一键登录”和“下次自动登录”；退出账号会清除登录凭据，但不会删除本机任务、课程、对话和个人资料。

日常使用先双击 `run-server.cmd` 启动完整服务端代理，再双击 `run-client.cmd` 启动桌面客户端。前者复用 `web/dev-api.ts` 中已经实现的信息门户、第二课堂、教务、电费和 AI 接口，避免落到 `server/index.mjs` 尚未完成的占位接口。首次使用前分别在 `web/` 与 `client/` 执行一次 `pnpm install`。

生产构建：

```powershell
cd .\web
pnpm run build
```

## 在线能力配置

复制 `.env.example` 为 `.env`，并把真实凭据放在项目内已忽略的 `secrets/`：

- `YOUXUEBAN_API_KEY_FILE`、`YOUXUEBAN_AI_ROUTES_FILE`：在线 AI；
- `YOUXUEBAN_JWGL_COOKIE_FILE`：按班级查询教务课表；
- `YOUXUEBAN_CAMPUS_PASSWORD_FILE`：仅供信息门户、教务系统和第二课堂会话失效后自动续登录；
- `YOUXUEBAN_PORTAL_COOKIE_FILE`：信息门户通知；
- `YOUXUEBAN_ACTIVITY_TOKEN_FILE`、`YOUXUEBAN_ACTIVITY_LIST_ENDPOINT`：第二课堂只读活动；
- `YOUXUEBAN_ELECTRICITY_COOKIE_FILE`、`YOUXUEBAN_ELECTRICITY_QUERY_URL`：官方电费余额与更新时间查询；
- `YOUXUEBAN_SEMESTER_START`：第 1 周起始日，用于周次与日期计算；周课表仍按周一至周日排列。

信息门户、教务系统和电费系统的 Cookie 会自然过期。首次运行 `python scripts/configure_campus_secrets.py` 并选择 6，将统一认证账号和密码保存到受保护的 `secrets/campus-password.txt`；此后信息门户、教务系统和第二课堂在确认鉴权失效时会自动续登录、原子更新 Cookie 或 token，并只重试原请求一次。多个并发请求会共用同一次续期，避免重复登录。信息门户和第二课堂遇到网站验证时可能短暂打开项目 Playwright Chromium；遇到验证码、密码错误或页面变化会停止并明确报错，不会无限重试。

校园页会明确区分在线、缓存和失效状态。也可运行 `python scripts/configure_campus_cookies_gui.py` 手工保存信息门户、教务系统和电费系统 Cookie，电费会话写入 `secrets/electricity-cookie.txt`。第二课堂在线接口返回 0 条时表示当前没有进行中的活动，不等同于连接失败。电费系统暂不参与统一的自动续期，失效时仍需手工更新其 Cookie。

会话失效时页面会明确提示更新相应凭据，不会显示演示结果。第二课堂只实现查询、查看和订阅，不提供报名、签到或退选操作。

## 验证

```powershell
cd .\web
.\node_modules\.bin\vue-tsc.cmd --noEmit -p .\tsconfig.app.json
.\node_modules\.bin\tsc.cmd --noEmit -p .\tsconfig.node.json
.\node_modules\.bin\vite.cmd build
```

界面修改还应在桌面和约 390px 宽度下实际验证欢迎界面、表单、课表切换、覆盖确认、AI 错误态与校园空状态。
