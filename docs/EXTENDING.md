# 扩展指南

> **最后更新：** 2026-07-22 · **适用版本：** v1.2.0

---

## 1. 给 skill 加 capability 块

在你的 skill 的 `SKILL.md` frontmatter 里加 `metadata.capability`：

```yaml
---
name: 我的技能
metadata:
  capability:
    id: my-skill              # 必须等于目录名
    intent_tags:               # 从 registry/intent-tags.md 选词
      - write_copy
      - write_copy_sales
    input_types: [product_spec] # 能吃啥
    output_types: [md]          # 能产啥
    is_meta: false              # 是否内部会再调子 skill
    priority: 0                 # 冲突消解用（高者优先）
---

## 1.5 利用平台原生能力（v1.2.0+）

为你的 skill 起名（`id`）时，**优先复用原生能力名**——政令台在 4 层 fallback 链
里会先识别原生能力，不需要你在 `zhenglingtai-capabilities.yaml` 配任何东西：

| 原生 cap_id | 依赖 | 用途 |
|---|---|---|
| `read_text` / `write_text` | stdlib | 读 / 写文本（任意 utf-8 编码） |
| `read_json` / `write_json` | stdlib | 读 / 写 JSON，自动校验合法性 |
| `csv_read` / `csv_write` | stdlib | 读 / 写 CSV（BOM 兼容 Excel） |
| `hash_sha256` | stdlib | 算文件 SHA256（产物溯源） |
| `read_yaml` / `write_yaml` | PyYAML | 已属依赖，立装即用 |
| `pptx_create` | python-pptx | 出 PPT（未装时 hint 给"pip install python-pptx"） |
| `xlsx_read` / `xlsx_write` | openpyxl | 读写 xlsx（同上） |
| `image_resize` | Pillow | 缩放图片（同上） |

查看当前 venv 已就绪的能力：

```bash
zlt health --verbose
```

或直接编程：

```python
from zhenglingtai_cli import native
print(native.ready_ids())          # 已就绪的 cap id
print(native.report_missing())     # 未就绪的："  • pptx_create: pip install python-pptx"
```


```

**HARD：** `intent_tags` 必须从受控词表选词。自造词会导致路由匹配失效。

---

## 2. 自动迁移老 skill

```bash
# 看哪些 skill 缺 capability
zlt migrate scan

# LLM 建议标签
zlt migrate suggest <skill_id>

# 批量 dry-run
zlt migrate batch --dry-run

# 确认后执行（自动备份 .bak）
zlt migrate batch
```

---

## 3. 写 capabilities 配置

生成模板：

```bash
zlt capabilities init
```

然后编辑生成的 `zhenglingtai-capabilities.yaml`，把 `noop` 改成真实执行方式。

### kind: local（本地 Python 函数）

```yaml
my-skill:
  kind: local
  target: "my_tools.skill_module:main_function"
```

函数签名：`def main_function(input: str, work_dir: Path) -> dict`

返回 `{"ok": True, "outputs": [...], "logs": "..."}`。

### kind: http（HTTP POST）

```yaml
my-skill:
  kind: http
  url: "https://api.example.com/v1/process"
  method: POST
  headers:
    Authorization: "Bearer $MY_API_KEY"
  body_template:
    input: "$input"
    output: "$output"
```

**HARD：** 占位符用 `$input` / `$output`（不用 `{input}`，防格式化字符串攻击）。

### kind: cli（本地命令行）

```yaml
my-skill:
  kind: cli
  cmd: "python3"
  args:
    - "script.py"
    - "--input"
    - "$input"
    - "--output"
    - "$output"
```

---

## 4. 加 intent_tags 到词表

如果受控词表里没有你要的标签：

1. 编辑 `registry/intent-tags.md`
2. 在对应类别下加新词
3. 提 PR 或自行维护（参见 GOVERNANCE.md）

**命名规范：** `动词_名词`（如 `clean_excel`、`write_copy`），小写下划线，英文。

---

## 5. 写 meta-skill

如果你的 skill 本身是一条流水线（内部会调子 skill）：

```yaml
metadata:
  capability:
    id: my-pipeline
    intent_tags: [content_produce]
    is_meta: true    # ← 关键：政令台识别后整条委托
```

**HARD：** `id == "zhenglingtai"` 的 skill 永不参与 meta 委托（防自指套娃）。
