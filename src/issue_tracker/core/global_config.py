"""全局工具配置管理.

全局配置文件: $XDG_CONFIG_HOME/issue-tracker/globals.yaml
存储工具级别的默认值，供 iss-project 创建新项目时使用。
"""

import os
import sys

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML。请执行: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

from issue_tracker.core.paths import get_config_dir

_GLOBALS_FILENAME = "globals.yaml"

_BUILTIN_DEFAULTS = {
    "priorities": ["P0", "P1", "P2", "P3"],
    "statuses": ["pending", "in_progress", "planned", "fixed", "n_a"],
    "github_comment_template": "自动同步: {issue_id} 已修复",
}


class GlobalConfig:
    """全局配置加载与保存.

    读取优先级: globals.yaml 中的值 > 内置默认值。
    首次写入时自动创建 globals.yaml。
    """

    def __init__(self):
        self.path = os.path.join(get_config_dir(), _GLOBALS_FILENAME)
        self._data: dict = self._load()

    # ── 内部 ─────────────────────────────────────────

    def _load(self) -> dict:
        if os.path.isfile(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def _defaults(self) -> dict:
        return self._data.get("defaults", {})

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)

    # ── 默认值读取 ────────────────────────────────────

    @property
    def default_priorities(self) -> list[str]:
        return self._defaults().get("priorities", _BUILTIN_DEFAULTS["priorities"])

    @property
    def default_statuses(self) -> list[str]:
        return self._defaults().get("statuses", _BUILTIN_DEFAULTS["statuses"])

    @property
    def default_github_comment_template(self) -> str:
        return self._defaults().get("github_comment_template", _BUILTIN_DEFAULTS["github_comment_template"])

    # ── 默认值写入 ────────────────────────────────────

    def set_default_priorities(self, priorities: list[str]):
        self._data.setdefault("defaults", {})["priorities"] = priorities
        self._save()

    def set_default_statuses(self, statuses: list[str]):
        self._data.setdefault("defaults", {})["statuses"] = statuses
        self._save()

    def set_default_github_comment_template(self, template: str):
        self._data.setdefault("defaults", {})["github_comment_template"] = template
        self._save()
