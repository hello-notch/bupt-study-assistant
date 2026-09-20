# Android 发布构建

Android 版本由 `android/app/build.gradle` 的 `versionName` 和 `versionCode` 管理。
桌面端版本仍由 `client/package.json` 管理，不随 Android 发布自动提升。

## 签名

正式包使用独立发布密钥，不使用 Android Debug 密钥。将密钥和配置保存在已忽略的
`secrets/` 目录，并在设备外安全备份；丢失密钥将无法给已安装的正式版签发兼容更新。
不得提交、上传或在日志中输出密钥与密码。

本机 `secrets/android-release.properties` 格式如下，路径相对于 `android/`：

```properties
storeFile=../secrets/youxueban-release.keystore
storePassword=<local secret>
keyAlias=youxueban-release
keyPassword=<local secret>
```

## 构建与验证

```powershell
pnpm --dir client test
pwsh -NoProfile -File ./scripts/build-android.ps1 -SdkRoot "<Android-SDK>" -JavaHome "<JDK>" -Gradle "<gradle.bat>" -Release
node scripts/mobile-ui.test.cjs
node scripts/homework-ui.test.cjs
```

构建会执行两项 TypeScript 检查、Vite 构建、Android 资源生成和 `assembleRelease`，
从 Gradle 输出元数据读取版本与产物，并用 `apksigner verify` 验证签名。
未提供 `-Release` 时仍构建 Debug 测试包。已缓存全部依赖时可添加 `-Offline`。

发布前核对 APK 的包名、版本、最低 Android 版本、签名与非 Debug 标志，并生成
SHA-256 校验文件。最终 APK 的真机验收应另行记录，旧 Debug 包的验收不能替代。

## 安装与升级

- 支持 Android 11（API 30）及以上版本。
- 正式 APK 关闭 WebView 调试，后续正式版应始终使用同一密钥并提高 `versionCode`。
- 旧 Debug 测试版与正式版签名不同，Android 不允许直接覆盖安装。请先保留重要数据，
  再手动卸载测试版并安装正式版；卸载会删除任务、课表、对话和本机配置。
- 本次发布流程不自动卸载应用、清除设备数据或发布 Windows 包。
