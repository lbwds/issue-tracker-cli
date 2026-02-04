"""WeldSmart all-issues.md 迁移插件.

解析 WeldSmart Pro 项目特定的 all-issues.md 格式，提取所有问题条目。
"""

import re
from typing import Optional

from . import BaseMigrator


# 状态符号 → 状态枚举映射
STATUS_SYMBOL_MAP = {
    "✅": "fixed",
    "❌": "pending",
    "⚠️": "n_a",
    "🟢": "in_progress",
    "📋": "planned",
}

# 编号前缀 → 阶段推断
PREFIX_PHASE_MAP = {
    "C": "phase1_2",   # Critical 多来自 Phase 1-2 审查
    "H": "phase1_2",
    "M": "phase2_3",   # Medium 横跨 Phase 2-3
    "L": "phase2_3",
    "A": "phase3",     # Architecture 为 Phase 3 新增
    "T": "phase3",     # Test 为 Phase 3 新增
}

# 编号前缀 → 优先级映射
PREFIX_PRIORITY_MAP = {
    "C": "P0",
    "H": "P1",
    "M": "P2",
    "L": "P3",
    "A": "P2",
    "T": "P3",
}


class WeldSmartMigrator(BaseMigrator):
    """解析 WeldSmart 的 all-issues.md 格式."""

    # 标题行正则: ### C-001: 标题文本 - ✅ 已修复 / ✅ 已完成
    # 支持各种状态符号
    TITLE_RE = re.compile(
        r"^###\s+([A-Z]-\d+):\s+(.+?)\s*-\s*"
        r"(✅\s*(?:已修复|已完成)|❌\s*待修复|⚠️\s*不适用|🟢\s*进行中|📋\s*待规划)"
    )

    def parse(self, source_path: str) -> list[dict]:
        """解析 all-issues.md，返回 issue 字典列表.

        Args:
            source_path: all-issues.md 文件路径

        Returns:
            解析出的 issue 字典列表
        """
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        issues: list[dict] = []
        current_issue: dict | None = None
        # 用于收集多行字段的状态
        current_field: str | None = None
        current_field_lines: list[str] = []

        for line in lines:
            # 尝试匹配标题行
            title_match = self.TITLE_RE.match(line)
            if title_match:
                # 保存之前的条目
                if current_issue is not None:
                    self._flush_field(current_issue, current_field, current_field_lines)
                    issues.append(current_issue)

                issue_id = title_match.group(1)
                title = title_match.group(2).strip()
                status_text = title_match.group(3).strip()
                status = self._parse_status(status_text)

                prefix = issue_id.split("-")[0]
                current_issue = {
                    "id": issue_id,
                    "title": title,
                    "priority": PREFIX_PRIORITY_MAP.get(prefix, "P3"),
                    "status": status,
                    "discovery_date": None,
                    "fix_date": None,
                    "file_path": None,
                    "location": None,
                    "description": None,
                    "impact": None,
                    "fix_plan": None,
                    "estimated_hours": None,
                    "actual_hours": None,
                    "phase": PREFIX_PHASE_MAP.get(prefix),
                    "github_issue_id": None,
                }
                current_field = None
                current_field_lines = []
                continue

            if current_issue is None:
                continue  # 标题之前的内容忽略

            # 分隔线 → 结束当前多行字段
            if line.strip() == "---":
                self._flush_field(current_issue, current_field, current_field_lines)
                current_field = None
                current_field_lines = []
                continue

            # 解析单行字段
            parsed = self._parse_single_line_field(current_issue, line)
            if parsed:
                # 单行字段解析成功，结束之前的多行字段
                self._flush_field(current_issue, current_field, current_field_lines)
                current_field = None
                current_field_lines = []
                continue

            # 检查多行字段的开始标记
            multiline_field = self._detect_multiline_field_start(line)
            if multiline_field:
                # 结束之前的多行字段
                self._flush_field(current_issue, current_field, current_field_lines)
                current_field = multiline_field
                current_field_lines = []
                continue

            # 累积当前多行字段的内容
            if current_field and current_issue is not None:
                current_field_lines.append(line)

        # 处理最后一个条目
        if current_issue is not None:
            self._flush_field(current_issue, current_field, current_field_lines)
            issues.append(current_issue)

        return issues

    # ── 字段解析 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_status(status_text: str) -> str:
        """从状态文本解析状态枚举值."""
        for symbol, status in STATUS_SYMBOL_MAP.items():
            if symbol in status_text:
                return status
        return "pending"

    @staticmethod
    def _parse_single_line_field(issue: dict, line: str) -> bool:
        """尝试解析单行 **字段**: 值 格式.

        Returns:
            True 表示成功解析了单行字段
        """
        stripped = line.strip()

        # **发现日期**: YYYY-MM-DD
        m = re.match(r"\*\*发现日期\*\*:\s*(.+)", stripped)
        if m:
            issue["discovery_date"] = m.group(1).strip()
            return True

        # **文件**: `路径` 或 多个路径
        m = re.match(r"\*\*文件\*\*:\s*(.+)", stripped)
        if m:
            raw = m.group(1).strip()
            # 去除反引号，提取路径
            paths = re.findall(r"`([^`]+)`", raw)
            if paths:
                issue["file_path"] = ", ".join(paths)
            else:
                issue["file_path"] = raw
            return True

        # **位置**: 描述
        m = re.match(r"\*\*位置\*\*:\s*(.+)", stripped)
        if m:
            issue["location"] = m.group(1).strip()
            return True

        # **预计工时**: X 小时 / Xh
        m = re.match(r"\*\*预计工时\*\*:\s*(.+)", stripped)
        if m:
            issue["estimated_hours"] = _parse_hours(m.group(1).strip())
            return True

        # **实际工时**: X 小时 / Xh
        m = re.match(r"\*\*实际工时\*\*:\s*(.+)", stripped)
        if m:
            issue["actual_hours"] = _parse_hours(m.group(1).strip())
            return True

        # **优先级**: PX
        m = re.match(r"\*\*优先级\*\*:\s*(.+)", stripped)
        if m:
            issue["priority"] = m.group(1).strip()
            return True

        # **状态**: ✅ 已修复/已完成 (YYYY-MM-DD) → 提取 fix_date
        m = re.match(r"\*\*状态\*\*:\s*✅\s*(?:已修复|已完成)\s*\((\d{4}-\d{2}-\d{2})\)", stripped)
        if m:
            issue["fix_date"] = m.group(1)
            issue["status"] = "fixed"
            return True

        # **状态**: 其他状态（不带日期）
        m = re.match(r"\*\*状态\*\*:\s*(.+)", stripped)
        if m:
            status_text = m.group(1).strip()
            issue["status"] = WeldSmartMigrator._parse_status(status_text)
            # 尝试提取状态后附带的日期
            dm = re.search(r"\((\d{4}-\d{2}-\d{2})\)", status_text)
            if dm and issue["status"] == "fixed":
                issue["fix_date"] = dm.group(1)
            return True

        # **GitHub Issue**: #XXX
        m = re.match(r"\*\*GitHub Issue\*\*:\s*#?(\d+)", stripped)
        if m:
            issue["github_issue_id"] = int(m.group(1))
            return True

        return False

    @staticmethod
    def _detect_multiline_field_start(line: str) -> Optional[str]:
        """检测多行字段的开始行（如 **问题描述**: 后面没有内容或仅有冒号）.

        Returns:
            字段名称（description/impact/fix_plan），或 None
        """
        stripped = line.strip()
        if stripped == "**问题描述**:" or stripped.startswith("**问题描述**:"):
            # 检查冒号后是否有内容
            after = stripped[len("**问题描述**:"):].strip()
            if not after:
                return "description"
            # 有内容则不是多行字段开始（罕见情况，但处理一致）
            return "description"
        if stripped == "**影响**:" or stripped.startswith("**影响**:"):
            after = stripped[len("**影响**:"):].strip()
            if not after:
                return "impact"
            return "impact"
        if stripped in ("**修复方案**:", "**修复方案(待规划)**:") or stripped.startswith("**修复方案"):
            return "fix_plan"
        return None

    @staticmethod
    def _flush_field(issue: dict, field: Optional[str], lines: list[str]):
        """将累积的多行字段内容写入 issue 字典."""
        if field is None or not lines:
            return

        # 去除首尾空行
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        if not lines:
            return

        text = "\n".join(lines).strip()

        if field == "description":
            issue["description"] = text
        elif field == "impact":
            issue["impact"] = text
        elif field == "fix_plan":
            issue["fix_plan"] = text


# ── 模块级辅助函数 ───────────────────────────────────────────────────────────


def _parse_hours(text: str) -> Optional[float]:
    """解析工时文本为浮点数.

    支持格式: "2 小时", "0.5 小时", "8h", "1 小时（需要 HAL 层支持）"
    """
    # 提取第一个数字（含小数点）
    m = re.match(r"([\d.]+)", text.strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None
