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
    def project_name(self) -> str:
        return self._raw["project"]["name"]

    @property
    def db_path(self) -> str:
        """返回 db_path（相对于 git root，由调用侧负责解析为绝对路径）."""
        return self._raw["project"]["db_path"]

    @property
    def id_format(self) -> str:
        return self._raw["id_rules"]["format"]

    @property
    def prefixes(self) -> dict[str, dict[str, str]]:
        """返回前缀配置映射: { 'C': {'priority': 'P0', 'label': 'Critical'}, ... }"""
        return self._raw["id_rules"]["prefixes"]

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
    def export_output(self) -> str:
        return self._raw.get("export", {}).get("output", "docs/project/all-issues.md")

    # ── 辅助方法 ─────────────────────────────────────────

    def priority_for_prefix(self, prefix: str) -> str | None:
        """根据编号前缀返回优先级."""
        entry = self.prefixes.get(prefix)
        return entry["priority"] if entry else None

    def label_for_prefix(self, prefix: str) -> str | None:
        """根据编号前缀返回标签."""
        entry = self.prefixes.get(prefix)
        return entry["label"] if entry else None

    def is_valid_priority(self, priority: str) -> bool:
        return priority in self.valid_priorities

    def is_valid_status(self, status: str) -> bool:
        return status in self.valid_statuses

    def is_valid_id(self, issue_id: str) -> bool:
        """校验编号格式是否合法（前缀-数字）."""
        parts = issue_id.split("-", 1)
        if len(parts) != 2:
            return False
        prefix, num = parts
        return prefix in self.prefixes and num.isdigit()

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
        if "name" not in self._raw["project"]:
            errors.append("缺少 project.name")
        if "db_path" not in self._raw["project"]:
            errors.append("缺少 project.db_path")

        # id_rules 子键
        if "format" not in self._raw["id_rules"]:
            errors.append("缺少 id_rules.format")
        if "prefixes" not in self._raw["id_rules"]:
            errors.append("缺少 id_rules.prefixes")
        else:
            for prefix, entry in self._raw["id_rules"]["prefixes"].items():
                if "priority" not in entry:
                    errors.append(f"前缀 {prefix} 缺少 priority")
                if "label" not in entry:
                    errors.append(f"前缀 {prefix} 缺少 label")

        # priorities 和 statuses 应为非空列表
        if not isinstance(self._raw["priorities"], list) or len(self._raw["priorities"]) == 0:
            errors.append("priorities 应为非空列表")
        if not isinstance(self._raw["statuses"], list) or len(self._raw["statuses"]) == 0:
            errors.append("statuses 应为非空列表")

        # 前缀中引用的 priority 必须在 priorities 列表中
        if "priorities" in self._raw and "id_rules" in self._raw:
            valid_p = set(self._raw["priorities"])
            for prefix, entry in self._raw.get("id_rules", {}).get("prefixes", {}).items():
                p = entry.get("priority")
                if p and p not in valid_p:
                    errors.append(f"前缀 {prefix} 的 priority '{p}' 不在 priorities 列表中")

        if errors:
            raise ValueError("配置校验失败:\n  " + "\n  ".join(errors))
