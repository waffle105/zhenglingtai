# 执行工序单（CLI 模板，与 A 形态同 schema）

> **字段表：**
>
> | 字段 | 类型 | 必填 | 含义 |
> |---|---|---|---|
> | `main_skill` | string | ✅ | 主 skill id |
> | `cooperative` | list[string] | ✅ | 协同 skill |
> | `meta_delegate` | string | ✅ | 委托 meta-skill |
> | `steps` | list[Step] | ✅ | 工序步骤 |
> | `stop_points` | list[int] | ✅ | 步骤后需用户确认 |
> | `fallbacks` | dict | ✅ | skill → 兜底策略 |
>
> **Step 子字段：**
>
> | 字段 | 类型 | 必填 | 含义 |
> |---|---|---|---|
> | `index` | int | ✅ | 步骤序号（从 1 开始） |
> | `skill_id` | string | ✅ | 该步调用的 skill id |
> | `input` | string | ❌ | 输入描述 |
> | `output` | string | ❌ | 产出描述 |
> | `check` | string | ❌ | 该步验收点 |

```json
{
  "main_skill": "<id | (无登记)>",
  "cooperative": ["<id>"],
  "meta_delegate": "",
  "steps": [
    {"index": 1, "skill_id": "<id>", "input": "...", "output": "...", "check": "..."}
  ],
  "stop_points": [<步骤编号>],
  "fallbacks": {"<skill_id>": "<兜底策略>"}
}
```
