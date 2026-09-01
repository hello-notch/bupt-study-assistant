param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 5173
)

$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$webRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'web'))
$viteScript = [System.IO.Path]::GetFullPath((Join-Path $webRoot 'node_modules\vite\bin\vite.js'))

if (-not $webRoot.StartsWith(
        $projectRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw '前端目录不在项目目录内，已拒绝启动。'
}

if (-not (Test-Path -LiteralPath $viteScript -PathType Leaf)) {
    throw '前端依赖尚未安装。请进入 web 目录执行 pnpm install。'
}

$nodeCommand = Get-Command 'node.exe' -ErrorAction SilentlyContinue
if ($null -eq $nodeCommand) {
    throw '没有找到 Node.js。请先安装 Node.js 20 或更高版本。'
}

$nodeExecutable = $nodeCommand.Source
$nativeArgs = @(
    $viteScript
    '--host'
    '127.0.0.1'
    '--port'
    [string]$Port
    '--strictPort'
)

Write-Host ''
Write-Host '邮学伴前端正在启动……' -ForegroundColor Cyan
Write-Host "浏览器地址：http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host '按 Ctrl+C 停止服务。'
Write-Host ''

Push-Location -LiteralPath $webRoot
try {
    & $nodeExecutable @nativeArgs
    $exitCode = $LASTEXITCODE
    $normalStopCodes = @(0, 130, -1, -1073741510)
    if ($exitCode -notin $normalStopCodes) {
        throw "前端服务启动失败，退出码：$exitCode"
    }
}
finally {
    Pop-Location
}
