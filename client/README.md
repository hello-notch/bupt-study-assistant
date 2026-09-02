# 邮学伴桌面客户端

客户端使用 Electron 加载 `web/dist`，不包含 NoneBot、NapCat 或任何校园凭据。它只是桌面窗口和安全的前端运行壳，在线账号、模型和校园数据由服务端处理。

## 一键运行

在项目根目录先双击 `run-server.cmd`，看到 `http://127.0.0.1:8787/` 后，再双击 `run-client.cmd`。服务端入口会加载现有完整校园与 AI 代理，不使用仅有占位接口的独立服务端原型。

首次运行前分别安装 `web/` 和 `client/` 依赖。也可以手工运行：

在项目根目录先构建前端：

```powershell
cd .\web
Copy-Item .\client-config.example .\.env
.\node_modules\.bin\vite.cmd build
cd ..\client
pnpm install
pnpm start
```

开发模式默认连接 `http://127.0.0.1:8787`。当前 Windows 内测包连接本机的非临时公网 IPv6 地址 `http://[2001:da8:215:8f02:7f5b:8f99:8107:90c3]:8787`，服务端入口会监听 IPv6。测试设备也必须支持 IPv6，且本机防火墙和上游网络需要允许 TCP 8787 入站。地址变化时，需要同时修改 `main.cjs` 的 `packagedAppUrl` 和 `web/.env` 的 `VITE_API_BASE_URL`，再重新打包。长期发布应换成带 AAAA 记录的稳定 HTTPS 域名。

## 打包 Windows 发布版

确认服务端地址后，在 `client/` 目录执行：

```powershell
pnpm run dist:win
```

产物位于 `client/dist/win-unpacked/`。分发时请把整个 `win-unpacked` 文件夹压缩后发送给测试用户；解压后双击 `邮学伴.exe` 即可，旁边的 DLL 和资源目录不能单独删除。当前包是未签名构建，Windows SmartScreen 可能显示未知发布者；正式公开发布前建议购买代码签名证书并通过 HTTPS 提供服务。

开发时可以先启动 Vite，再设置：

```powershell
$env:YOUXUEBAN_CLIENT_URL = "http://127.0.0.1:5173"
pnpm start
```

窗口启用沙箱和上下文隔离，禁止网页直接访问 Node.js 文件系统。外部校园链接会交给系统浏览器打开。
