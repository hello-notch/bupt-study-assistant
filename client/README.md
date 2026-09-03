# 邮学伴桌面客户端

Electron 客户端加载包内 `web/dist`，并通过 `preload.cjs` 暴露最小 IPC 接口。`local-runtime.cjs` 在主进程中直接访问校园系统与用户指定的 OpenAI 兼容模型服务；不需要邮学伴服务端。

Windows 包只携带 Playwright SDK，不内置 Chromium。北邮统一认证当前会拒绝 Electron 内核的登录请求，因此信息门户或电费会话失效时，客户端会按顺序寻找 Playwright 缓存和常见 Chrome/Edge 安装；都不存在时才自动下载 Chromium，完成后打开隔离浏览器并继续本机查询。统一认证密码、Cookie 和浏览器配置不会上传到邮学伴服务器；会话 Cookie 与账号配置一起由 `safeStorage` 加密保存。

校园账号、教务账号、密码、API URL、API Key 和默认模型使用 Electron `safeStorage` 加密保存到当前用户数据目录。渲染页面只能读取配置状态、账号名、URL 和模型名，无法读取密码或 API Key。删除校园配置时会同时清除独立校园会话分区。

```powershell
cd ..\web
pnpm run build
cd ..\client
pnpm install
pnpm start
```

构建 Windows 1.0.1 完整依赖版：

```powershell
pnpm run dist:win
```

产物为 `client/dist/YouXueBan-1.0.1-Windows-x64-full.zip`。压缩包包含完整的 Electron 运行库、网页资源和 Playwright SDK，不要单独复制 `邮学伴.exe`。当前没有商业代码签名证书，SmartScreen 可能显示未知发布者。
