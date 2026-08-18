# API 参考

> **最后更新：** 2026-07-22 · **适用版本：** v1.2.0

> **v1.2.0 新增 §子能力 4 层 fallback**（见 EXTENDING §1.5）：原生能力 →
> 用户声明 cap → LLM 直接产文本 → noop 升级给人。`zlt health` 默认会报告
> 当前 venv 已就绪多少个原生能力；`--verbose` 看逐条状态。

---

## 政令台 CLI 子命令参考

> **两个入口（v1.0.3 起）：**
> - **`zlt`** = pip 包直连入口（`pip install` 后即有）——本文档大部分子命令用它
> - **`zhengling`** = 聚合 shim（`bin/`，由 `install.sh` / `install.ps1` 安装）——
>   shim 独有的 `doctor` / `uninstall` 用它；其余子命令 shim 会探测环境后转发给 CLI
>
> v1.0.3 前 pip 入口也叫 `zhengling`，与 shim 冲突（pip 的 bin 常排在 PATH 前，
> 导致 `zhengling doctor` 打到了没有 doctor 的 pip 入口）——已改名 `zlt`。

### zlt health

自检环境，不调 LLM。

```
zlt health [--verbose]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `--verbose` | flag | false | 显示最近 10 条政令日志 |

**退出码：** 0

---

### zlt registry

列出本机登记册里所有可路由 skill。

```
zlt registry [--skills-dir DIR]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `--skills-dir` | path | `~/.workbuddy/skills` | skill 目录 |

**退出码：** 0

---

### zlt translate

只跑通译层（L1），打印任务书 JSON。

```
zlt translate "你的指令" [--config FILE]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `prompt` | str | 必填 | 用户原始指令 |
| `--config` | path | `zlt.config.yaml` | LLM config |

**退出码：** 0

---

### zlt run

跑完整四层：通译 → 流转 → 执行 → 验收。

```
zlt run "你的指令" [options]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `prompt` | str | 必填 | 用户原始指令 |
| `--config` | path | `zlt.config.yaml` | LLM config（`--offline` 时不需要） |
| `--skills-dir` | path | `~/.workbuddy/skills` | skill 目录 |
| `--capabilities` | path | `zhenglingtai-capabilities.yaml` | 子能力配置 |
| `--work-dir` | path | `.` | 工作目录 |
| `--route-mode` | enum | `auto` | `auto` / `deterministic` / `llm` |
| `--offline` | flag | false | 纯确定性模式（v1.1.0），见下 |

**--offline（v1.1.0）：** 纯确定性端到端——L1 规则构造最小任务书、
L2 强制确定性路由、L4 机器契约验收（SKILL.md §5：文件存在/非空/页数/字数/py 语法），
**全程不调 LLM、无需 LLM config**。适合 CI 冒烟、无 key 环境、验证 capabilities 的物理产出。
注意：offline 下任务书未经 LLM 通译（`intent_tags` 为空 → 通用模式），
accept 的语义条目全部进 `subjective` 等用户确认。

**退出码：**

| 码 | 含义 |
|---|---|
| 0 | 达标 |
| 2 | 流程错误（配置/网络/LLM 解析失败） |
| 3 | 封驳未达标（含 offline 机器契约未过 / 打满 3 轮 ESCALATE） |
| 4 | 子能力执行失败 |

**D12 可观测性：** 每次运行自动生成 `~/.zhenglingtai/runs/YYYYMMDD-HHMMSS.log`（JSON Lines，可被 `jq` 解析）。

---

### zlt verify

单独跑验收层（L4），传入已有的任务书 / 工序单 JSON + 实际产物。

```
zlt verify --task task.json --proc proc.json [--produced '{"path":"...","type":"md"}'] [--config FILE] [--offline]
```

| 参数 | 说明 |
|---|---|
| `--produced` | 产物 dict 的 JSON 字符串，可多次；传裸路径也可（按后缀推类型） |
| `--offline` | 验收走机器契约（v1.1.0，不调 LLM、无需 config） |

**退出码：** 0（达标）/ 3（未达标）

---

### zlt capabilities init

D7：扫描登记册 → 生成 capabilities yaml 模板。

```
zlt capabilities init [--skills-dir DIR] [--output FILE]
```

---

### zlt migrate scan

D8：扫描所有缺 capability 块的 skill。

```
zlt migrate scan [--skills-dir DIR]
```

---

### zlt migrate suggest

D8：LLM 读 SKILL.md 正文 → 建议 intent_tags。

```
zlt migrate suggest <skill_id> [--config FILE] [--skills-dir DIR]
```

---

### zlt migrate batch

D8：批量迁移。dry-run 只生成 `migration_plan.md`，不写文件。

```
zlt migrate batch [--config FILE] [--skills-dir DIR] [--dry-run]
```

---

### zhengling doctor

环境探测器——决定走哪条路径（WB / CLI / 提示词）。

> **归属说明：** `doctor` 是 **shim 层**（`bin/zhengling`）的子命令，由 `doctor/detect.py` 实现；
> Python 包本身**没有**注册 doctor 子命令——`python -m zhenglingtai_cli doctor` 会报未知子命令。
> 已安装的用户走 shim（`zhengling doctor`）即可；未装 shim 时可跑 `python doctor/detect.py`。

```
zhengling doctor [--json] [--explain]
```

| 参数 | 说明 |
|---|---|
| `--json` | JSON 输出（给 shim 用） |
| `--explain` | 解释为何选这个形态 |
