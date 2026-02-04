"""Issue 数据模型定义."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Issue:
    """单个问题条目的数据类."""

    id: str                                  # 编号: C-001, M-037 等
    title: str                               # 标题
    priority: str                            # 优先级: P0/P1/P2/P3
    status: str                              # 状态: pending/in_progress/planned/fixed/n_a
    discovery_date: str                      # 发现日期 YYYY-MM-DD
    fix_date: Optional[str] = None           # 修复日期 YYYY-MM-DD
    file_path: Optional[str] = None          # 文件路径（多个逗号分隔）
    location: Optional[str] = None           # 位置描述（行号等）
    description: Optional[str] = None        # 问题描述
    impact: Optional[str] = None             # 影响
    fix_plan: Optional[str] = None           # 修复方案
    estimated_hours: Optional[float] = None  # 预计工时
    actual_hours: Optional[float] = None     # 实际工时
    phase: Optional[str] = None              # 所属阶段
    github_issue_id: Optional[int] = None    # 关联的 GitHub Issue 编号
    created_at: Optional[str] = None         # 创建时间
    updated_at: Optional[str] = None         # 更新时间

    def to_dict(self) -> dict:
        """转换为字典（用于数据库插入）."""
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "discovery_date": self.discovery_date,
            "fix_date": self.fix_date,
            "file_path": self.file_path,
            "location": self.location,
            "description": self.description,
            "impact": self.impact,
            "fix_plan": self.fix_plan,
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "phase": self.phase,
            "github_issue_id": self.github_issue_id,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Issue":
        """从数据库行构造 Issue 对象."""
        return cls(
            id=row["id"],
            title=row["title"],
            priority=row["priority"],
            status=row["status"],
            discovery_date=row["discovery_date"],
            fix_date=row.get("fix_date"),
            file_path=row.get("file_path"),
            location=row.get("location"),
            description=row.get("description"),
            impact=row.get("impact"),
            fix_plan=row.get("fix_plan"),
            estimated_hours=row.get("estimated_hours"),
            actual_hours=row.get("actual_hours"),
            phase=row.get("phase"),
            github_issue_id=row.get("github_issue_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class GithubSyncLogEntry:
    """GitHub 同步日志条目."""

    id: int
    issue_id: str
    github_issue_id: int
    action: str          # close / comment
    status: str          # success / failed
    error_msg: Optional[str] = None
    synced_at: Optional[str] = None
