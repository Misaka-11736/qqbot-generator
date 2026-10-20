# 编译安装包：需要 NSIS 3（makensis）
# 用法：powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1 -Nsis "C:\Program Files (x86)\NSIS"

param(
    [string]$Nsis = "",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Python) {
    $candidates = @("$Root\.build\venv\Scripts\python.exe", "$Root\.venv\Scripts\python.exe")
    foreach ($c in $candidates) { if (Test-Path $c) { $Python = $c; break } }
}
if (-not $Python) { $Python = "python" }

$makensis = if ($Nsis) { Join-Path $Nsis "makensis.exe" } else { "makensis.exe" }
if (-not (Test-Path $makensis) -and -not (Get-Command $makensis -ErrorAction SilentlyContinue)) {
    throw "找不到 makensis.exe。安装 NSIS 3，或用 -Nsis 指定目录。"
}

Write-Host "==> 生成图标与资源" -ForegroundColor Cyan
& $Python scripts\make_assets.py
& $Python scripts\make_icon.py

Write-Host "==> PyInstaller 打包" -ForegroundColor Cyan
& $Python -m PyInstaller --noconfirm --clean qqbot-generator.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

$dist = Join-Path $Root "dist"
$built = Join-Path $dist "QQBotGenerator.exe"
$final = Join-Path $dist "QQ Bot生成器.exe"
if (Test-Path $built) {
    if (Test-Path $final) { Remove-Item -Force $final }
    Move-Item $built $final
}

Write-Host "==> NSIS 编译安装包" -ForegroundColor Cyan
& $makensis /INPUTCHARSET UTF8 (Join-Path $Root "installer\qqbot-generator.nsi")
if ($LASTEXITCODE -ne 0) { throw "makensis 失败" }

Write-Host "`n完成：" -ForegroundColor Green
Get-ChildItem $dist | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
