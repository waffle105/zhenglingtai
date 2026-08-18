# 政令台 · 一键安装（Windows PowerShell）
# ============================================
# 包结构：单一 zhenglingtai/ 目录内含 SKILL.md + 可选 cli/ + 可选 prompts/
# 行为：best-effort 装三块，单步骤失败不阻断。
# 注释规范：每个动作前写"为什么"。
# 版本：v1.2.0（元 Skill 安装改为拷贝模式，不再用软链/junction）

[CmdletBinding()]
param([switch]$Uninstall)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BundleRoot = $ScriptDir
$CliDir = Join-Path $BundleRoot "cli"
$PromptDir = Join-Path $BundleRoot "prompts"
$BinSrc = Join-Path $BundleRoot "bin\zhengling.cmd"

$UserBin = Join-Path $env:USERPROFILE "bin"
$WbSkills = Join-Path $env:USERPROFILE ".workbuddy\skills"
$ZltProm = Join-Path $env:USERPROFILE ".zhenglingtai\prompts"

if ($Uninstall) {
    Write-Host "[uninstall] 移除 shim ..." -ForegroundColor Yellow
    Remove-Item -Force (Join-Path $UserBin "zhengling.cmd") -ErrorAction SilentlyContinue
    Write-Host "[uninstall] 移除 skill（拷贝或软链） ..." -ForegroundColor Yellow
    if (Test-Path (Join-Path $WbSkills "zhenglingtai")) {
        # 为什么带 -Recurse：v1.0.1 起为拷贝安装，目录非空，不带 -Recurse 删不掉
        Remove-Item -Recurse -Force (Join-Path $WbSkills "zhenglingtai") -ErrorAction SilentlyContinue
    }
    Write-Host "[uninstall] 卸 CLI 包 ..." -ForegroundColor Yellow
    if ((Get-Command pip -ErrorAction SilentlyContinue) -and (Test-Path $CliDir)) {
        & pip uninstall -y zhenglingtai-cli 2>$null | Out-Null
    }
    Write-Host "[uninstall] 删提示词副本 ..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force (Join-Path $env:USERPROFILE ".zhenglingtai") -ErrorAction SilentlyContinue
    Write-Host "[uninstall] 完成。" -ForegroundColor Green
    exit 0
}

Write-Host "==== 政令台一键安装 (Windows PowerShell) ====" -ForegroundColor Cyan
Write-Host "包根: $BundleRoot"; Write-Host ""

$failed = 0

# 1) 安装元 Skill（v1.0.1 拷贝模式）
#    为什么不用软链/junction：SymbolicLink 需管理员权限；junction 指向源目录，
#    源目录一删 skill 就挂。拷贝后 skill 独立存在，源目录可删。
Write-Host "[1/3] 安装 WorkBuddy 元 Skill（拷贝模式） ..." -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $BundleRoot "SKILL.md"))) {
    Write-Host "    跳过：未找到 SKILL.md"; $failed++
} else {
    if (-not (Test-Path $WbSkills)) { New-Item -ItemType Directory -Path $WbSkills -Force | Out-Null }
    $aDest = Join-Path $WbSkills "zhenglingtai"
    if (Test-Path $aDest) {
        if (Test-Path "$aDest.bak") { Remove-Item -Recurse -Force "$aDest.bak" }
        Move-Item -Force $aDest "$aDest.bak"
        Write-Host "    注意：原 zhenglingtai 已备份为 .bak" -ForegroundColor Yellow
    }
    try {
        Copy-Item -Recurse -Force $BundleRoot $aDest
        Write-Host "    ✔ 已拷贝到 $aDest（源目录可删）" -ForegroundColor Green
    } catch {
        Write-Host "    ✘ 拷贝失败：$_"; $failed++
    }
}
Write-Host ""

# 2) 装 CLI
Write-Host "[2/3] 装 CLI（zhenglingtai-cli） ..." -ForegroundColor Cyan
$py = $null
foreach ($cmd in @("python","python3","py")) {
    $p = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($p) { $py = $p.Source; break }
}
if (-not $py) {
    Write-Host "    跳过：python 不在 PATH"; $failed++
} elseif (-not (Test-Path $CliDir)) {
    Write-Host "    跳过：未找到 $CliDir"; $failed++
} else {
    # v1.0.1 修复：删掉了外层多余的 `if ($LASTEXITCODE -eq 0)` 包裹——
    # 它检查的是无关前序命令的退出码，会导致 pip install 被跳过。
    & $py -m pip install -e $CliDir --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    ✔ CLI 已装" -ForegroundColor Green
    } else {
        Write-Host "    ✘ pip install 失败"; $failed++
    }
}
Write-Host ""

# 3) 拷提示词
Write-Host "[3/3] 拷提示词 ..." -ForegroundColor Cyan
if (-not (Test-Path $PromptDir)) {
    Write-Host "    跳过：未找到 $PromptDir"; $failed++
} else {
    if (-not (Test-Path $ZltProm)) { New-Item -ItemType Directory -Path $ZltProm -Force | Out-Null }
    Copy-Item -Path (Join-Path $PromptDir "*") -Destination $ZltProm -Recurse -Force
    Write-Host "    ✔ 落到 $ZltProm" -ForegroundColor Green
}
Write-Host ""

# 4) 装 shim
#    v1.0.2 修复：不再裸拷贝——shim 用 "%SCRIPT_DIR%\.." 定位 BUNDLE_ROOT，
#    裸拷到 %USERPROFILE%\bin 后 BUNDLE_ROOT 会指向 %USERPROFILE%（detect.py 必找不到）。
#    改为拷贝时把 BUNDLE_ROOT 写死为当前包根的绝对路径。
Write-Host "[+] 装聚合入口 zhengling ..." -ForegroundColor Cyan
if (-not (Test-Path $UserBin)) { New-Item -ItemType Directory -Path $UserBin -Force | Out-Null }
$shimCmd = Join-Path $UserBin "zhengling.cmd"
try {
    # Encoding Default = 系统 ANSI（中文 Windows 即 GBK）——.cmd 里的中文 echo 才不会变问号
    (Get-Content $BinSrc -Raw) -replace 'set "BUNDLE_ROOT=.*"',
        ('set "BUNDLE_ROOT=' + $BundleRoot + '"  REM 安装时写死（install.ps1 注入）') |
        Set-Content -Path $shimCmd -Encoding Default
    Write-Host "    ✔ shim → $shimCmd（BUNDLE_ROOT 已写死为 $BundleRoot）" -ForegroundColor Green
    Write-Host "    'zhengling' 找不到时：[Environment]::SetEnvironmentVariable('Path',`$env:Path + ';$UserBin','User')" -ForegroundColor Yellow
} catch {
    Write-Host "    ✘ 装 shim 失败：$_"; $failed++
}
Write-Host ""

Write-Host "[+] 跑 zhengling doctor 自检 ..." -ForegroundColor Cyan
if ($py) { & $py (Join-Path $BundleRoot "doctor\detect.py") }
Write-Host ""

Write-Host "==== 安装总结 ====" -ForegroundColor Cyan
if ($failed -eq 0) { Write-Host "  全部完成。" -ForegroundColor Green }
else { Write-Host "  $failed 个步骤失败或跳过。" -ForegroundColor Yellow }
