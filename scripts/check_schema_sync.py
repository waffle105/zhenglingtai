#!/usr/bin/env python3
"""三形态 schema 一致性检查（v1.0.3，对应评审 P3）。

为什么存在：
    任务书 / 工序单 / 验收单三个 schema 同时出现在三处：
      1. 代码（单一事实来源）：cli/zhenglingtai_cli/discipline.py 的 dataclass
      2. 文档：docs/SCHEMA.md 的字段表
      3. CLI 模板：cli/templates/zhengling-*.md 的字段表
    任何一处改字段而另两处没跟上，就会出现"宣称与实现不符"（v1.0.0~v1.0.2 的教训）。
    本脚本在 CI 里挡住这种漂移。

用法：
    python scripts/check_schema_sync.py          # 在包根或任意目录跑
    退出码：0 = 一致；1 = 漂移（打印明细）

对比口径：
    - TaskBook   ↔ SCHEMA.md §1  ↔ cli/templates/zhengling-shibu-task.md
    - Procedure(含 Step) ↔ SCHEMA.md §2  ↔ cli/templates/zhengling-gongxu-dan.md
    - Acceptance ↔ SCHEMA.md §3  ↔ cli/templates/zhengling-yanshou-dan.md
    - 模板/文档里的 backtick 键名视为声明的字段集合
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 包根（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli"))

from zhenglingtai_cli import discipline  # noqa: E402


def _fields(dc) -> set[str]:
    """取 dataclass 的字段名集合。"""
    return set(dc.__dataclass_fields__.keys())


def _backtick_keys(md_path: Path) -> set[str]:
    """抠 markdown 里 `key` 形式的 backtick 键名（字段表声明）。"""
    text = md_path.read_text(encoding="utf-8")
    return set(re.findall(r"`([a-z_][a-z0-9_]*)`", text))


# (schema 名, dataclass 列表, SCHEMA.md 节标题关键词, cli 模板文件)
CHECKS = [
    (
        "TaskBook",
        [discipline.TaskBook],
        "政令任务书（TaskBook）",
        "zhengling-shibu-task.md",
    ),
    (
        "Procedure",
        [discipline.Procedure, discipline.Step],
        "执行工序单（Procedure）",
        "zhengling-gongxu-dan.md",
    ),
    (
        "Acceptance",
        [discipline.Acceptance],
        "验收确认单（Acceptance）",
        "zhengling-yanshou-dan.md",
    ),
]


def _schema_md_section_keys(keyword: str) -> set[str]:
    """从 SCHEMA.md 指定节（## 标题含关键词）里抠 backtick 键名。"""
    text = (ROOT / "docs" / "SCHEMA.md").read_text(encoding="utf-8")
    # 按 ## 分节，找到目标节
    sections = re.split(r"\n## ", text)
    for sec in sections:
        if keyword in sec.split("\n", 1)[0]:
            return set(re.findall(r"`([a-z_][a-z0-9_]*)`", sec))
    raise AssertionError(f"SCHEMA.md 里找不到节：{keyword}")


def main() -> int:
    drift = False
    for name, dcs, section_kw, tpl_file in CHECKS:
        code_fields: set[str] = set()
        for dc in dcs:
            code_fields |= _fields(dc)

        doc_fields = _schema_md_section_keys(section_kw)
        tpl_fields = _backtick_keys(ROOT / "cli" / "templates" / tpl_file)

        # 文档/模板可能引用其他 schema 的键（如示例 JSON 里的嵌套），
        # 判定标准：代码字段必须全部出现在文档与模板中（缺 = 漂移）；
        # 反向只警告（文档多写的通常是说明性引用）。
        miss_doc = code_fields - doc_fields
        miss_tpl = code_fields - tpl_fields
        if miss_doc:
            drift = True
            print(f"✘ {name}: SCHEMA.md 缺字段 {sorted(miss_doc)}")
        if miss_tpl:
            drift = True
            print(f"✘ {name}: cli/templates/{tpl_file} 缺字段 {sorted(miss_tpl)}")
        if not miss_doc and not miss_tpl:
            print(f"  ✔ {name}: 代码 {len(code_fields)} 字段在 SCHEMA.md 与 CLI 模板中一致")

    if drift:
        print("\nschema 漂移 detected——以 discipline.py 为准补齐文档/模板，或反向修正代码。")
        return 1
    print("\n三形态 schema 一致 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
