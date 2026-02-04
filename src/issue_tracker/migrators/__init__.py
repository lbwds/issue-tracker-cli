"""迁移插件基类定义."""

from abc import ABC, abstractmethod


class BaseMigrator(ABC):
    """迁移插件抽象基类.

    每个项目实现一个子类，负责解析项目特定的源文件格式。
    """

    @abstractmethod
    def parse(self, source_path: str) -> list[dict]:
        """解析源文件，返回 issue 字典列表.

        Args:
            source_path: 源文件路径

        Returns:
            issue 字典列表，每个字典的键对应 issues 表字段名
        """
        raise NotImplementedError

    def validate(self, issues: list[dict]) -> list[str]:
        """数据完整性校验，返回警告信息列表.

        Args:
            issues: 待校验的 issue 列表

        Returns:
            警告信息列表（空列表表示无问题）
        """
        warnings = []
        seen_ids = set()
        for issue in issues:
            issue_id = issue.get("id", "<missing>")

            # 检查必填字段
            for required in ("id", "title", "priority", "status", "discovery_date"):
                if not issue.get(required):
                    warnings.append(f"[{issue_id}] 缺少必填字段: {required}")

            # 检查重复编号
            if issue_id in seen_ids:
                warnings.append(f"[{issue_id}] 编号重复")
            seen_ids.add(issue_id)

        return warnings
