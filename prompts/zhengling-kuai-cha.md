# 政令台速查卡（C 形态）

---

## 三句话走轻任务

```
1) 复述确认：你让我做 X，对吗？
2) 规划：我打算 Y 步骤完成。
3) 自检：做完了，对照你的要求，A/B/C 都齐了。
```

适用：单一件事、明确、低歧义。

---

## 四层走中重任务

| 层 | 输入 | 产物 | 门禁 |
|---|---|---|---|
| ① 通译 | 口语指令 | 任务书 JSON | 未确认 → 不进② |
| ② 流转 | 任务书 + skill 清单 | 工序单 JSON | 未产出 → 不执行 |
| ③ 执行 | 工序单 | 阶段简报 + 产物 | 步骤失败 → 报阻塞 |
| ④ 验收 | 任务书 + 工序单 + 产物 | 验收确认单 | 未达标 → 打回 |

---

## 分级触发

| 用户说 | 推荐级别 |
|---|---|
| "简单点 / 直接做" | 轻 |
| "正式 / 重要 / 要存档 / 多步" | 重 |
| 没明示 + 单一件事 | 中 |

---

## 最小任务书 schema

```json
{what, why, scope_in[], scope_out[], accept[], unknowns[], intent_tags[]}
```

> 完整模板见政令台包内 `templates/政令任务书.md`（若你是从 `~/.zhenglingtai/prompts/` 读到的本卡，
> 模板在 `~/.workbuddy/skills/zhenglingtai/templates/` 下）

## 最小工序单 schema

```json
{
  main_skill, cooperative[], meta_delegate,
  steps[{index, skill_id, input, output, check}],
  stop_points[], fallbacks{}
}
```

## 封驳怎么写

```json
{
  "result": "未达标",
  "per_item": [
    {"item": "<任务书 Accept 第 N 条>", "status": "fail", "deviation": "<...>"}
  ],
  "deviations": ["<补救建议>"],
  "subjective": ["<AI 不擅判项>"]
}
```

> HARD：result=未达标 时 deviations 不可空。

---

## 遇阻输出模板

```
【BLOCK】层=执行 步骤=<编号>
原因：<...>
回退：<建议处理>
需用户决策：<true/false>
```

---

## 五种产物类型契约

| 产物 | 验收能查的 |
|---|---|
| md/txt | 文件存在、非空、含关键段 |
| xlsx/csv | 文件存在、sheet/列数符合预期 |
| pptx | 文件存在、页数 ≥ 预期 |
| png/jpg/svg | 文件存在、尺寸 > 0 |
| mp4 | 文件存在、时长 > 0 |

主观项（文风/创意/老板视角）→ 写进 `subjective`，**等用户勾**。
