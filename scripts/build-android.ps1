param(
    [string]$SdkRoot = $env:ANDROID_HOME,
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$Gradle = "gradle",
    [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $SdkRoot) { throw 'Set ANDROID_HOME or pass -SdkRoot (Android SDK 35 and build-tools 35.0.0).' }
if (-not $JavaHome) { throw 'Set JAVA_HOME or pass -JavaHome (JDK 17 or 21).' }
$env:ANDROID_HOME = (Resolve-Path -LiteralPath $SdkRoot).Path
$env:JAVA_HOME = (Resolve-Path -LiteralPath $JavaHome).Path
& pnpm --dir (Join-Path $root 'web') run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
& node (Join-Path $PSScriptRoot 'build-android-assets.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Android assets build failed.' }
$gradleArgs = @('-p', (Join-Path $root 'android'), '--no-daemon', '--console=plain', 'assembleDebug')
if ($Offline) { $gradleArgs += '--offline' }
& $Gradle @gradleArgs
if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
$destination = Join-Path $root 'android/app/build/outputs/apk/debug/YouXueBan-1.1.0-Android-test.apk'
Copy-Item -LiteralPath (Join-Path $root 'android/app/build/outputs/apk/debug/app-debug.apk') -Destination $destination -Force
Write-Output $destination
