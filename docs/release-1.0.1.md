# 邮学伴 1.0.1 发布说明

## 产物

- Windows 完整目录压缩包（含 `邮学伴.exe` 及 Electron 运行依赖）：`client/dist/YouXueBan-1.0.1-Windows-x64-full.zip`

## 体积与打包取舍

Windows 包只保留 Electron 应用、前端构建产物和 Playwright SDK，不随包携带 Chromium、headless shell、ffmpeg 或构建缓存。首次需要校园统一认证时，运行时按以下顺序寻找 Chromium：Playwright 默认缓存、用户常见的 Chrome/Edge 安装目录；都不存在时才执行 `playwright install chromium --no-shell` 下载到用户 Playwright 缓存目录。

项目中的 `node_modules`、`web/node_modules`、`web/dist`、测试数据库、日志、凭据和临时探针均不属于源码提交。Electron 的 `locales`、`.pak`、DLL 等属于构建后的运行时依赖，不能从发布压缩包中单独删除。

## 文案与离线数据

Web 页面文案统一在 `web/src/texts.ts` 读取，包括鉴权、安全和参数校验错误信息。信息门户和第二课堂成功读取后会写入设备本地缓存；刷新失败时继续展示最近一次真实数据，并把来源标为“缓存”，同时提供重新登录入口。通知摘要由已配置的 DeepSeek 模型在设备内生成，未配置模型或登录失效时会给出明确提示并保留原文链接。
