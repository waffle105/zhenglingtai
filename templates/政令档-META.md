# 政令档 META.json · 字段表

> **用途：** 每个政令档目录下的 `META.json`——记录该政令的元数据，用于验收追踪和自学习反哺。
> **schema：** 见 `META.schema.json`（JSON Schema draft 2020-12）

---

## 字段表

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `decree_id` | string | ✅ | 政令唯一标识：日期 + 意图缩写 + 短随机，如 `2026-07-22-竞品分析-a1b2c` |
| `created_at` | string (date-time) | ✅ | ISO 8601 创建时间 |
| `intent_tags` | list[string] | ✅ | 意图标签（从 `registry/intent-tags.md` 选词） |
| `resolved_skills` | list[string] | ✅ | 路由匹配到的 skill id 列表；通用模式下为空 |
| `outputs` | list[object] | ✅ | 产出物列表 |
| `accept_status` | enum | ✅ | 验收结论：`达标` / `未达标` / `待用户确认` |
| `history` | list[object] | ✅ | 四层执行历史 |
| `subjective_pending` | list[string] | ❌ | 待用户主观确认的项 |
| `retries` | integer | ❌ | 验收打回次数（默认 0） |

### outputs 子字段

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `type` | string | ✅ | 产出类型：md/xlsx/pptx/png/mp4/py 等 |
| `path` | string | ✅ | 相对于政令档目录的路径 |
| `bytes` | integer | ❌ | 文件大小 |
| `summary` | string | ❌ | 一句话摘要 |

### history 子字段

| 键名 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `layer` | enum | ✅ | 层名：`通译` / `流转` / `执行` / `验收` |
| `action` | string | ✅ | 该层做了什么 |
| `timestamp` | string (date-time) | ✅ | 执行时间 |
| `duration_ms` | integer | ❌ | 耗时（毫秒） |

---

## 示例

> 示例中的 skill id 均为 `example-*` 占位（通用版承诺：不预填任何真实 skill 名），
> 实际使用时替换为你本机登记册里的真实 id。

```json
{
  "decree_id": "2026-07-22-竞品分析-a1b2c",
  "created_at": "2026-07-22T10:00:00+08:00",
  "intent_tags": ["competitor_analysis", "make_ppt"],
  "resolved_skills": ["example-competitor-analysis", "example-ppt"],
  "outputs": [
    {"type": "md", "path": "交付物/竞品分析.md", "bytes": 12345, "summary": "3家竞品对比"},
    {"type": "pptx", "path": "交付物/竞品分析.pptx", "bytes": 882100, "summary": "12页汇报版"}
  ],
  "accept_status": "达标",
  "history": [
    {"layer": "通译", "action": "出任务书", "timestamp": "2026-07-22T10:00:00+08:00", "duration_ms": 1200},
    {"layer": "流转", "action": "路由到 example-competitor-analysis + example-ppt", "timestamp": "2026-07-22T10:01:00+08:00", "duration_ms": 800},
    {"layer": "执行", "action": "两步执行完成", "timestamp": "2026-07-22T10:05:00+08:00", "duration_ms": 240000},
    {"layer": "验收", "action": "3条accept全达标", "timestamp": "2026-07-22T10:06:00+08:00", "duration_ms": 3000}
  ],
  "subjective_pending": [],
  "retries": 0
}
```
