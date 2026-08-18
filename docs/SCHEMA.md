# Schema 参考

> **最后更新：** 2026-07-22 · **适用版本：** v1.2.0
> **JSON Schema：** 见 `templates/META.schema.json`

---

## 1. 政令任务书（TaskBook）

通译司（L1）的产物。

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `what` | string | ✅ | 意图：一句话说清要做什么 |
| `why` | string | ✅ | 目的：决定验收的"好坏"标准 |
| `scope_in` | list[string] | ✅ | 范围：含 |
| `scope_out` | list[string] | ✅ | 范围：不含（防加戏） |
| `accept` | list[string] | ✅ | 验收标准（可勾选，至少 1 条） |
| `unknowns` | list[string] | ✅ | 未知项（可空） |
| `intent_tags` | list[string] | ✅ | 意图标签（从 `intent-tags.md` 选词） |

```json
{
  "what": "A vs B 竞品分析",
  "why": "给老板汇报",
  "scope_in": ["4 维度对比", "md + pptx"],
  "scope_out": ["市场规模预测"],
  "accept": ["md 含双方案例", "PPT 页数 ≥ 10"],
  "unknowns": [],
  "intent_tags": ["competitor_analysis", "make_ppt"]
}
```

**兼容性承诺：** v1.0.0 起只加字段不删字段、不改字段名。

---

## 2. 执行工序单（Procedure）

流转司（L2）的产物。

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `main_skill` | string | ✅ | 主 skill id；通用模式为 `"(无登记)"` |
| `cooperative` | list[string] | ✅ | 协同 skill id 列表 |
| `meta_delegate` | string | ✅ | 委托 meta-skill id；无委托为空 |
| `steps` | list[Step] | ✅ | 工序步骤（至少 1 步） |
| `stop_points` | list[int] | ✅ | 需用户确认的步骤编号 |
| `fallbacks` | dict | ✅ | skill → 兜底策略映射 |

### Step 子字段

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `index` | int | ✅ | 步骤序号（从 1 开始） |
| `skill_id` | string | ✅ | 该步调用的 skill id |
| `input` | string | ❌ | 输入描述 |
| `output` | string | ❌ | 产出描述 |
| `check` | string | ❌ | 该步验收点 |

---

## 3. 验收确认单（Acceptance）

督查验收司（L4）的产物。

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `result` | enum | ✅ | `达标` / `未达标` |
| `per_item` | list[object] | ✅ | 每条 Accept 的对照 |
| `deviations` | list[string] | ✅ | 偏差与补救建议 |
| `subjective` | list[string] | ✅ | AI 不擅判项（等用户勾） |
| `deliverables` | list[object] | ✅ | 实际产物列表 |

**HARD：** `result=未达标` 时 `deviations` 不可空（自动补说明）。

### per_item 子字段

| 键名 | 类型 | 含义 |
|---|---|---|
| `item` | string | 任务书 Accept 条目 |
| `status` | enum | `ok` / `fail` |
| `evidence` | string | 证据 |
| `deviation` | string | 偏差描述（仅 fail 时） |

---

## 4. 政令档 META.json

每个政令档目录的元数据文件。详见 `templates/META.schema.json`（JSON Schema draft 2020-12）。

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `decree_id` | string | ✅ | 政令唯一标识 |
| `created_at` | string (date-time) | ✅ | 创建时间 |
| `intent_tags` | list[string] | ✅ | 意图标签 |
| `resolved_skills` | list[string] | ✅ | 路由匹配的 skill |
| `outputs` | list[object] | ✅ | 产出物 |
| `accept_status` | enum | ✅ | `达标` / `未达标` / `待用户确认` |
| `history` | list[object] | ✅ | 四层执行历史 |
| `subjective_pending` | list[string] | ❌ | 待用户确认项 |
| `retries` | integer | ❌ | 验收打回次数（默认 0） |
