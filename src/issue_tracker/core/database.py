"""SQLite 数据库 CRUD 封装层."""

import sqlite3
from typing import Optional

from .model import Issue


# ── Schema SQL ───────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS issues (
    id              TEXT    PRIMARY KEY,
    title           TEXT    NOT NULL,
    priority        TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    discovery_date  TEXT    NOT NULL,
    fix_date        TEXT,
    file_path       TEXT,
    location        TEXT,
    description     TEXT,
    impact          TEXT,
    fix_plan        TEXT,
    estimated_hours REAL,
    actual_hours    REAL,
    phase           TEXT,
    github_issue_id INTEGER,
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS github_sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id        TEXT    NOT NULL,
    github_issue_id INTEGER NOT NULL,
    action          TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    error_msg       TEXT,
    synced_at       TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (issue_id) REFERENCES issues(id)
);

CREATE INDEX IF NOT EXISTS idx_priority        ON issues(priority);
CREATE INDEX IF NOT EXISTS idx_status          ON issues(status);
CREATE INDEX IF NOT EXISTS idx_discovery_date  ON issues(discovery_date);
CREATE INDEX IF NOT EXISTS idx_github          ON issues(github_issue_id);

CREATE VIEW IF NOT EXISTS v_pending AS
    SELECT id, title, priority, status, discovery_date, file_path
    FROM issues
    WHERE status IN ('pending', 'in_progress', 'planned')
    ORDER BY priority, discovery_date;

CREATE VIEW IF NOT EXISTS v_summary AS
    SELECT id, title, priority, status, discovery_date, fix_date, github_issue_id
    FROM issues
    ORDER BY id;
"""


class Database:
    """SQLite 数据库操作封装.

    提供 Issue 表的 CRUD 方法和统计查询。
    """

    def __init__(self, db_path: str):
        """初始化数据库连接并创建表.

        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_schema()

    def _init_schema(self):
        """执行 schema SQL 建表."""
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self):
        """关闭数据库连接."""
        self._conn.close()

    # ── Issue CRUD ───────────────────────────────────────────────────────────

    def add_issue(self, issue: Issue) -> None:
        """插入新问题条目.

        Args:
            issue: Issue 对象

        Raises:
            sqlite3.IntegrityError: 编号已存在
        """
        d = issue.to_dict()
        self._conn.execute(
            """INSERT INTO issues
               (id, title, priority, status, discovery_date, fix_date, file_path,
                location, description, impact, fix_plan, estimated_hours,
                actual_hours, phase, github_issue_id)
               VALUES (:id, :title, :priority, :status, :discovery_date,
                       :fix_date, :file_path, :location, :description, :impact,
                       :fix_plan, :estimated_hours, :actual_hours, :phase,
                       :github_issue_id)""",
            d,
        )
        self._conn.commit()

    def upsert_issue(self, issue: Issue) -> None:
        """插入或更新问题条目（迁移时使用）.

        Args:
            issue: Issue 对象
        """
        d = issue.to_dict()
        self._conn.execute(
            """INSERT OR REPLACE INTO issues
               (id, title, priority, status, discovery_date, fix_date, file_path,
                location, description, impact, fix_plan, estimated_hours,
                actual_hours, phase, github_issue_id)
               VALUES (:id, :title, :priority, :status, :discovery_date,
                       :fix_date, :file_path, :location, :description, :impact,
                       :fix_plan, :estimated_hours, :actual_hours, :phase,
                       :github_issue_id)""",
            d,
        )
        self._conn.commit()

    def get_issue(self, issue_id: str) -> Optional[Issue]:
        """根据编号查询单条问题.

        Args:
            issue_id: 问题编号

        Returns:
            Issue 对象，不存在时返回 None
        """
        row = self._conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()
        if row is None:
            return None
        return Issue.from_row(dict(row))

    def update_issue(self, issue_id: str, **kwargs) -> bool:
        """更新问题条目的指定字段.

        Args:
            issue_id: 问题编号
            **kwargs: 待更新的字段及值

        Returns:
            True 表示更新成功（存在该编号），False 表示编号不存在
        """
        if not kwargs:
            return False

        # 白名单过滤，仅允许更新已知字段
        allowed = {
            "title", "priority", "status", "discovery_date", "fix_date",
            "file_path", "location", "description", "impact", "fix_plan",
            "estimated_hours", "actual_hours", "phase", "github_issue_id",
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        if not filtered:
            return False

        # 自动更新 updated_at
        filtered["updated_at"] = "datetime('now')"

        set_clauses = []
        values = []
        for k, v in filtered.items():
            if k == "updated_at":
                set_clauses.append(f"{k} = datetime('now')")
            else:
                set_clauses.append(f"{k} = ?")
                values.append(v)
        values.append(issue_id)

        sql = f"UPDATE issues SET {', '.join(set_clauses)} WHERE id = ?"
        cursor = self._conn.execute(sql, values)
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_issue(self, issue_id: str) -> bool:
        """删除问题条目.

        Returns:
            True 表示删除成功
        """
        cursor = self._conn.execute("DELETE FROM issues WHERE id = ?", (issue_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def issue_exists(self, issue_id: str) -> bool:
        """检查编号是否已存在."""
        row = self._conn.execute(
            "SELECT 1 FROM issues WHERE id = ?", (issue_id,)
        ).fetchone()
        return row is not None

    def get_next_id(self) -> int:
        """返回下一个可用的序号.

        查询当前数据库中所有纯数字 ID 的最大值，返回 max+1。
        数据库为空或无纯数字 ID 时返回 1。
        """
        row = self._conn.execute(
            "SELECT MAX(CAST(id AS INTEGER)) as max_id FROM issues WHERE id GLOB '[0-9]*'"
        ).fetchone()
        return (row["max_id"] or 0) + 1

    # ── 查询 ─────────────────────────────────────────────────────────────────

    def query_issues(
        self,
        *,
        issue_id: Optional[str] = None,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        phase: Optional[str] = None,
        file_glob: Optional[str] = None,
        github_issue_id: Optional[int] = None,
    ) -> list[Issue]:
        """多条件过滤查询.

        Args:
            issue_id: 精确匹配编号
            priority: 优先级过滤
            status: 状态过滤
            phase: 阶段过滤
            file_glob: 文件路径 glob 匹配（如 src/hal/*）
            github_issue_id: GitHub Issue 编号过滤

        Returns:
            匹配的 Issue 列表，按 priority ASC, discovery_date ASC 排序
        """
        conditions = []
        params: list = []

        if issue_id:
            conditions.append("id = ?")
            params.append(issue_id)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if phase:
            conditions.append("phase = ?")
            params.append(phase)
        if github_issue_id is not None:
            conditions.append("github_issue_id = ?")
            params.append(github_issue_id)
        if file_glob:
            # 将 glob 转换为 LIKE 模式: src/hal/* → src/hal/%
            like_pattern = file_glob.replace("*", "%").replace("?", "_")
            # file_path 可能是逗号分隔的多个路径，逐一检查
            conditions.append("file_path LIKE ?")
            params.append(f"%{like_pattern}%")

        where_sql = " AND ".join(conditions) if conditions else "1=1"
        sql = f"""
            SELECT * FROM issues
            WHERE {where_sql}
            ORDER BY priority ASC, discovery_date ASC
        """
        rows = self._conn.execute(sql, params).fetchall()
        return [Issue.from_row(dict(r)) for r in rows]

    # ── 统计 ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """返回问题统计数据.

        Returns:
            包含总数、按优先级统计、按状态统计的字典
        """
        total = self._conn.execute("SELECT COUNT(*) as cnt FROM issues").fetchone()["cnt"]

        by_priority = {}
        for row in self._conn.execute(
            "SELECT priority, COUNT(*) as cnt FROM issues GROUP BY priority ORDER BY priority"
        ).fetchall():
            by_priority[row["priority"]] = row["cnt"]

        by_status = {}
        for row in self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM issues GROUP BY status ORDER BY status"
        ).fetchall():
            by_status[row["status"]] = row["cnt"]

        # 按优先级分组的固定/待处理统计
        by_priority_detail = {}
        for row in self._conn.execute(
            """SELECT priority, status, COUNT(*) as cnt
               FROM issues
               GROUP BY priority, status
               ORDER BY priority, status"""
        ).fetchall():
            p = row["priority"]
            if p not in by_priority_detail:
                by_priority_detail[p] = {}
            by_priority_detail[p][row["status"]] = row["cnt"]

        return {
            "total": total,
            "by_priority": by_priority,
            "by_status": by_status,
            "by_priority_detail": by_priority_detail,
        }

    # ── GitHub 同步相关 ──────────────────────────────────────────────────────

    def get_pending_github_sync(self) -> list[Issue]:
        """查询待 GitHub 同步的条目.

        条件: status=fixed AND github_issue_id IS NOT NULL
              且在 github_sync_log 中无 action='close' + status='success' 的记录

        Returns:
            待同步的 Issue 列表
        """
        sql = """
            SELECT i.* FROM issues i
            WHERE i.status = 'fixed'
              AND i.github_issue_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM github_sync_log g
                  WHERE g.issue_id = i.id
                    AND g.action = 'close'
                    AND g.status = 'success'
              )
        """
        rows = self._conn.execute(sql).fetchall()
        return [Issue.from_row(dict(r)) for r in rows]

    def log_github_sync(
        self,
        issue_id: str,
        github_issue_id: int,
        action: str,
        status: str,
        error_msg: Optional[str] = None,
    ) -> None:
        """记录 GitHub 同步日志.

        Args:
            issue_id: 问题编号
            github_issue_id: GitHub Issue 编号
            action: 操作类型 (close/comment)
            status: 执行状态 (success/failed)
            error_msg: 错误信息（仅 failed 时有）
        """
        self._conn.execute(
            """INSERT INTO github_sync_log
               (issue_id, github_issue_id, action, status, error_msg)
               VALUES (?, ?, ?, ?, ?)""",
            (issue_id, github_issue_id, action, status, error_msg),
        )
        self._conn.commit()
