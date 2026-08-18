# 受控意图标签词表（intent-tags）

> **本词表是路由主键**：政令台流转司从任务书里归一化出的 `intent_tags_query` 必须从这里选词；新 skill 的 `intent_tags` 也必须从这里取词或提 PR 新增。
>
> **同义不同词会直接导致匹配失效**——这是过去"路由准确率上不去"的最常见 bug。所以：
> - **禁止**自造同义标签（如同时有 `write_copy` 和 `write_text`）
> - **禁止**近义重复（语义重叠的标签需合并）
> - 唯一例外是"宽 vs 专"层级关系：`write_copy`（宽）与 `write_copy_sales`（专）可以并存，按"最具体优先"消歧（参见 SKILL.md §3.7）
>
> **废弃别名归一化（v1.0.1 起）：** 表中带 ⚠️ 的废弃别名（如 `slide_deck`）仅为兼容旧 skill 保留。
> 路由匹配时，流转司应先把任务书和登记册里的废弃别名**归一化替换为规范词**再打分；新声明 capability 的 skill 一律使用规范词。

## 命名约定

- 全小写 + 蛇形命名（`clean_excel`，不 `CleanExcel` / `clean-excel`）
- 格式：`动词_对象` 或 `领域_动作`
- `decree_mode` / `orchestrate_skills` 是元 Skill（政令台本身）的自指标签

## 为什么这样分类

分类沿用主流内容/数据/媒体生产流程——便于使用者一看就知道"我想要的能力属于哪类，能用哪个标签"。新增分类请说明归属。

---

## 内容创作 content

| 标签 | 语义 | 典型用法 |
|---|---|---|
| `content_produce` | 通用内容生产（文章 / 视频流水线） | 用一个 meta-skill 串多道工序产整套内容 |
| `article_pipeline` | 图文流水线 | 选题→大纲→配图→多平台改写 |
| `video_pipeline` | 视频生产线 | 文案→分镜→配音→合成 |
| `write_copy` | 通用营销文案（宽） | 任何偏商业场景的文案基线 |
| `write_copy_sales` | 卖货/销售文案（专，如雷军风格） | 偏带货 / 发布会 / 评测类文案 |
| `write_novel` | 小说写作（短中篇） | 单篇 / 短篇 |
| `long_form_fiction` | 长篇虚构（章回/长篇连载） | 长篇连载 |
| `write_book` | 基于知识库写书 | 把已有材料组织成完整书籍 |

## 数据处理 data

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `clean_excel` | 清洗 Excel | 脏数据去重、格式统一 |
| `normalize_table` | 表格规范化 | 列名/类型对齐 |
| `dedupe_rows` | 去重 | 整行重复 / 关键字段重复 |
| `data_analysis` | 数据分析 | 统计、可视化、洞察 |

## 研究洞察 research

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `competitor_analysis` | 竞品分析 | A vs B 对比 |
| `market_insight` | 市场洞察 | 行业研究 / 趋势 |
| `web_research` | 联网调研 | 一般资料收集 |
| `user_research` | 用户研究 | 用户画像 / 访谈分析 |

## 培训教育 training

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `training_doc` | 培训材料 | 培训大纲 / 培训讲义 |
| `courseware` | 课件 / 讲义 | 演示用 PPT / 讲稿 |
| `handbook` | 操作手册 | SOP / 用户手册 |
| `instructional_design` | 课程设计 | ADDIE / 教学设计 |
| `course_plan` | 课程方案 | 单门课的完整方案 |

## 媒体生成 media

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `transcript_video` | 视频转写 / 提取文案 | 音视频转文字 |
| `extract_copy` | 提取文案 | 从音视频/图片里抠文字 |
| `make_ppt` | 做 PPT（规范词） | 汇报幻灯片 |
| `slide_deck` | ⚠️ 已废弃别名 | v1.0.1 起归一化为 `make_ppt`；仅为兼容旧 skill 保留，新 skill 禁用（按"删词需 MAJOR"承诺暂不删除） |
| `poster_prompt` | 海报提示词 | AI 生图用的文字提示词 |
| `image_gen` | 出图 | 文生图 / 图生图 |
| `video_gen` | 出视频 | 文生视频 |
| `edit_video` | 剪视频 / 口播处理 | 识别口误 / 生成审查稿 |

## 产品 / PM product

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `prd` | 产品需求文档 | PRD 撰写 |
| `requirement` | 需求梳理 | 用户故事 / 需求拆解 |
| `roadmap` | 路线图 | 迭代 / 里程碑规划 |

## 知识管理 knowledge

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `knowledge_frame` | 知识框架梳理 | 把材料组织成框架图 / 课程脉络 |
| `kb_fetch` | 抓取知识库 / 文档 | 从飞书/语雀/wiki 取内容 |

## Skill 工程 skill-dev

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `skill_create` | 创建 skill | 从 0 设计一个 SKILL.md |
| `skill_pack` | 打包 skill | 打成 zip 便于分发 |
| `skill_audit` | skill 安全审查 | 安装前审查第三方 skill |

## 通用 general

| 标签 | 语义 | 典型场景 |
|---|---|---|
| `summarize` | 总结 | 长文 → 摘要 |
| `translate` | 翻译 | 中英互译等 |
| `qa` | 问答 / 查用法 | 短问短答 |
| `decree_mode` | 进入政令模式本身 | 政令台元 Skill 自指 |
| `orchestrate_skills` | 调度 / 编排多个 skill | 政令台流转层的语义标签 |

---

## 维护规则

### 新增词流程

1. 先查现有词表确认无同义/近义词
2. 提新词时应给出：
   - 归属分类（已有分类或新建）
   - 与最近邻词的区别（"宽 vs 专"层级关系 / 完全独立）
   - 至少 1 个未来会用它的 skill 类型举例
3. 改本文件 `intent-tags.md` → 同步 commit CHANGELOG

### 禁止

- 自造同义标签 → 直接复用现有或提 PR
- 近义重复（含外文直译）→ 必须合并
- 测试标签 / 临时标签 → 留 PR review 时剔除
