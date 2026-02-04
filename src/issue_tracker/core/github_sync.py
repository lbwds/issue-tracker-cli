"""GitHub 单向同步逻辑.

数据库中 status=fixed 的条目 → 自动关闭对应的 GitHub Issue。
依赖 gh CLI（GitHub CLI），需要提前登录认证。
"""

import subprocess
import sys

from .config import Config
from .database import Database
from .model import Issue


class GithubSync:
    """GitHub 单向同步器."""

    def __init__(self, config: Config, db: Database):
        self._config = config
        self._db = db

    def sync(self, dry_run: bool = False) -> dict:
        """执行同步.

        Args:
            dry_run: True 时仅打印待同步列表，不实际执行

        Returns:
            同步结果汇总: { 'pending': int, 'success': int, 'failed': int, 'details': list }
        """
        if not self._config.github_enabled:
            print("GitHub 同步已禁用（config.yaml github.enabled = false）")
            return {"pending": 0, "success": 0, "failed": 0, "details": []}

        if not self._config.github_close_on_fix:
            print("GitHub close_on_fix 已禁用")
            return {"pending": 0, "success": 0, "failed": 0, "details": []}

        pending_issues = self._db.get_pending_github_sync()

        if not pending_issues:
            print("无待同步的条目。")
            return {"pending": 0, "success": 0, "failed": 0, "details": []}

        print(f"待同步条目: {len(pending_issues)} 条")
        print("-" * 60)

        result = {"pending": len(pending_issues), "success": 0, "failed": 0, "details": []}

        for issue in pending_issues:
            gh_id = issue.github_issue_id
            comment = self._config.github_comment_template.format(issue_id=issue.id)
            print(f"  {issue.id} → GitHub Issue #{gh_id} (标题: {issue.title})")

            if dry_run:
                print(f"    [dry-run] 将执行: gh issue close {gh_id} --comment \"{comment}\"")
                result["details"].append({"issue_id": issue.id, "action": "dry-run"})
                continue

            # 实际执行 gh 命令
            success, error_msg = self._close_github_issue(gh_id, comment)

            if success:
                self._db.log_github_sync(issue.id, gh_id, "close", "success")
                result["success"] += 1
                result["details"].append({"issue_id": issue.id, "action": "close", "status": "success"})
                print(f"    ✓ 已关闭 GitHub Issue #{gh_id}")
            else:
                self._db.log_github_sync(issue.id, gh_id, "close", "failed", error_msg)
                result["failed"] += 1
                result["details"].append({"issue_id": issue.id, "action": "close", "status": "failed", "error": error_msg})
                print(f"    ✗ 关闭失败: {error_msg}", file=sys.stderr)

        print("-" * 60)
        print(f"同步完成: {result['success']} 成功, {result['failed']} 失败")
        return result

    @staticmethod
    def _close_github_issue(github_issue_id: int, comment: str) -> tuple[bool, str | None]:
        """调用 gh CLI 关闭 GitHub Issue.

        Args:
            github_issue_id: GitHub Issue 编号
            comment: 关闭时附加的评论

        Returns:
            (成功标志, 错误信息)
        """
        try:
            subprocess.run(
                ["gh", "issue", "close", str(github_issue_id), "--comment", comment],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return True, None
        except subprocess.CalledProcessError as e:
            return False, f"gh 命令失败: {e.stderr.strip()}"
        except FileNotFoundError:
            return False, "gh CLI 未安装或未在 PATH 中"
        except subprocess.TimeoutExpired:
            return False, "gh 命令超时 (30s)"
