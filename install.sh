#!/usr/bin/env bash
# 政令台 · 一键安装（Linux / macOS / Git Bash）
# ============================================
# 包结构：单一目录 `zhenglingtai/` 内含
#   - SKILL.md （WorkBuddy 元 Skill 入口）
#   - cli/ （可选 Python CLI 附件）
#   - prompts/ （可选提示词附件）
#   - bin/ （smart shim）
#   - install.sh, install.ps1（本脚本 + Win 版本）
# 行为：best-effort 装三块；哪些环节有就用哪些。
# 注释规范：每个动作前写"为什么"+"如果 X 则 Y"。
# 硬约束：不修改 PATH 之外的 shell rc；不替用户填 API key。
# 版本：v1.2.0（元 Skill 安装改为拷贝模式，不再用目录软链）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
BUNDLE_ROOT="$SCRIPT_DIR"
CLI_DIR="${BUNDLE_ROOT}/cli"
PROMPT_DIR="${BUNDLE_ROOT}/prompts"
BIN_SRC="${BUNDLE_ROOT}/bin/zhengling"

USER_BIN="${HOME}/.local/bin"
WB_SKILLS="${HOME}/.workbuddy/skills"
ZLT_PROM="${HOME}/.zhenglingtai/prompts"

# 卸载
if [ "${1:-}" = "--uninstall" ]; then
    echo "[uninstall] 移除 shim ..."; rm -f "${USER_BIN}/zhengling"
    echo "[uninstall] 移除 skill（拷贝或软链） ..."; rm -rf "${WB_SKILLS}/zhenglingtai"
    echo "[uninstall] 卸 CLI 包（如 pip 已装） ..."
    if command -v pip >/dev/null 2>&1 && [ -d "${CLI_DIR}" ]; then
        pip uninstall -y zhenglingtai-cli 2>/dev/null || true
    fi
    echo "[uninstall] 删提示词副本 ..."; rm -rf "${HOME}/.zhenglingtai"
    echo "[uninstall] 完成。"
    exit 0
fi

echo "==== 政令台一键安装 ===="
echo "包根: ${BUNDLE_ROOT}"
echo ""

FAILED=0

# ---------- 1) 元 Skill 安装到 WB ----------
# v1.0.1 改为"拷贝优先"：
#   为什么不用软链：① Windows Git Bash 建目录软链需管理员/开发者模式，常失败；
#                  ② 软链指向解压目录，源目录一删 skill 就挂。
#   拷贝后 skill 独立存在，源目录可删。升级 = 重跑本脚本（旧版先备份为 .bak）。
echo "[1/3] 安装 WorkBuddy 元 Skill（拷贝模式） ..."
if [ ! -f "${BUNDLE_ROOT}/SKILL.md" ]; then
    echo "    跳过：未找到 ${BUNDLE_ROOT}/SKILL.md"; FAILED=$((FAILED+1))
else
    mkdir -p "${WB_SKILLS}"
    if [ -e "${WB_SKILLS}/zhenglingtai" ] || [ -L "${WB_SKILLS}/zhenglingtai" ]; then
        rm -rf "${WB_SKILLS}/zhenglingtai.bak"
        mv "${WB_SKILLS}/zhenglingtai" "${WB_SKILLS}/zhenglingtai.bak"
        echo "    注意：原 zhenglingtai 已被备份为 .bak"
    fi
    if cp -r "${BUNDLE_ROOT}" "${WB_SKILLS}/zhenglingtai"; then
        echo "    ✔ 已拷贝到 ${WB_SKILLS}/zhenglingtai（源目录可删）"
    else
        echo "    ✘ 拷贝失败"; FAILED=$((FAILED+1))
    fi
fi
echo ""

# ---------- 2) 装 CLI 附件 ----------
echo "[2/3] 装 CLI 附件（zhenglingtai-cli） ..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "    跳过：python3 不在 PATH"; FAILED=$((FAILED+1))
elif ! python3 -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null; then
    echo "    跳过：Python < 3.10"; FAILED=$((FAILED+1))
elif [ ! -d "${CLI_DIR}" ]; then
    echo "    跳过：未找到 ${CLI_DIR}"; FAILED=$((FAILED+1))
else
    if python3 -m pip install -e "${CLI_DIR}" --quiet 2>&1; then
        echo "    ✔ CLI 已装：${CLI_DIR}"
    else
        echo "    ✘ pip install 失败（不影响其它）"; FAILED=$((FAILED+1))
    fi
fi
echo ""

# ---------- 3) 拷提示词附件 ----------
echo "[3/3] 拷提示词附件（C 形态） ..."
if [ ! -d "${PROMPT_DIR}" ]; then
    echo "    跳过：未找到 ${PROMPT_DIR}"; FAILED=$((FAILED+1))
else
    mkdir -p "${ZLT_PROM}"
    if cp -r "${PROMPT_DIR}/." "${ZLT_PROM}/" 2>/dev/null; then
        echo "    ✔ 提示词落到 ${ZLT_PROM}"
    else
        echo "    ✘ 拷贝失败（不影响其它）"; FAILED=$((FAILED+1))
    fi
fi
echo ""

# ---------- 4) 装 shim ----------
# v1.0.2 修复：shim 不再裸拷贝——shim 用 "SCRIPT_DIR/.." 定位 BUNDLE_ROOT，
# 裸拷到 USER_BIN 后 BUNDLE_ROOT 会指向 ~/.local（detect.py 必找不到）。
# 改为拷贝时把 BUNDLE_ROOT 写死为当前包根的绝对路径。
echo "[+] 装聚合入口 zhengling ..."
mkdir -p "${USER_BIN}"
if sed "s|^BUNDLE_ROOT=.*|BUNDLE_ROOT=\"${BUNDLE_ROOT}\"  # 安装时写死（install.sh 注入）|" \
        "${BIN_SRC}" > "${USER_BIN}/zhengling" 2>/dev/null \
    && chmod +x "${USER_BIN}/zhengling"; then
    echo "    ✔ shim → ${USER_BIN}/zhengling（BUNDLE_ROOT 已写死为 ${BUNDLE_ROOT}）"
    echo "    如 'zhengling' 找不到，请把 ${USER_BIN} 加到 PATH："
    echo "        echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
else
    echo "    ✘ 装 shim 失败"; FAILED=$((FAILED+1))
fi
echo ""

# ---------- 5) doctor 自检 ----------
echo "[+] 跑 zhengling doctor 自检 ..."
if command -v python3 >/dev/null 2>&1; then
    if command -v zhengling >/dev/null 2>&1; then
        zhengling doctor || true
    else
        python3 "${BUNDLE_ROOT}/doctor/detect.py" || true
    fi
fi
echo ""

# ---------- 总结 ----------
echo "==== 安装总结 ===="
if [ "${FAILED}" -eq 0 ]; then
    echo "  全部完成。"
else
    echo "  ${FAILED} 个步骤失败或跳过——看上方输出。"
fi
echo ""
echo "用法：zhengling run \"你的指令\""
echo "      zhengling doctor"
