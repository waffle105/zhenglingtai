# 验收确认单（CLI 模板，与 A 形态同 schema）

> **字段表：**
>
> | 字段 | 类型 | 必填 | 含义 |
> |---|---|---|---|
> | `result` | enum{达标,未达标} | ✅ | 封驳结论 |
> | `per_item` | list[object] | ✅ | 每条 Accept 的对照 |
> | `deviations` | list[string] | ✅ | 偏差与补救建议 |
> | `subjective` | list[string] | ✅ | AI 不擅判项 |
> | `deliverables` | list[object] | ✅ | 实际产物路径 |

```json
{
  "result": "达标",
  "per_item": [
    {"item": "<任务书 Accept 第1条>", "status": "ok", "evidence": "<...>"},
    {"item": "<任务书 Accept 第2条>", "status": "fail", "deviation": "<...>"}
  ],
  "deviations": ["<未达标项的具体补救建议>"],
  "subjective": ["文风是否符合预期？"],
  "deliverables": [
    {"path": "<...>", "type": "md", "summary": "<一句话摘要>"}
  ]
}
```
