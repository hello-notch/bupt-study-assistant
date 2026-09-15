# 邮学伴

邮学伴是面向北邮学生的本地优先学习与校园信息助手。Windows EXE 加载安装包内的 Vue 页面，不需要部署或启动邮学伴服务端，也没有邮学伴账密登录。

## 当前功能

- 首次打开只询问昵称，背景为带碰撞和变色效果的跳动圆球；昵称、任务、课程、宿舍号、对话和偏好保存在当前设备。
- 进入主页后提示分别绑定“北邮统一身份认证”和“教务系统”两套账号。密码仅用于设备内登录校园系统，可在设置中修改或删除；保存本机凭据不会修改学校系统真实密码，也不会自动读取课表。
- 课程页提供“一键导入我的课表”和 XLS/XLSX/CSV 文件导入，导入前均可预览并选择课程。
- 信息门户通知、第二课堂活动及信息门户“待办中心”条目会进入校园页；待办中心会优先显示在“今天”，每项保留对应链接。
- 电费仍以楼宇和宿舍号为查询条件，例如 `A410`、`S2-410` 或 `学8 321`。
- 学习助手当前仅支持 DeepSeek 官方 API，地址固定为 `https://api.deepseek.com`。首次使用时要求填写 API Key，可在三个受支持模型间切换；未配置前不会发送模型请求。
- 设置可修改或删除校园账号与模型配置。Windows 使用 Electron `safeStorage` 加密保存敏感信息；前端 `localStorage` 不保存账号密码或 API Key。

第二课堂只提供查询、查看和订阅，不提供报名、签到或退选。校园系统登录遇到验证码、页面结构变化或鉴权失败时会显示真实失败原因，不会用演示数据伪装成功。

## 目录

```text
bupt_study_assistant/
├─ web/                         桌面应用的 Vue 3 + TypeScript 页面
├─ client/                      Electron 桌面壳与设备内运行时
│  ├─ local-runtime.cjs         校园、课表、电费和模型直连逻辑
│  └─ main.cjs / preload.cjs    安全 IPC 边界
├─ docs/                        当前架构和发布文档
├─ scripts/                     桌面启动、课表回归测试与图标工具
└─ run-client.cmd               构建源码并直接打开桌面应用
```

历史 NoneBot 代码、运行数据和 NapCat 不属于桌面客户端。QQ 机器人版本已独立维护在
[`hello-notch/amadeus-qq-bot`](https://github.com/hello-notch/amadeus-qq-bot)，两个产品互不作为运行依赖。

## 开发与运行

首次准备（需要 Node.js 22 和 pnpm）：

```powershell
pnpm --dir web install --frozen-lockfile
pnpm --dir client install --frozen-lockfile
```

双击根目录 `run-client.cmd`，或运行：

```powershell
.\run-client.cmd
```

启动器每次先检查类型并重新构建页面，再打开 Electron 桌面窗口，不启动网页服务器，也不生成发布包。缺少依赖或构建失败时显示错误，双击启动时窗口会保留供查看。修改源码后关闭测试窗口、重新运行即可；验收后再执行发布构建。

测试版使用开发客户端自己的本机用户目录，不自动迁移已安装版本的数据；首次可能需要填写昵称和重新绑定校园账号。不要同时打开多个源码测试窗口。

已移除旧 `run-web.cmd`、`run-web.ps1`、`web/dev-api.ts` 及网页专用配置模板。`web/` 仍是桌面 UI 源码，不能删除。本机 `.env`、`secrets/`、`data/`、`logs/` 保留但不再是桌面依赖；不会自动删除其中的个人资料。

课表导入按课程名、星期、起止节次、周次、教师与地点识别同一安排。同名同时段的分周授课分别保留；重复导入相同安排不会新增副本。旧版已漏掉的课程需要重新导入原课表。

## 构建

当前发布版本为 `1.1.0`。

Windows 1.1.0 完整依赖版：

```powershell
cd .\client
pnpm run dist:win
```

产物为 `client/dist/YouXueBan-1.1.0-Windows-x64-full.zip`，压缩包内包含 `邮学伴.exe`、Electron 运行库、网页资源和 Playwright SDK，不需要另装 Node.js。认证会话失效时会优先寻找本机 Chromium，找不到才自动下载。完整更新记录见 [`docs/release-1.1.0.md`](docs/release-1.1.0.md)。


## 验证

运行 `pnpm --dir client test` 验证本地运行时和两种课表导入的分周保留规则。

```powershell
cd .\web
.\node_modules\.bin\vue-tsc.cmd --noEmit -p .\tsconfig.app.json
.\node_modules\.bin\tsc.cmd --noEmit -p .\tsconfig.node.json
.\node_modules\.bin\vite.cmd build
```

界面变更还需验证桌面与约 390px 手机宽度、无横向溢出、控制台无错误，以及欢迎、绑定、课表导入、助手配置和删除本机凭据流程。
