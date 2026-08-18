# 内部机制

> **最后更新：** 2026-07-22 · **适用版本：** v1.2.0

---

## 1. 四层纪律时序图

```
用户指令
   │
   ▼
┌──────────────────────────────────┐
│ ① 通译司（L1）                     │
│    输入：口语指令                    │
│    LLM 调用：1 次                   │
│    产物：TaskBook JSON              │
│    门禁：未确认 → 不进 L2            │
│    日志：layer1_done                │
└──────────┬───────────────────────┘
           │ (确认后)
           ▼
┌──────────────────────────────────┐
│ ② 流转司（L2）                     │
│    输入：TaskBook + 登记册           │
│    确定性阶段：score() 排序          │
│    LLM 阶段（auto 模式）：编排       │
│    产物：Procedure JSON             │
│    门禁：未产出 → 不执行             │
│    日志：layer2_done                │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ ③ 执行工坊（L3）                    │
│    输入：Procedure                  │
│    调用：executor.execute()         │
│    每步：noop/local/http/cli        │
│    产物：阶段简报 + 实际产物          │
│    遇阻：【BLOCK】上报               │
│    日志：layer3_step_done            │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│ ④ 督查验收司（L4）                  │
│    输入：TaskBook + Procedure + 产物  │
│    LLM 调用：1 次                   │
│    产物：Acceptance JSON            │
│    封驳：未达标 → 打回 L3            │
│    HARD：deviations 不可空           │
│    日志：layer4_done                 │
└──────────┬───────────────────────┘
           │
           ▼
       交付 / 打回
```

---

## 2. 登记册自发现机制

### 扫描流程

```
~/.workbuddy/skills/
├── skill-a/
│   └── SKILL.md          ← 扫描 frontmatter
│       ---
│       metadata:
│         capability:     ← 有这个块 → 入册
│           id: skill-a
│           intent_tags: [write_copy]
│       ---
├── skill-b/
│   └── SKILL.md          ← 无 capability 块 → 跳过
│       ---
│       name: Skill B
│       ---
└── zhenglingtai/         ← 自身 → META_SELF_IDS 排除
```

### 路由决策

```
TaskBook.intent_tags = ["write_copy", "make_ppt"]
         │
         ▼
    filter_by_intent()     ← 粗筛：intent_tags 有交集
         │                  ← META_SELF_IDS 排除
         ▼
    score()                ← 精排：|交集|/|query| + output_types 加权
         │
         ▼
    冲突消解（§3.7）
    ├─ output_types 不重叠 → 协同串行
    └─ output_types 重叠   → 最具体优先
         │
         ▼
    meta 检查
    ├─ is_meta=true → 整条委托
    └─ is_meta=false → 正常工序
         │
         ▼
    Procedure JSON
```

---

## 3. --route-mode 三种模式对比

| | auto（默认） | deterministic | llm |
|---|---|---|---|
| 选 skill | 确定性算法 | 确定性算法 | LLM |
| 编工序 | LLM（仅多 skill 时） | 确定性模板 | LLM |
| LLM 调用次数 | 0-1 | 0 | 1 |
| 可复现 | ✅（选 skill 稳定） | ✅（100%） | ❌ |
| 适合 | 日常 | CI / 离线 / 测试 | 对照 |

> **--offline（v1.1.0）**：比 deterministic 更进一步——L1 规则构造任务书、L4 机器契约验收，
> 全程零 LLM 调用（无需 config）。适合 CI 冒烟、无 key 环境、验证 capabilities 配置的物理产出。

---

## 3.5 路由加权系数的设计依据（v1.1.0 补）

**当前生效公式**：`score() = |命中标签| / |query| + 0.01 × priority`

评审曾指出系数"是拍脑袋定的"。公开设计依据、现状勘误与调优方法：

| 系数 | 依据 | 现状 |
|---|---|---|
| **召回率基底** `\|命中\|/\|query\|` | 意图覆盖优先：能覆盖全部意图的 skill 排在只覆盖部分的前面——路由的主目标 | ✅ 生效 |
| **priority × 0.01** | tie-breaker 级：只在同分时生效，人工微调同分候选，**不允许喧宾夺主**压过语义匹配 | ✅ 生效 |
| output_types 命中 +0.3 | 产出匹配是强信号（要 pptx 给只能产 md 的 skill 必失败） | ⚠️ **预留未生效**：`registry.score()` 签名支持，但 TaskBook schema 无 `expected_outputs` 字段，调用方恒传空集 |
| input_types 命中 +0.2 | 素材匹配（弱信号，可靠格式转换救） | ❌ 从未实现，v1.1.0 起从 SKILL.md §3.2 描述中移除 |

> 本节的"⚠️ 预留未生效"是 v1.0.x 时代"宣称与实现不符"的遗留——
> SKILL.md §3.2 曾把两个加权项写成生效算法。v1.1.0 已按实际实现对齐文档。
> 启用路径：TaskBook 增加 `expected_outputs` 字段（MINOR 变更）→ L1 通译时从
> accept 解析产出类型 → score() 的加权自然生效，基准用例需先行补齐。

**调优方法（改系数的合法流程）：**
1. 改系数前，先在 `cli/tests/benchmark_routing.json` 里**补能区分新旧系数差异的用例**——基准覆盖不了的场景不允许凭空调参
2. 改完跑 `pytest tests/test_routing_benchmark.py`：基准全绿才允许合入
3. 系数变更写入 CHANGELOG 并注明基准用例编号

---

## 4. D12 可观测性架构

```
zlt run "..."
   │
   ├─ 控制台 [INFO] layer1_done what=...     ← 人类可读
   │
   └─ ~/.zhenglingtai/runs/20260722-100000.log
       {"timestamp":"...","level":"INFO","msg":"layer1_done","what":"..."}
       {"timestamp":"...","level":"INFO","msg":"layer2_done","main_skill":"..."}
       {"timestamp":"...","level":"INFO","msg":"run_complete"}
       ↑
       JSON Lines，可被 jq 解析
```

`zlt health --verbose` 读取 `~/.zhenglingtai/runs/*.log` 汇总最近 10 条。
