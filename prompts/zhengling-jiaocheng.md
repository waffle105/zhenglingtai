# 政令台教程（C 形态：提示词附件）

> **形态：** C（纯提示词片段；无代码，无 Python）
> **配套：** 4 个角色的 system prompt 在 `zhengling-profiles/` 下；速查卡在 `zhengling-kuai-cha.md`

---

## 0. 什么是"政令台"的纪律层

政令台不是 LLM——它是一套**让 LLM 干活更可靠的工作流**。

```
通译司 → 问清楚要做什么（出"任务书"）
流转司 → 规划怎么干（出"工序单"）
执行工坊 → 一步一脚印干活（产"阶段简报"）
督查验收司 → 对照任务书封驳（出"验收确认单"）
```

**为什么这样拆：** 单 LLM 既要理解、又要规划、又要干、又要检查——它会偷懒、漏项、看起来干完了其实没干。四层让每个角色只干一件事，**封驳权独立**才能压住偷懒。

---

## 1. 五分钟跑通

### 第 1 步：粘 system prompt

把 `zhengling-profiles/tongyi.md` 整段粘到 LLM 对话框 system 指令（或第一条 user 消息）。

### 第 2 步：发指令

> "帮我做一份竞品分析"

通译司出任务书 JSON，**停下等确认**。

### 第 3 步：粘流转司 prompt

确认后新开会话（或同会话换 system prompt），粘 `zhengling-profiles/liuzhuan.md`，喂任务书给它。

### 第 4 步：自己（或另一会话）当执行工坊

执行工坊在提示词形态里**通常是你自己**——因为没有 Python 帮你调子能力。按工序单一步步做，每步写简报。

### 第 5 步：粘验收司 prompt

新开会话粘 `zhengling-profiles/yanshou.md`，把任务书 + 工序单 + 实际产物喂给它，出验收单。

---

## 2. 完整示例（重任务 · 一遍四层）

> "帮我做一份竞品对比分析，要能直接给老板汇报，最后给我一份 PPT。"

### ① 通译 → 任务书

```json
{
  "what": "A vs B 两家产品的功能/价格/定位/用户口碑 4 维度对比分析，产出 md + PPT",
  "why": "给老板汇报，需结论清晰、数据可信",
  "scope_in": ["4 维度对比", "md + pptx 双产出"],
  "scope_out": ["市场规模预测", "财务建模"],
  "accept": [
    "md 含 A、B 双方案例维度对比",
    "关键数据有出处",
    "PPT 页数 ≥ 10，含「结论与建议」页"
  ],
  "unknowns": [],
  "intent_tags": ["competitor_analysis", "make_ppt"]
}
```

> **门禁：** 没点头 → 不进 ②。

### ② 流转 → 工序单

```json
{
  "main_skill": "competitor-analysis",
  "cooperative": ["pptx"],
  "meta_delegate": "",
  "steps": [
    {"index": 1, "skill_id": "competitor-analysis",
     "input": "A vs B 主题", "output": "竞品分析.md",
     "check": "md 存在、含 4 维度对比"},
    {"index": 2, "skill_id": "pptx",
     "input": "竞品分析.md", "output": "竞品分析.pptx",
     "check": "pptx 存在、页数 ≥ 10"}
  ],
  "stop_points": [1],
  "fallbacks": {"pptx": "退回 markdown 汇报版"}
}
```

### ③ 执行 → 阶段简报

```
[步骤 1]
- 做了什么：网上调研 + 写竞品分析.md
- 产出：竞品分析.md（3.2KB）
- 下一步：暂停等用户确认

（用户口头确认"分析可以，推进"）

[步骤 2]
- 做了什么：md 转 PPT
- 产出：竞品分析.pptx（12 页）
- 下一步：进入验收
```

> 遇阻输出结构化块：
> ```
> 【BLOCK】层=执行 步骤=2
> 原因：不知用什么 PPT 工具
> 回退：先做 markdown 汇报版
> 需用户决策：true
> ```

### ④ 验收 → 验收单

```json
{
  "result": "达标",
  "per_item": [
    {"item": "md 含 A、B 双方案例维度对比", "status": "ok", "evidence": "4 维度齐全"},
    {"item": "关键数据有出处", "status": "ok", "evidence": "8 处带 URL"},
    {"item": "PPT 页数 ≥ 10", "status": "ok", "evidence": "12 页"}
  ],
  "deviations": [],
  "subjective": ["文风是否符合预期？"],
  "deliverables": [
    {"path": "竞品分析.md", "type": "md", "summary": "A vs B 4 维度对比"},
    {"path": "竞品分析.pptx", "type": "pptx", "summary": "12 页汇报版"}
  ]
}
```

---

## 3. 复杂度分级

| 级别 | 判定 | 走法 |
|---|---|---|
| **轻** | 单一件事、明确 | 三句话（复述→规划→自检）|
| **中** | 一两件、有依赖 | 四层 inline |
| **重** | 多件、要存档 | 全四层 + 每层产物落 markdown |

---

## 4. 反幻觉自检

- [ ] 交付物真实存在（不编造）
- [ ] 无任务书范围外的加戏
- [ ] 引用的外部事实有出处
- [ ] 未知项已解决或显式标"未确认"

---

## 5. 升级路径

| 用了一阵子的痛点 | 怎么升 |
|---|---|
| 想自动化、不想手填 | 用 SKILL.md（元 skill）|
| 想跑批/CI/独立团队 | 用 prompts/ + CLI 子目录 |
| 想给团队同事铺 | 把 prompts/ 整目录打成 zip 发——他只要有 LLM 对话框 |
