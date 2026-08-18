"""环境探测器——决定 zhengling 该走哪条路径。

聚合层（zhengling shim）的灵魂。
Why this exists:
    单一 skill 包 `zhenglingtai/` 不需要"三形态"——它本身就能跑。
    但用户可能在不同环境里用（WorkBuddy 内 / 终端 Python CLI / 没 Python 没用 WB）。
    本探测器只看"什么能用"，让 shim 自动派发。

策略：
    优先级：WorkBuddy 内自动激活 > 终端 CLI > 提示词兜底
    探测顺序：先看 SKILL.md 是否被 WB 加载（靠路径探测）→ 后看 zhengling CLI → 最后看 prompt 副本。

注释规范：
    - 函数 docstring 三行
    - 函数 < 50 行
    - 关键判定显式注释"如果 X 则 Y"
    - 硬约束 HARD: 前缀
    - 跨文件 import 用相对路径

版本：v1.2.0
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path


class Form(str, Enum):
    """使用场景枚举——不需要"哪形态"，而是"什么能用"。

    用 str Enum 让结果能直接 JSON 序列化 / 写环境变量。

    WB     = 在 WorkBuddy 内（SKILL.md 被加载），直接输出
    CLI    = 终端里 zhengling CLI 可调
    PROMPT = 兜底：~/.zhenglingtai/prompts/ 存在
    NONE   = 啥都没装
    """

    WB = "WB"
    CLI = "CLI"
    PROMPT = "PROMPT"
    NONE = "NONE"


@dataclass
class DetectResult:
    """探测结果。

    字段表（键名 / 类型 / 必填 / 含义）：
      active          enum     ✅   选中的形态
      wb_available    bool     ✅   WB 内 SKILL.md 是否可加载
      cli_available   bool     ✅   终端 zhengling CLI 是否可用
      prompt_available bool     ✅   提示词副本是否存在
      skill_count     int      ❌   可路由 skill 数
      cwd             str      ❌   探测时所在目录
      notes           list[str]❌   备注
    """

    active: Form
    wb_available: bool
    cli_available: bool
    prompt_available: bool
    skill_count: int = 0
    cwd: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["active"] = self.active.value
        return d


_FRONTMATTER_RE = None  # 延迟编译，见 _frontmatter_text()


def _frontmatter_text(text: str) -> str:
    """抠出 YAML frontmatter 块（无则返回空串）。

    Why this exists:
        v1.0.2 前用 `"capability:" in text` 裸字符串扫全文——正文提到该词即误判。
        只查 frontmatter 才是"skill 是否声明了 capability"的真实判据。
    """
    global _FRONTMATTER_RE
    import re
    if _FRONTMATTER_RE is None:
        _FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    m = _FRONTMATTER_RE.match(text)
    return m.group(1) if m else ""


def _probe_wb() -> tuple[bool, str]:
    """探测 WB：找 ~/.workbuddy/skills/zhenglingtai/SKILL.md。

    返回 (是否可用, 证据文本)。
    """
    p = Path.home() / ".workbuddy" / "skills" / "zhenglingtai" / "SKILL.md"
    if not p.exists():
        return False, "未找到 ~/.workbuddy/skills/zhenglingtai/SKILL.md"
    text = p.read_text(encoding="utf-8", errors="ignore")
    fm = _frontmatter_text(text)
    if "capability:" in fm and "id: zhenglingtai" in fm:
        return True, f"找到 {p}"
    return True, f"找到 {p}（但 frontmatter 异常）"


def _probe_cli() -> tuple[bool, str]:
    """探测 CLI：zlt 命令（v1.0.3 起的 pip 入口）或 Python 模块。

    Why zlt not zhengling:
        v1.0.3 起 pip console_script 改名 zlt——旧名 zhengling 是 shim 占用
        （本探测就是 shim 调起的，which("zhengling") 会命中 shim 自己，误报 CLI 可用）。
    """
    which = shutil.which("zlt")
    if which:
        return True, f"zlt 命令位于 {which}"
    try:
        import zhenglingtai_cli  # noqa: F401
        return True, "Python 模块 zhenglingtai_cli 可 import"
    except ImportError:
        return False, "zlt 命令未找到且 zhenglingtai_cli 不可 import"


def _probe_prompt() -> tuple[bool, str]:
    """探测提示词副本。"""
    p = Path.home() / ".zhenglingtai" / "prompts"
    if not p.exists():
        return False, "未找到 ~/.zhenglingtai/prompts/"
    mds = list(p.glob("**/*.md"))
    if not mds:
        return False, f"{p} 存在但空"
    return True, f"{p} 含 {len(mds)} 个 md"


def _count_capable_skills() -> int:
    """统计声明了 capability 的 skill 数（v1.0.2 起只查 frontmatter）。"""
    skills_dir = Path.home() / ".workbuddy" / "skills"
    if not skills_dir.exists():
        return 0
    cnt = 0
    for child in skills_dir.iterdir():
        if not child.is_dir():
            continue
        sm = child / "SKILL.md"
        if not sm.exists():
            continue
        text = sm.read_text(encoding="utf-8", errors="ignore")
        if "capability:" in _frontmatter_text(text):
            cnt += 1
    return cnt


def detect() -> DetectResult:
    """探测 → 决策 → 返回。

    决策规则（参见 ../INSTALL.md）：
      WB 可用 → 最自然
      CLI 可用 → 终端用户
      提示词可读 → 兜底
      都没 → NONE，notes 提示补装
    """
    wb_ok, wb_ev = _probe_wb()
    cli_ok, cli_ev = _probe_cli()
    pr_ok, pr_ev = _probe_prompt()

    # v1.0.2：证据文本进 notes（之前被直接丢弃，用户看不到"为什么不可用"）
    notes: list[str] = []
    if wb_ok:
        active = Form.WB
    elif cli_ok:
        active = Form.CLI
    elif pr_ok:
        active = Form.PROMPT
    else:
        active = Form.NONE
        notes.append("什么都没装——跑 ./install.sh 完整安装")
    notes.append(f"WB 探测：{wb_ev}")
    notes.append(f"CLI 探测：{cli_ev}")
    notes.append(f"提示词探测：{pr_ev}")

    skill_count = _count_capable_skills()
    if skill_count == 0:
        notes.append("本机没有声明 capability 的 skill——会进通用模式（纪律层仍生效）")

    return DetectResult(
        active=active,
        wb_available=wb_ok,
        cli_available=cli_ok,
        prompt_available=pr_ok,
        skill_count=skill_count,
        cwd=str(Path.cwd()),
        notes=notes,
    )


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    want_json = "--json" in args
    want_explain = "--explain" in args

    res = detect()

    if want_json:
        print(json.dumps(res.to_dict(), ensure_ascii=False))
        return 0

    print("===== zhengling doctor =====")
    print(f"探测目录: {res.cwd}")
    print()
    # v1.0.2：删掉了调试残留行 `CLI: {res.cli_available}`——
    # 探测证据已进 notes 统一展示，不再单独打一行布尔值
    print(f"  WorkBuddy 元 Skill：{'可用 ✔' if res.wb_available else '不可用 ✘'}")
    print(f"  CLI（zhenglingtai-cli）：{'可用 ✔' if res.cli_available else '不可用 ✘'}")
    print(f"  提示词副本：{'可用 ✔' if res.prompt_available else '不可用 ✘'}")
    print()
    print(f"  本机可路由 skill：{res.skill_count}")
    print(f"  → 当前生效：{res.active.value}")
    if res.notes:
        print()
        print("  备注：")
        for n in res.notes:
            print(f"    - {n}")

    if want_explain:
        print()
        print("===== 为什么是这个形态 =====")
        rules = {
            Form.WB: "WB 可用：在 WorkBuddy 里直接说'政令模式'，纪律全自动化。",
            Form.CLI: "WB 不可用但 CLI 可用：终端 zhengling run '...'。",
            Form.PROMPT: "啥都没装：把提示词副本粘进 LLM 对话框。",
            Form.NONE: "三处都不行：请跑 ./install.sh 完整安装。",
        }
        print(f"  {rules[res.active]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
