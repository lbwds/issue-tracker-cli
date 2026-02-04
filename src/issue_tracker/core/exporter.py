"""Export 逻辑: 从数据库生成 markdown 文件."""

from datetime import datetime

from .config import Config
from .database import Database
from .model import Issue


# 状态符号映射
STATUS_EMOJI = {
    "fixed": "✅ 已修复",
    "pending": "❌ 待修复",
    "in_progress": "🟢 进行中",
    "planned": "📋 待规划",
    "n_a": "⚠️ 不适用",
}

# 优先级排序权重（数值越小排越前）
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

# 优先级分组标题模板
PRIORITY_SECTION_TITLES = {
    "P0": "Critical Priority (P0 - 紧急，影响硬实时性能)",
    "P1": "High Priority (P1 - 高，严重影响代码质量和安全性)",
    "P2": "Medium Priority (P2 - 中，影响代码可维护性和健壮性)",
    "P3": "Low Priority (P3 - 低，代码风格和最佳实践)",
}


class Exporter:
    """从数据库导出 markdown 报告."""

    def __init__(self, config: Config, db: Database):
        self._config = config
        self._db = db

    def export(self, output_path: str | None = None) -> str:
        """生成 markdown 并写入文件.

        Args:
            output_path: 输出路径，None 时使用 config 中的默认值

        Returns:
            实际写入的文件路径
        """
        if output_path is None:
            output_path = self._config.export_output

        content = self._generate()

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def _generate(self) -> str:
        """生成完整的 markdown 内容."""
        all_issues = self._db.query_issues()
        stats = self._db.get_stats()

        sections = []

        # 头部元信息
        sections.append(self._header(stats))

        # 目录
        sections.append(self._toc())

        # 文档格式规范
        sections.append(self._format_spec())

        # 总体统计
        sections.append(self._statistics(all_issues, stats))

        # 按优先级分组的详细条目
        # 先按优先级分组，特殊处理 Architecture(A-) 和 Test(T-)
        grouped = self._group_issues(all_issues)
        for priority in ["P0", "P1", "P2", "P3"]:
            if priority in grouped and grouped[priority]:
                sections.append(self._priority_section(priority, grouped[priority]))

        # Architecture 条目单独一节
        if "Architecture" in grouped and grouped["Architecture"]:
            sections.append(self._architecture_section(grouped["Architecture"]))

        # Test 条目单独一节
        if "Test" in grouped and grouped["Test"]:
            sections.append(self._test_section(grouped["Test"]))

        # 待修复问题优先级排序
        sections.append(self._pending_priority_list(all_issues))

        # 附录统计
        sections.append(self._appendix(all_issues))

        # 页脚
        sections.append(self._footer())

        return "\n".join(sections)

    # ── 各段生成 ─────────────────────────────────────────────────────────────

    def _header(self, stats: dict) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        total = stats["total"]
        fixed = stats["by_status"].get("fixed", 0)
        pending_count = total - fixed - stats["by_status"].get("n_a", 0)
        lines = [
            "# WeldSmart Pro 全阶段问题清单汇总",
            "",
            f"> 生成时间: {now}",
            f"> 总条目数: {total} | 已修复: {fixed} | 待处理: {pending_count}",
            f"> 文档版本: 全阶段完整版（由 issue-tracker 工具自动生成）",
            "",
            "---",
            "",
        ]
        return "\n".join(lines)

    def _toc(self) -> str:
        lines = [
            "## 目录",
            "",
            "- [文档格式规范](#文档格式规范)",
            "  - [问题编号规则](#问题编号规则)",
            "  - [问题条目格式](#问题条目格式)",
            "- [总体统计](#总体统计)",
            "  - [按优先级统计](#按优先级统计)",
            "  - [问题概要汇总](#问题概要汇总)",
            "- [Critical Priority (P0 - 紧急，影响硬实时性能)](#critical-priority-p0---紧急影响硬实时性能)",
            "- [High Priority (P1 - 高，严重影响代码质量和安全性)](#high-priority-p1---高严重影响代码质量和安全性)",
            "- [Medium Priority (P2 - 中，影响代码可维护性和健壮性)](#medium-priority-p2---中影响代码可维护性和健壮性)",
            "- [Low Priority (P3 - 低，代码风格和最佳实践)](#low-priority-p3---低代码风格和最佳实践)",
            "- [Architecture Issues (架构设计问题)](#architecture-issues-架构设计问题)",
            "- [Test Issues (测试稳定性问题)](#test-issues-测试稳定性问题)",
            "- [待修复问题优先级排序](#待修复问题优先级排序)",
            "- [附录：问题分类统计](#附录问题分类统计)",
            "",
            "---",
            "",
        ]
        return "\n".join(lines)

    def _format_spec(self) -> str:
        lines = [
            "## 文档格式规范",
            "",
            "### 问题编号规则",
            "",
            "| 前缀 | 优先级 | 说明 |",
            "|------|--------|------|",
        ]
        for prefix, info in self._config.prefixes.items():
            lines.append(f"| {prefix}-xxx | {info['priority']} ({info['label']}) | {info['label']} |")
        lines.extend([
            "",
            "### 问题条目格式",
            "",
            "```markdown",
            "### X-xxx: 问题标题 - ❌ 待修复/✅ 已修复",
            "**发现日期**: YYYY-MM-DD",
            "**文件**: `文件路径`",
            "**位置**: 行号或代码位置",
            "",
            "**问题描述**:",
            "问题的详细描述，包括代码示例(如有)。",
            "",
            "**影响**:",
            "问题造成的影响。",
            "",
            "**修复方案**:",
            "建议的修复方案，包括代码示例。",
            "",
            "**预计工时**: X 小时",
            "**优先级**: P0/P1/P2/P3",
            "```",
            "",
            "---",
            "",
        ])
        return "\n".join(lines)

    def _statistics(self, all_issues: list[Issue], stats: dict) -> str:
        lines = [
            "## 总体统计",
            "",
            "### 按优先级统计",
            "",
            "| 优先级 | 总数 | 已修复 | 待处理 | 进度 |",
            "|--------|------|--------|--------|------|",
        ]

        # 按优先级分组统计
        grouped = self._group_issues(all_issues)

        # 显示顺序: P0, P1, P2, P3, Architecture, Test
        display_order = [
            ("Critical (P0)", "P0"),
            ("High     (P1)", "P1"),
            ("Medium   (P2)", "P2"),
            ("Low      (P3)", "P3"),
            ("Architecture (A)", "Architecture"),
            ("Test     (T)", "Test"),
        ]

        grand_total = 0
        grand_fixed = 0
        grand_pending = 0

        for label, key in display_order:
            issues_in_group = grouped.get(key, [])
            total = len(issues_in_group)
            fixed = sum(1 for i in issues_in_group if i.status == "fixed")
            # n_a 不算待处理
            pending = total - fixed - sum(1 for i in issues_in_group if i.status == "n_a")
            pct = f"{int(fixed / total * 100)}%" if total > 0 else "N/A"
            lines.append(f"| {label} | {total} | {fixed} | {pending} | {pct} |")

            grand_total += total
            grand_fixed += fixed
            grand_pending += pending

        grand_pct = f"{int(grand_fixed / grand_total * 100)}%" if grand_total > 0 else "N/A"
        lines.append(f"| **总计** | **{grand_total}** | **{grand_fixed}** | **{grand_pending}** | **{grand_pct}** |")

        # n_a 备注
        na_issues = [i for i in all_issues if i.status == "n_a"]
        if na_issues:
            na_ids = ", ".join(i.id for i in na_issues)
            lines.append(f"\n*注：{na_ids} 标记为\"不适用\"，实际无需修复")

        # 问题概要汇总
        lines.extend([
            "",
            "### 问题概要汇总",
            "",
            "| 编号 | 问题描述 | 优先级 | 发现日期 | 状态 |",
            "|------|----------|--------|----------|------|",
        ])

        # 按编号排序输出概要表
        for issue in sorted(all_issues, key=lambda i: self._sort_key(i.id)):
            status_emoji = STATUS_EMOJI.get(issue.status, issue.status)
            lines.append(f"| {issue.id} | {issue.title} | {issue.priority} | {issue.discovery_date} | {status_emoji} |")

        lines.extend(["", "---", ""])
        return "\n".join(lines)

    def _priority_section(self, priority: str, issues: list[Issue]) -> str:
        title = PRIORITY_SECTION_TITLES.get(priority, f"{priority} Priority")
        lines = [f"## {title}", ""]

        for issue in sorted(issues, key=lambda i: self._sort_key(i.id)):
            lines.append(self._format_issue(issue))
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _architecture_section(self, issues: list[Issue]) -> str:
        lines = ["## Architecture Issues (架构设计问题)", ""]
        for issue in sorted(issues, key=lambda i: self._sort_key(i.id)):
            lines.append(self._format_issue(issue))
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def _test_section(self, issues: list[Issue]) -> str:
        lines = [
            "## Test Issues (测试稳定性问题)",
            "",
            "> 以下问题为测试运行中发现的不稳定（flaky）测试。这些测试单独执行时全部通过，仅在完整测试套件压力下概率性失败。根因均为测试基础设施级别的资源竞争，非业务逻辑缺陷。",
            "",
        ]
        for issue in sorted(issues, key=lambda i: self._sort_key(i.id)):
            lines.append(self._format_issue(issue))
            lines.append("---")
            lines.append("")
        return "\n".join(lines)

    def _pending_priority_list(self, all_issues: list[Issue]) -> str:
        """待修复问题优先级排序章节."""
        pending = [i for i in all_issues if i.status in ("pending", "in_progress", "planned")]
        if not pending:
            return "## 待修复问题优先级排序\n\n所有问题已修复或不适用。\n\n---\n"

        lines = ["## 待修复问题优先级排序", ""]

        # 按优先级分组
        prio_groups = {}
        for issue in pending:
            p = issue.priority
            prio_groups.setdefault(p, []).append(issue)

        for p in ["P0", "P1", "P2", "P3"]:
            if p not in prio_groups:
                continue
            group = prio_groups[p]
            label_map = {"P0": "紧急 (P0)", "P1": "高 (P1)", "P2": "中 (P2)", "P3": "低 (P3)"}
            lines.append(f"### {label_map[p]}")
            total_hours = sum(i.estimated_hours or 0 for i in group)
            for issue in sorted(group, key=lambda i: self._sort_key(i.id)):
                status_emoji = STATUS_EMOJI.get(issue.status, issue.status)
                hours_str = f" ({issue.estimated_hours}h)" if issue.estimated_hours else ""
                lines.append(f"{_list_index(issue, group)}. **{issue.id}**: {issue.title}{hours_str} {status_emoji}")
            lines.append(f"\n**预计工时**: {total_hours} 小时")
            lines.append("")

        lines.extend(["---", ""])
        return "\n".join(lines)

    def _appendix(self, all_issues: list[Issue]) -> str:
        """附录: 问题分类统计."""
        lines = ["## 附录：问题分类统计", "", "### 按模块统计"]

        # 简单按文件路径推断模块
        module_map = {"core": [], "hal": [], "business": [], "tests": [], "other": []}
        for issue in all_issues:
            fp = issue.file_path or ""
            assigned = False
            for mod in ("core", "hal", "business", "tests"):
                if mod in fp.lower():
                    module_map[mod].append(issue)
                    assigned = True
                    break
            if not assigned:
                module_map["other"].append(issue)

        for mod, issues in module_map.items():
            if not issues:
                continue
            total = len(issues)
            fixed = sum(1 for i in issues if i.status == "fixed")
            pending_ids = [i.id for i in issues if i.status not in ("fixed", "n_a")]
            pending_str = f" - 含 {', '.join(pending_ids)}" if pending_ids else ""
            status_mark = "✅" if fixed == total else ""
            lines.append(f"- **{mod.capitalize()} 模块**: {total} 个问题 ({fixed} 已修复){pending_str} {status_mark}")

        lines.extend(["", "---", ""])
        return "\n".join(lines)

    def _footer(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return "\n".join([
            "---",
            "",
            f"**文档维护者**: issue-tracker 自动生成",
            f"**生成时间**: {now}",
            "",
        ])

    # ── 单条 Issue 格式化 ────────────────────────────────────────────────────

    def _format_issue(self, issue: Issue) -> str:
        """格式化单条 Issue 为 markdown."""
        status_emoji = STATUS_EMOJI.get(issue.status, issue.status)
        lines = [f"### {issue.id}: {issue.title} - {status_emoji}"]

        lines.append(f"**发现日期**: {issue.discovery_date}")

        if issue.file_path:
            # 多个文件路径用反引号包裹
            paths = [p.strip() for p in issue.file_path.split(",")]
            if len(paths) == 1:
                lines.append(f"**文件**: `{paths[0]}`")
            else:
                lines.append("**文件**: " + ", ".join(f"`{p}`" for p in paths))

        if issue.location:
            lines.append(f"**位置**: {issue.location}")

        lines.append("")

        if issue.description:
            lines.append("**问题描述**:")
            lines.append(issue.description)
            lines.append("")

        if issue.impact:
            lines.append("**影响**:")
            lines.append(issue.impact)
            lines.append("")

        if issue.fix_plan:
            lines.append("**修复方案**:")
            lines.append(issue.fix_plan)
            lines.append("")

        if issue.estimated_hours is not None:
            lines.append(f"**预计工时**: {_format_hours(issue.estimated_hours)}")

        if issue.actual_hours is not None:
            lines.append(f"**实际工时**: {_format_hours(issue.actual_hours)}")

        if issue.priority:
            lines.append(f"**优先级**: {issue.priority}")

        # 状态行（含修复日期）
        if issue.status == "fixed" and issue.fix_date:
            lines.append(f"**状态**: ✅ 已修复 ({issue.fix_date})")
        elif issue.status == "n_a":
            lines.append(f"**状态**: ⚠️ 不适用")
        elif issue.status == "in_progress":
            lines.append(f"**状态**: 🟢 进行中")
        elif issue.status == "planned":
            lines.append(f"**状态**: 📋 待规划")

        lines.append("")
        return "\n".join(lines)

    # ── 辅助 ─────────────────────────────────────────────────────────────────

    def _group_issues(self, issues: list[Issue]) -> dict[str, list[Issue]]:
        """按分组键归类 Issue.

        A- 前缀 → Architecture, T- 前缀 → Test, 其余按 priority 分组。
        """
        groups: dict[str, list[Issue]] = {}
        for issue in issues:
            prefix = issue.id.split("-")[0] if "-" in issue.id else ""
            if prefix == "A":
                groups.setdefault("Architecture", []).append(issue)
            elif prefix == "T":
                groups.setdefault("Test", []).append(issue)
            else:
                groups.setdefault(issue.priority, []).append(issue)
        return groups

    @staticmethod
    def _sort_key(issue_id: str) -> tuple[str, int]:
        """编号排序键: (前缀字母, 数字部分)."""
        parts = issue_id.split("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return (parts[0], int(parts[1]))
        return (issue_id, 0)


# ── 模块级辅助函数 ───────────────────────────────────────────────────────────


def _format_hours(hours: float) -> str:
    """格式化工时: 整数显示为 'X 小时'，小数保留一位."""
    if hours == int(hours):
        return f"{int(hours)} 小时"
    return f"{hours} 小时"


def _list_index(issue: Issue, group: list[Issue]) -> int:
    """返回 issue 在 group 中的 1-based 索引."""
    try:
        return group.index(issue) + 1
    except ValueError:
        return 0
