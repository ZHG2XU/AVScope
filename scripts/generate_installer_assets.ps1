$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logoPath = Join-Path $root "qt\resources\avscope.png"
$outputDir = Join-Path $root "packaging\assets"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

function New-RoundedPath {
    param(
        [System.Drawing.RectangleF]$Rectangle,
        [float]$Radius
    )

    $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $diameter = $Radius * 2
    $arc = [System.Drawing.RectangleF]::new($Rectangle.X, $Rectangle.Y, $diameter, $diameter)
    $path.AddArc($arc, 180, 90)
    $arc.X = $Rectangle.Right - $diameter
    $path.AddArc($arc, 270, 90)
    $arc.Y = $Rectangle.Bottom - $diameter
    $path.AddArc($arc, 0, 90)
    $arc.X = $Rectangle.X
    $path.AddArc($arc, 90, 90)
    $path.CloseFigure()
    return $path
}

function New-InstallerWelcomeBitmap {
    param(
        [string]$Destination,
        [System.Drawing.Image]$Logo
    )

    $bitmap = [System.Drawing.Bitmap]::new(164, 314, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

        $bounds = [System.Drawing.Rectangle]::new(0, 0, 164, 314)
        $background = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            $bounds,
            [System.Drawing.Color]::FromArgb(5, 13, 25),
            [System.Drawing.Color]::FromArgb(12, 39, 62),
            90.0
        )
        $graphics.FillRectangle($background, $bounds)
        $background.Dispose()

        $glow = [System.Drawing.Drawing2D.GraphicsPath]::new()
        $glow.AddEllipse(-80, 180, 280, 220)
        $glowBrush = [System.Drawing.Drawing2D.PathGradientBrush]::new($glow)
        $glowBrush.CenterColor = [System.Drawing.Color]::FromArgb(105, 34, 181, 206)
        $glowBrush.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 5, 13, 25))
        $graphics.FillPath($glowBrush, $glow)
        $glowBrush.Dispose()
        $glow.Dispose()

        $cardPath = New-RoundedPath ([System.Drawing.RectangleF]::new(20, 28, 124, 124)) 28
        $cardBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(28, 255, 255, 255))
        $graphics.FillPath($cardBrush, $cardPath)
        $cardPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(50, 80, 218, 210), 1)
        $graphics.DrawPath($cardPen, $cardPath)
        $graphics.DrawImage($Logo, 31, 39, 102, 102)
        $cardPen.Dispose()
        $cardBrush.Dispose()
        $cardPath.Dispose()

        $trackPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(100, 72, 223, 204), 2)
        $trackPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $trackPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $points = @(
            [System.Drawing.PointF]::new(16, 204),
            [System.Drawing.PointF]::new(35, 204),
            [System.Drawing.PointF]::new(44, 187),
            [System.Drawing.PointF]::new(57, 227),
            [System.Drawing.PointF]::new(70, 174),
            [System.Drawing.PointF]::new(82, 214),
            [System.Drawing.PointF]::new(97, 191),
            [System.Drawing.PointF]::new(112, 204),
            [System.Drawing.PointF]::new(148, 204)
        )
        $graphics.DrawLines($trackPen, $points)
        $trackPen.Dispose()

        $font = [System.Drawing.Font]::new("Segoe UI Semibold", 13, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $smallFont = [System.Drawing.Font]::new("Segoe UI", 8, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
        $white = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(244, 248, 252))
        $muted = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(119, 207, 219))
        $graphics.DrawString("AVSCOPE", $font, $white, 18, 255)
        $graphics.DrawString("MEDIA INTELLIGENCE", $smallFont, $muted, 18, 278)
        $muted.Dispose()
        $white.Dispose()
        $smallFont.Dispose()
        $font.Dispose()

        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Bmp)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

function New-InstallerHeaderBitmap {
    param(
        [string]$Destination,
        [System.Drawing.Image]$Logo
    )

    $bitmap = [System.Drawing.Bitmap]::new(150, 57, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.Clear([System.Drawing.Color]::White)

        $accentBrush = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            [System.Drawing.Rectangle]::new(0, 0, 150, 57),
            [System.Drawing.Color]::FromArgb(235, 250, 252),
            [System.Drawing.Color]::White,
            0.0
        )
        $graphics.FillRectangle($accentBrush, 0, 0, 150, 57)
        $accentBrush.Dispose()

        $linePen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(62, 203, 199), 2)
        $graphics.DrawBezier($linePen, 0, 43, 34, 14, 54, 55, 93, 23)
        $graphics.DrawBezier($linePen, 18, 54, 49, 26, 65, 55, 103, 35)
        $linePen.Dispose()

        $graphics.DrawImage($Logo, 101, 7, 43, 43)
        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Bmp)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

$logo = [System.Drawing.Image]::FromFile($logoPath)
try {
    New-InstallerWelcomeBitmap -Destination (Join-Path $outputDir "installer-welcome.bmp") -Logo $logo
    New-InstallerHeaderBitmap -Destination (Join-Path $outputDir "installer-header.bmp") -Logo $logo
}
finally {
    $logo.Dispose()
}

Write-Output "Installer assets generated in $outputDir"
