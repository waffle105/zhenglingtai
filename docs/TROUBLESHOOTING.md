# 排错指南

> **最后更新：** 2026-07-22 · **适用版本：** v1.2.0

---

## 常见错误

### `zhengling` 命令找不到

**原因：** `~/.local/bin`（Win: `%USERPROFILE%\bin`）不在 PATH。

**解法：**
```bash
# Linux/macOS
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc

# Windows PowerShell
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$env:USERPROFILE\bin", "User")
```

---

### `doctor` 显示 NONE

**原因：** 三块都没装。

**解法：** 跑 `./install.sh`（Win: `install.ps1`）。

---

### `doctor` 显示"WorkBuddy 不可用"

**原因：** 拷贝失败或 SKILL.md frontmatter 异常。

**解法：**
1. 检查 `~/.workbuddy/skills/zhenglingtai/SKILL.md` 是否存在
2. 检查 frontmatter 无 `#` 注释行（YAML 块内不允许行注释）
3. 手动补拷：`cp -r zhenglingtai/ ~/.workbuddy/skills/`（v1.0.1 起为拷贝模式，不再用软链/junction）

---

### `run` 进了通用模式

**原因：** skill 没声明 `capability` 块或 `intent_tags` 不匹配。

**解法：**
```bash
zlt migrate scan          # 看哪些 skill 缺 capability
zlt migrate batch         # 批量补
```

---

### 子能力执行返回 noop

**原因：** skill 在登记册里，但 `zhenglingtai-capabilities.yaml` 没配真实执行方式。

**解法：**
```bash
zlt capabilities init     # 生成模板
# 编辑 yaml，把 kind: noop 改成 local/http/cli
```

---

### LLM 调用超时 / 返回非 JSON

**原因：** API key 无效、网络不通、模型不支持 JSON mode。

**解法：**
1. 检查 `zlt.config.yaml` 的 `api_key` / `base_url`
2. 用 `--route-mode=deterministic` 绕过 LLM 路由（L1/L4 仍需 LLM）
3. 换模型（推荐 DeepSeek-chat 或 OpenAI gpt-4o-mini）

---

### 自指套娃（已修复）

**症状：** 用户说"政令模式做 X"→ 无限递归。

**状态：** v0.2.1 已修复——`META_SELF_IDS = {"zhenglingtai"}` 排除政令台自身。

---

### run.log 在哪

**路径：** `~/.zhenglingtai/runs/YYYYMMDD-HHMMSS.log`

**格式：** JSON Lines（每行一个 JSON 对象），可用 `jq` 解析：

```bash
# 查看最近一次运行的错误
cat ~/.zhenglingtai/runs/*.log | jq 'select(.level == "ERROR")'

# 查看所有 run 的耗时
cat ~/.zhenglingtai/runs/*.log | jq 'select(.msg == "run_complete")'
```

```bash
zlt health --verbose     # 查看最近 10 条政令摘要
```
