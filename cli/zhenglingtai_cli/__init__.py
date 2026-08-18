"""政令台 CLI（B 形态 / 纪律层的脱壳版）—— Python 包 `zhenglingtai-cli`。

定位：
    - 是 `zhenglingtai/` 元 skill 的**可选附件**，不是独立 skill 形态
    - 让"没 WorkBuddy / 想用 CLI / 想自己选 LLM"的同事也能用纪律层
    - 同四层纪律、同 schema（任务书/工序单/验收单 JSON），跨形态互通

设计动机（B 形态为什么存在）：
    A 元 skill 在 WorkBuddy 进程内能直接 `Skill(...)` 调任意 skill——最自然。
    但你可能只是终端 + Python，没开 WorkBuddy——B 形态就是让你在终端里跑同一套纪律。

What this package does vs what the meta-skill does:
    元 skill (zhenglingtai/SKILL.md)：在 WorkBuddy 内被加载，自动调度任意 skill
    本包 (cli/zhenglingtai_cli)：在终端被 `python -m zhenglingtai_cli` 调起
    **纪律层/路由算法/任务书 schema 都一样**——形态差异只在"如何调子能力"。

命名规则：
    顶层目录 = `zhenglingtai/`（Skill 生态认）
    pip 包名 = `zhenglingtai-cli`（PEP 503 规范化：连字符）
    Python 模块 = `zhenglingtai_cli`（PEP 8 模块名规范：下划线）
    三处一致：基础名都是 zhenglingtai，差异只在分隔符（-/→/_）。

注释规范（沿用 ../SKILL.md）：
    - 文件头写"用途+作者+版本"
    - 关键设计点显式"为什么"段
    - "如果 X 则 Y" 不省略
    - 硬约束 HARD: 前缀
    - 跨文件用相对路径 import

版本：v1.2.0（与 ../CHANGELOG.md 一致）
"""

__version__ = "1.2.0"
