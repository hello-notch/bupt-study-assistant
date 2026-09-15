$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Drawing.Common

$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot 'client\resources\app-icon.png'
New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null

$bitmap = [Drawing.Bitmap]::new(512, 512, [Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear([Drawing.Color]::Transparent)

    $path = [Drawing.Drawing2D.GraphicsPath]::new()
    try {
        $radius = 112.0
        $diameter = $radius * 2
        $path.AddArc(16, 16, $diameter, $diameter, 180, 90)
        $path.AddArc(496 - $diameter, 16, $diameter, $diameter, 270, 90)
        $path.AddArc(496 - $diameter, 496 - $diameter, $diameter, $diameter, 0, 90)
        $path.AddArc(16, 496 - $diameter, $diameter, $diameter, 90, 90)
        $path.CloseFigure()
        $background = [Drawing.SolidBrush]::new([Drawing.Color]::FromArgb(37, 99, 235))
        try {
            $graphics.FillPath($background, $path)
        }
        finally {
            $background.Dispose()
        }
    }
    finally {
        $path.Dispose()
    }

    $font = [Drawing.Font]::new('Microsoft YaHei UI', 280, [Drawing.FontStyle]::Bold, [Drawing.GraphicsUnit]::Pixel)
    $brush = [Drawing.SolidBrush]::new([Drawing.Color]::White)
    $format = [Drawing.StringFormat]::new()
    try {
        $format.Alignment = [Drawing.StringAlignment]::Center
        $format.LineAlignment = [Drawing.StringAlignment]::Center
        $graphics.DrawString('邮', $font, $brush, [Drawing.RectangleF]::new(0, -4, 512, 512), $format)
    }
    finally {
        $format.Dispose()
        $brush.Dispose()
        $font.Dispose()
    }

    $bitmap.Save($target, [Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

Write-Host 'Generated Windows app icon.'
