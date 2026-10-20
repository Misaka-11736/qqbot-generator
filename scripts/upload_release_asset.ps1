param(
    [Parameter(Mandatory = $true)][string]$Tag,
    [Parameter(Mandatory = $true)][string]$File,
    [string]$AssetName = "",
    [string]$Repo = "Misaka-11736/qqbot-generator"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $File)) { throw "文件不存在：$File" }
if (-not $AssetName) { $AssetName = Split-Path -Leaf $File }

function Get-GitExe {
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $found = Get-ChildItem "$env:LOCALAPPDATA\GitHubDesktop" -Recurse -Filter git.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*\git\cmd\git.exe" } |
        Select-Object -First 1
    if (-not $found) { throw "找不到 git.exe，请安装 Git 或 GitHub Desktop" }
    return $found.FullName
}

$git = Get-GitExe
$credential = "protocol=https`nhost=github.com`n`n" | & $git credential fill 2>&1
$token = (@($credential) | Where-Object { $_ -like "password=*" }) -replace "password=", ""
if (-not $token) { throw "没有从 git credential 拿到 GitHub Token" }

$headers = @{
    Authorization          = "Bearer $token"
    "User-Agent"           = "qqbot-release-uploader"
    Accept                 = "application/vnd.github+json"
}

$releaseFile = "$env:TEMP\gh-release.json"
$relStatus = curl.exe -sS --max-time 60 -o $releaseFile -w "%{http_code}" `
    -H "Authorization: Bearer $token" -H "User-Agent: qqbot-release-uploader" `
    "https://api.github.com/repos/$Repo/releases/tags/$Tag"
if ($relStatus -ne "200") { throw "找不到 Release $Tag（HTTP $relStatus）" }
$release = Get-Content $releaseFile -Raw -Encoding utf8 | ConvertFrom-Json
$uploadUrl = ($release.upload_url -replace "\{.*$", "") + "?name=" + [uri]::EscapeDataString($AssetName)
$existing = @($release.assets) | Where-Object { $_.name -eq $AssetName }
if ($existing) {
    Write-Host "资产已存在，先删除旧文件：$AssetName"
    curl.exe -sS --max-time 60 -X DELETE `
        -H "Authorization: Bearer $token" -H "User-Agent: qqbot-release-uploader" `
        "https://api.github.com/repos/$Repo/releases/assets/$($existing.id)" -o NUL
}

Write-Host "上传 $AssetName 到 $Tag ..."
$status = curl.exe -sS --max-time 1800 -X POST `
    -H "Authorization: Bearer $token" `
    -H "Content-Type: application/octet-stream" `
    -H "User-Agent: qqbot-release-uploader" `
    --data-binary "@$File" `
    -o "$env:TEMP\gh-asset-upload.json" `
    -w "%{http_code}" `
    $uploadUrl

if ($status -ne "201") {
    $body = Get-Content "$env:TEMP\gh-asset-upload.json" -Raw -Encoding utf8 -ErrorAction SilentlyContinue
    throw "上传失败（HTTP $status）：$body"
}

$asset = Get-Content "$env:TEMP\gh-asset-upload.json" -Raw -Encoding utf8 | ConvertFrom-Json
Write-Host "上传成功：$($asset.browser_download_url)（$([math]::Round($asset.size / 1MB, 1)) MB）"
