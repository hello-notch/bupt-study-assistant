param(
    [string]$SdkRoot = $env:ANDROID_HOME,
    [string]$JavaHome = $env:JAVA_HOME,
    [string]$Gradle = "gradle",
    [switch]$Offline,
    [switch]$Release
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $SdkRoot) { throw 'Set ANDROID_HOME or pass -SdkRoot (Android SDK 35 and build-tools 35.0.0).' }
if (-not $JavaHome) { throw 'Set JAVA_HOME or pass -JavaHome (JDK 17 or 21).' }
$env:ANDROID_HOME = (Resolve-Path -LiteralPath $SdkRoot).Path
$env:JAVA_HOME = (Resolve-Path -LiteralPath $JavaHome).Path
if ($Release -and -not (Test-Path -LiteralPath (Join-Path $root 'secrets/android-release.properties'))) {
    throw 'Release signing is missing. See docs/android-release.md; never publish a Debug APK as a release.'
}
& pnpm --dir (Join-Path $root 'web') run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
& node (Join-Path $PSScriptRoot 'build-android-assets.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Android assets build failed.' }
$variant = if ($Release) { 'release' } else { 'debug' }
$task = if ($Release) { 'assembleRelease' } else { 'assembleDebug' }
$gradleArgs = @('-p', (Join-Path $root 'android'), '--no-daemon', '--console=plain', $task)
if ($Offline) { $gradleArgs += '--offline' }
& $Gradle @gradleArgs
if ($LASTEXITCODE -ne 0) { throw 'Android build failed.' }
$output = Join-Path $root "android/app/build/outputs/apk/$variant"
$metadata = Get-Content -LiteralPath (Join-Path $output 'output-metadata.json') -Raw | ConvertFrom-Json
if (@($metadata.elements).Count -ne 1) { throw 'Expected one universal APK.' }
$apk = $metadata.elements[0]
$suffix = if ($Release) { '' } else { '-test' }
$destination = Join-Path $output "YouXueBan-$($apk.versionName)-Android$suffix.apk"
Copy-Item -LiteralPath (Join-Path $output $apk.outputFile) -Destination $destination -Force
if ($Release) {
    & (Join-Path $env:ANDROID_HOME 'build-tools/35.0.0/apksigner.bat') verify --verbose --print-certs $destination
    if ($LASTEXITCODE -ne 0) { throw 'Release APK signature verification failed.' }
    $badging = & (Join-Path $env:ANDROID_HOME 'build-tools/35.0.0/aapt.exe') dump badging $destination
    if ($LASTEXITCODE -ne 0) { throw 'Release APK metadata verification failed.' }
    if (($badging -join "`n") -match 'application-debuggable') { throw 'Refusing to publish a debuggable APK.' }
    $checksum = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    [System.IO.File]::WriteAllText("$destination.sha256", "$checksum  $([System.IO.Path]::GetFileName($destination))`n", [System.Text.UTF8Encoding]::new($false))
}
Write-Output $destination
