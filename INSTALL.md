# 政令台 · 安装详解

> **唯一安装动作：** 把整个 `zhenglingtai/` 目录拷到 `~/.workbuddy/skills/`。
> **可选附件：** `cli/`、`prompts/` 可独立装或都装。
> **推荐：** 直接跑 `./install.sh`（Windows: `install.ps1`）一键装。

---

## 0. 系统要求

| 形态 | 要求 |
|---|---|
| **元 Skill（核心）** | WorkBuddy ≥ 0.x |
| **CLI 附件（可选）** | Python ≥ 3.10 + pip |
| **提示词附件（可选）** | 任何能贴 system prompt 的 LLM 对话框 |

---

## 1. 一键安装（推荐）

### Linux / macOS / Git Bash

```bash
cd zhenglingtai/
./install.sh
```

### Windows PowerShell

```powershell
cd zhenglingtai\
powershell -ExecutionPolicy Bypass -File install.ps1
```

### 装哪些、按什么顺序

install.sh/.ps1 是 best-effort：能装的都尝试，单步失败不阻断。

1. **元 Skill 拷贝到 `~/.workbuddy/skills/zhenglingtai`**（v1.0.1 起为拷贝模式，不用软链——拷完源目录可删）
2. **CLI 附件** `pip install -e cli/`（如果装了 Python）
3. **提示词附件** 拷到 `~/.zhenglingtai/prompts/`
4. **smart shim** `zhengling` 放到 `~/.local/bin/`（Win: `%USERPROFILE%\bin\`），拷贝时 BUNDLE_ROOT 写死为包根绝对路径
5. **跑 doctor 自检** 看装得怎么样

---

## 2. 手动安装（不进 PATH / 只想用一种形态）

### 只用 WorkBuddy 元 Skill

```bash
cp -r zhenglingtai/ ~/.workbuddy/skills/
```

### 只用 CLI 附件

```bash
cd cli/
pip install -e .
zlt --version        # v1.0.3 起 pip 入口为 zlt（旧名 zhengling 归 shim 专用）
```

### 只用提示词附件

```bash
cp -r prompts/ ~/.zhenglingtai/prompts/
```

然后照 `prompts/zhengling-jiaocheng.md` 跑。

---

## 3. 装完怎么验

```bash
zhengling doctor                # 一行看出当前生效形态
```

期望输出类似：
```
===== zhengling doctor =====
WorkBuddy 元 Skill：可用 ✔
CLI（zhenglingtai-cli）：可用 ✔
提示词副本：可用 ✔

本机可路由 skill：3（声明了 capability 块的）
→ 当前生效：CLI 形态
```

---

## 4. PATH 设置（如果你用 CLI / shim）

### Linux / macOS（bash）

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Windows PowerShell

```powershell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:USERPROFILE\bin", "User")
```

---

## 5. 卸载

```bash
zhengling uninstall          # 反向安装
```

这会做：
- 移除 smart shim
- 删除 `~/.workbuddy/skills/zhenglingtai`（v1.0.1 起为拷贝安装，目录整体移除）
- `pip uninstall zhenglingtai-cli`
- 删 `~/.zhenglingtai/prompts/`

**幂等**——已经不在的东西不会再失败。

---

## 6. 升级（如 v1.0.1 → v1.0.2）

```bash
# 拿到新版 zip 解压后，直接重跑安装脚本：
cd zhenglingtai/
./install.sh             # 旧版会被自动备份为 zhenglingtai.bak 再覆盖
```

---

## 7. 排错

| 症状 | 可能原因 | 解法 |
|---|---|---|
| `zhengling` 命令找不到 | PATH 没设 | §4 PATH 设置 |
| `doctor` 显示"WorkBuddy 不可用" | 拷贝失败 | 手动 `cp -r zhenglingtai/ ~/.workbuddy/skills/` |
| `doctor` 显示"CLI 不可用" | pip install 失败 | 手动 `pip install -e cli/` |
| `doctor` 显示"提示词不可用" | 拷脚本失败 | 手动 `cp -r prompts/ ~/.zhenglingtai/` |
| 三块都不行 | 没跑 install | 跑一遍（§1）|

---

## 8. 安全提示（HARD）

- `install.sh` / `install.ps1` 不会替你填 API key——CLI 附件用时再设 `ZLT_API_KEY`
- `install.sh` 不修改 PATH 以外的 shell rc 文件
- 分享给别人时，确保删掉 `cli/zlt.config.yaml`（如已用示例配置改过）
