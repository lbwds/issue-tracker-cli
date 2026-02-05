"""配置加载与校验."""

import os
import sys
from typing import Any

try:
    import yaml
except ImportError:
    # PyYAML 未安装时提供友好提示
    print("错误: 需要 PyYAML。请执行: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


class Config:
    """项目配置管理类.

    负责加载 config.yaml 并校验配置合法性。
    """

    def __init__(self, config_path: str):
        """加载并校验配置文件.

        Args:
            config_path: config.yaml 的路径

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置内容校验失败
        """
        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            self._raw: dict[str, Any] = yaml.safe_load(f)

        self._config_dir = os.path.dirname(os.path.abspath(config_path))
        self._validate()

    # ── 公开属性 ─────────────────────────────────────────

    @property
    def project_id(self) -> str:
        return self._raw["project"]["id"]

    @property
    def project_name(self) -> str:
        return self._raw["project"]["name"]

    @property
    def id_format(self) -> str:
        return self._raw["id_rules"]["format"]

    @property
    def valid_priorities(self) -> list[str]:
        return self._raw["priorities"]

    @property
    def valid_statuses(self) -> list[str]:
        return self._raw["statuses"]

    @property
    def github_enabled(self) -> bool:
        return self._raw.get("github", {}).get("enabled", False)

    @property
    def github_close_on_fix(self) -> bool:
        return self._raw.get("github", {}).get("close_on_fix", False)

    @property
    def github_comment_template(self) -> str:
        return self._raw.get("github", {}).get("comment_template", "已修复: {issue_id}")

    @property
    def github_repo(self) -> str | None:
        """获取绑定的 GitHub 仓库 (owner/name 格式)."""
        return self._raw.get("github", {}).get("repo")

    @property
    def export_output(self) -> str:
        return self._raw.get("export", {}).get("output", "issues.md")

    # ── 辅助方法 ─────────────────────────────────────────

    def is_valid_priority(self, priority: str) -> bool:
        return priority in self.valid_priorities

    def is_valid_status(self, status: str) -> bool:
        return status in self.valid_statuses

    def is_valid_id(self, issue_id: str) -> bool:
        """校验编号格式是否合法（纯数字）."""
        return issue_id.isdigit()

    # ── 内部校验 ─────────────────────────────────────────

    def _validate(self):
        """校验配置文件结构和内容."""
        errors = []

        # 必须存在的顶级键
        for key in ("project", "id_rules", "priorities", "statuses"):
            if key not in self._raw:
                errors.append(f"缺少必须的配置项: {key}")

        if errors:
            raise ValueError("配置校验失败:\n  " + "\n  ".join(errors))

        # project 子键
        if "id" not in self._raw["project"]:
            errors.append("缺少 project.id (纯数字项目编号)")
        if "name" not in self._raw["project"]:
            errors.append("缺少 project.name")

        # id_rules 子键
        if "format" not in self._raw["id_rules"]:
            errors.append("缺少 id_rules.format")

        # priorities 和 statuses 应为非空列表
        if not isinstance(self._raw["priorities"], list) or len(self._raw["priorities"]) == 0:
            errors.append("priorities 应为非空列表")
        if not isinstance(self._raw["statuses"], list) or len(self._raw["statuses"]) == 0:
            errors.append("statuses 应为非空列表")

        if errors:
            raise ValueError("配置校验失败:\n  " + "\n  ".join(errors))
