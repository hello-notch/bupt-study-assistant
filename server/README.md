# 邮学伴服务端

这是一个不依赖 NoneBot 的独立服务端原型，负责邮学伴账号登录、模型请求转发和服务端校园缓存接口。它尚未接入现有完整的校园适配器，因此不是当前桌面客户端的本机启动入口。

## 桌面客户端的本机服务端

请在项目根目录双击 `run-server.cmd`，或运行：

```powershell
.\run-server.cmd
```

该入口会加载 `web/dev-api.ts`，提供信息门户、第二课堂、教务、电费、AI 与认证的完整代理接口。

## 独立部署原型

如需继续开发独立部署原型，可在项目根目录执行：

```powershell
node .\server\index.mjs
```

默认监听 `127.0.0.1:8787`。生产环境至少设置：

```powershell
$env:YOUXUEBAN_SERVER_HOST = "0.0.0.0"
$env:YOUXUEBAN_SERVER_PORT = "8787"
$env:YOUXUEBAN_ALLOWED_ORIGIN = "https://client.example.com"
$env:YOUXUEBAN_MODEL_URL = "https://api.example.com/v1"
$env:YOUXUEBAN_MODEL_API_KEY = "在受保护的环境变量或密钥系统中设置"
$env:YOUXUEBAN_MODEL_NAME = "模型名称"
node .\server\index.mjs
```

用户账号写入 `server/data/users.json`，该目录已被 Git 忽略。服务端只保存邮学伴账号的密码哈希，不保存明文密码。

## 校园缓存

将真实的只读校园条目写入 `server/data/campus.json`，格式可以是条目数组，或 `{ "items": [...] }`。条目应包含 `id`、`url`、`kind`、`title`、`summary`、`source` 和 `publishedAt`。服务端会把它们以 `/api/campus` 提供给客户端。

当前服务端不会把开发者的个人教务账号冒充成所有用户，也不会提供报名、签到、退选或绕过验证的接口。需要接入真实数据源时，应在独立适配器中实现授权、缓存、限流和失效状态。
