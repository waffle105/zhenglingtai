# 政令任务书（CLI 模板，与 A 形态同 schema）

> **字段表（键名 / 类型 / 必填 / 含义）：**
>
> | 字段 | 类型 | 必填 | 含义 |
> |---|---|---|---|
> | `what` | string | ✅ | 意图（一句话说明） |
> | `why` | string | ✅ | 目的（决定验收的"好坏"标准） |
> | `scope_in` | list[string] | ✅ | 范围：含 |
> | `scope_out` | list[string] | ✅ | 范围：不含 |
> | `accept` | list[string] | ✅ | 验收标准（至少 1 条） |
> | `unknowns` | list[string] | ✅ | 未知项（可空） |
> | `intent_tags` | list[string] | ✅ | 意图标签（从词表选） |

```json
{
  "what": "<一句话说清要做什么>",
  "why": "<为什么要做 / 交付给谁>",
  "scope_in": ["<本次覆盖的内容>"],
  "scope_out": ["<明确排除的内容，至少 1 条>"],
  "accept": [
    "<可勾选的达成条件>",
    "<第二条>"
  ],
  "unknowns": [],
  "intent_tags": [
    "<从 ../../registry/intent-tags.md 选词>"
  ]
}
```
