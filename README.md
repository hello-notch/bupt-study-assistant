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
├─ web/                         Vue 3 + TypeScript 页面与本地开发适配器
├─ client/                      Electron 桌面壳与设备内运行时
│  ├─ local-runtime.cjs         校园、课表、电费和模型直连逻辑
│  └─ main.cjs / preload.cjs    安全 IPC 边界
├─ config/                      浏览器开发态的无凭据模型路由
├─ docs/                        当前架构和发布文档
└─ scripts/                     图标等本地构建辅助脚本
```

历史 NoneBot 代码、运行数据和 NapCat 不属于桌面客户端。QQ 机器人版本已独立维护在
[`hello-notch/amadeus-qq-bot`](https://github.com/hello-notch/amadeus-qq-bot)，两个产品互不作为运行依赖。

## 开发与运行

网页开发模式：

```powershell
cd .\web
pnpm install
pnpm run dev
```

网页开发模式不会在浏览器中保存密码或 API Key；校园与模型能力可继续从本机已忽略的 `.env` / `secrets/` 调试配置读取。正式本机配置流程应通过 Electron 客户端验证。

桌面客户端：

```powershell
cd .\web
pnpm run build
cd ..\client
pnpm install
pnpm start
```

也可在项目根目录双击 `run-client.cmd`。不再需要 `run-server.cmd`、远程 API 地址或自签名服务器证书。

## 构建

Windows 1.0.1 完整依赖版：

```powershell
cd .\client
pnpm run dist:win
```

产物为 `client/dist/YouXueBan-1.0.1-Windows-x64-full.zip`，压缩包内包含 `邮学伴.exe`、Electron 运行库、网页资源和 Playwright SDK，不需要另装 Node.js。认证会话失效时会优先寻找本机 Chromium，找不到才自动下载。


## 验证

```powershell
cd .\web
.\node_modules\.bin\vue-tsc.cmd --noEmit -p .\tsconfig.app.json
.\node_modules\.bin\tsc.cmd --noEmit -p .\tsconfig.node.json
.\node_modules\.bin\vite.cmd build
```

界面变更还需验证桌面与约 390px 手机宽度、无横向溢出、控制台无错误，以及欢迎、绑定、课表导入、助手配置和删除本机凭据流程。
