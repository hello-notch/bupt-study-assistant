# 邮学伴

邮学伴是面向北邮学生的本地优先学习与校园信息助手，现提供 Windows 客户端与 Android 客户端。两端加载安装包内的共享 Vue 页面，不需要部署或启动邮学伴服务端，也没有邮学伴账密登录。

## 当前功能

- 首次打开只询问昵称，背景为带碰撞和变色效果的跳动圆球；昵称、任务、课程、宿舍号、对话和偏好保存在当前设备。
- 进入主页后提示分别绑定“北邮统一身份认证”和“教务系统”两套账号。密码仅用于设备内登录校园系统，可在设置中修改或删除；保存本机凭据不会修改学校系统真实密码，也不会自动读取课表。
- 课程页提供“一键导入我的课表”和 XLS/XLSX/CSV 文件导入，导入前均可预览并选择课程。
- 手机课表按所选周隐藏无课周末、压缩整周空节次，并裁掉最后一节课之后的空行；仍可通过添加课程按钮补充隐藏时段的课程。
- 任务页可通过已绑定的统一身份认证同步教学云作业，读取课程名、标题、正文及截止时间。安卓按日程开始/待办截止时间排序，Windows 保持自定义任务优先；待交作业不可手动完成或删除，完整同步后从平台待办消失的作业自动变为“已提交”，此时可以删除。
- 课程详情提供“查看作业”，进入任务页并筛选当前课程的全部已同步作业，包括已提交记录。
- 信息门户通知、第二课堂活动及信息门户“待办中心”条目会进入校园页；待办中心会优先显示在“今天”，每项保留对应链接。
- 电费仍以楼宇和宿舍号为查询条件，例如 `A410`、`S2-410` 或 `学8 321`。
- 学习助手当前仅支持 DeepSeek 官方 API，地址固定为 `https://api.deepseek.com`。首次使用时要求填写 API Key，可在受支持模型间切换；未配置前不会发送模型请求。
- 设置可修改或删除校园账号与模型配置。Windows 使用 Electron `safeStorage` 加密保存敏感信息；前端 `localStorage` 不保存账号密码或 API Key。

第二课堂只提供查询、查看和订阅，不提供报名、签到或退选。校园系统登录遇到验证码、页面结构变化或鉴权失败时会显示真实失败原因，不会用演示数据伪装成功。

### Android 任务与活动

- 安卓任务分为日程和待办：日程保存开始/结束时间并在开始前提醒，待办只保存截止时间并在截止前提醒。旧任务自动作为待办保留，日程页同时列出未来七天课程。
- 第二课堂与课程或未完成日程直接重叠时显示红色“时间冲突”；双方起止时间各扩展十分钟后才重叠时显示黄色“时间冲突”。端点恰好相接不算直接重叠，间隔恰好二十分钟不算缓冲冲突。待办不占用时间段。
- 活动可以“加入日程”并防止重复添加；“提醒报名”默认在报名前五分钟通知，可在设置中调整为 0 至 10080 分钟，也可在活动或设置中取消。修改设置会重排已保存的报名提醒。
- 提醒由 Android 原生闹钟持久化调度；进入提前提醒窗口才添加的未到期任务会补提醒，已发送的相同提醒不会因为刷新重复通知。需开启系统通知和相应系统权限。课程/任务遵循静默时段；主动订阅的报名提醒不受静默时段限制。
- 教学云兼容缺失 `user-info` Cookie 的登录会话；上游课程 ID 无效时保留真实作业，分类明确显示“教学班”或“课程名称未提供”，不会因课程名缺失丢弃整次同步。身份校验、失败保留和完整快照校验仍然生效。

以上新行为仅在安卓启用；安卓状态迁移至 `youxueban-state-android-v11`，旧状态保留为迁移来源，Windows 继续使用 `youxueban-state-v10`。

## 目录

```text
bupt_study_assistant/
├─ web/                         桌面应用的 Vue 3 + TypeScript 页面
├─ client/                      Electron 桌面壳与设备内运行时
│  ├─ local-runtime.cjs         校园、课表、电费和模型直连逻辑
│  └─ main.cjs / preload.cjs    安全 IPC 边界
├─ android/                     Android 原生壳、安全桥接与校园认证适配
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

Android 当前源码构建版本为 `1.2.1`，上一发布版说明见 [`docs/release-1.2.0.md`](docs/release-1.2.0.md)。本次改进仅面向 Android，不自动上传或发布；Windows 已发布版本仍为 `1.1.0`。

Windows 1.1.0 完整依赖版：

```powershell
cd .\client
pnpm run dist:win
```

产物为 `client/dist/YouXueBan-1.1.0-Windows-x64-full.zip`，压缩包内包含 `邮学伴.exe`、Electron 运行库、网页资源和 Playwright SDK，不需要另装 Node.js。认证会话失效时会优先寻找本机 Chromium，找不到才自动下载。完整更新记录见 [`docs/release-1.1.0.md`](docs/release-1.1.0.md)。


## 验证

### Android

Android 版提供本机任务、课程、文件课表导入、校园信息、电费和学习助手，并针对手机调整导航、课表和触摸交互。敏感配置使用 Android Keystore 保护，校园认证使用独立 WebView；生成的网页资源、SDK、本机配置与签名密钥不提交仓库。

准备 Android SDK 35、build-tools 35.0.0、JDK 17 或 21 和兼容的 Gradle 后：

```powershell
pwsh -NoProfile -File .\scripts\build-android.ps1 -SdkRoot "<Android-SDK>" -JavaHome "<JDK>" -Gradle "<gradle.bat>"
```

默认输出为 `android/app/build/outputs/apk/debug/YouXueBan-1.2.0-Android-test.apk`，属于 Debug 测试包，并非正式签名发布包。构建会重新生成共享网页及 Android 运行时资源。连接已授权的手机后可通过 `adb install -r` 覆盖安装同签名测试包；开发与验收要求见 `AGENTS.md` 第 12 节。

正式发布需配置本机签名并为上述构建命令添加 `-Release`，输出为 `android/app/build/outputs/apk/release/YouXueBan-1.2.0-Android.apk`。签名、验证和升级注意事项见 [`docs/android-release.md`](docs/android-release.md)。正式签名与旧 Debug 测试包不同，不能直接覆盖安装；卸载会删除本机数据，请先保留重要内容。

教学云需要校内网环境。首次点击“同步作业”完成统一认证；应用启动、回到前台及运行期间会尝试自动更新（定时检查间隔五分钟），不会在后台自动弹出认证窗口。登录失效、网络异常或详情读取不完整时保留已有记录，不据此判定作业已提交。当前只同步学生首页的作业待办，不导入讨论、调查、测验或互评任务，也不代替用户提交作业。已提交记录来自此前同步过的待办，不会回溯导入全部历史作业。

接入约定与验证边界见 `docs/android-homework.md`。

安卓返回键与手势可返回编辑前一层；空周课表显示完整节次。系统提醒使用原生持久化闹钟队列，需在设置中检查通知和“闹钟和提醒”权限，并允许手机后台运行。Flash 图片附件支持压缩后发送；DeepSeek Files API 的图片支持不等于任意 PDF/Word 文档支持。实现与验收边界见 `docs/android-refinements.md`。

### 自动化验证

运行 `pnpm --dir client test` 验证本地运行时和两种课表导入的分周保留规则。

构建网页后，`node scripts/mobile-ui.test.cjs` 和 `node scripts/homework-ui.test.cjs` 使用隔离测试数据验证移动布局、分周课表、作业状态转换、删除限制、正文安全渲染及课程筛选，不写入真实客户端的数据。

```powershell
cd .\web
.\node_modules\.bin\vue-tsc.cmd --noEmit -p .\tsconfig.app.json
.\node_modules\.bin\tsc.cmd --noEmit -p .\tsconfig.node.json
.\node_modules\.bin\vite.cmd build
```

界面变更还需验证桌面与约 390px 手机宽度、无横向溢出、控制台无错误，以及欢迎、绑定、课表导入、助手配置和删除本机凭据流程。
