@echo off
REM zhengling · 政令台聚合入口 (Windows .cmd 包装)
REM 调用 doctor/detect.py 与 zhenglingtai_cli（pip 包名）
REM 注释规范沿用 ../SKILL.md

setlocal

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "BUNDLE_ROOT=%SCRIPT_DIR%\.."

set "PY="
for %%P in (python python3 py) do (
    for /f "tokens=*" %%X in ('where %%P 2^>nul') do (
        set "PY=%%X"
        goto :got_py
    )
)
:got_py
if "%PY%"=="" (
    echo [zhengling] python 不在 PATH。请先装 Python 3.10+。
    exit /b 1
)

set "SUBCMD=%~1"
if "%SUBCMD%"=="" set "SUBCMD=doctor"
shift /1
REM v1.0.2：ARGS 先显式置空，避免依赖"未定义变量展开为空"的隐式行为
set "ARGS="
:parse_args
if "%~1"=="" goto :dispatch
set "ARGS=%ARGS% "%~1""
shift /1
goto :parse_args

:dispatch
if /i "%SUBCMD%"=="doctor" goto :form_doctor
if /i "%SUBCMD%"=="health" goto :form_doctor
if /i "%SUBCMD%"=="uninstall" goto :form_uninstall

REM 探测
set "ACTIVE="
for /f "tokens=*" %%A in ('"%PY%" "%BUNDLE_ROOT%\doctor\detect.py" --json 2^>nul ^| "%PY%" -c "import sys,json; print(json.load(sys.stdin).get('active','NONE'))" 2^>nul') do (
    set "ACTIVE=%%A"
)

if "%ACTIVE%"=="WB" goto :form_wb
if "%ACTIVE%"=="CLI" goto :form_cli
if "%ACTIVE%"=="PROMPT" goto :form_prompt
echo [zhengling] 三块都没装，请跑 install.ps1。
exit /b 2

:form_doctor
"%PY%" "%BUNDLE_ROOT%\doctor\detect.py" %ARGS%
exit /b %errorlevel%

:form_uninstall
powershell -ExecutionPolicy Bypass -File "%BUNDLE_ROOT%\install.ps1" -Uninstall
exit /b %errorlevel%

:form_wb
echo [zhengling] 已在 WorkBuddy 内（SKILL.md 已加载）。
echo     请在 WorkBuddy 对话框里输入：zhengling run "%ARGS%"
exit /b 0

:form_cli
"%PY%" -m zhenglingtai_cli %SUBCMD% %ARGS%
exit /b %errorlevel%

:form_prompt
echo [zhengling] 终端 zhengling CLI 未装。
echo     请把下面这段粘进任意 LLM 对话框的 system 指令：
echo.
if exist "%USERPROFILE%\.zhenglingtai\prompts\fans\deepseek-system-prompt.md" (
    type "%USERPROFILE%\.zhenglingtai\prompts\fans\deepseek-system-prompt.md"
) else (
    echo ^(提示词未安装——请跑 install.ps1^)
)
exit /b 0
