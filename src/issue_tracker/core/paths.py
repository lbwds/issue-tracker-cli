"""公共路径工具 — 按 XDG Base Directory Specification 解析目录."""

import os

# 项目级配置文件名
CONFIG_FILENAME = "issue-tracker.yaml"


def get_config_dir() -> str:
    """项目配置目录: $XDG_CONFIG_HOME/issue-tracker (默认 ~/.config/issue-tracker)."""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, "issue-tracker")


def get_data_dir() -> str:
    """数据存储目录: $XDG_DATA_HOME/issue-tracker (默认 ~/.local/share/issue-tracker)."""
    base = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(base, "issue-tracker")


def get_backups_dir() -> str:
    """备份目录: $XDG_DATA_HOME/issue-tracker/backups."""
    return os.path.join(get_data_dir(), "backups")


def ensure_directories() -> None:
    """确保必要的目录存在.

    按 XDG Base Directory Specification 创建:
    - $XDG_CONFIG_HOME/issue-tracker/         : 项目配置文件
    - $XDG_DATA_HOME/issue-tracker/           : 数据库文件
    - $XDG_DATA_HOME/issue-tracker/exports/   : 导出文件
    - $XDG_DATA_HOME/issue-tracker/backups/   : 项目备份
    """
    for d in (get_config_dir(), get_data_dir(),
              os.path.join(get_data_dir(), "exports"), get_backups_dir()):
        os.makedirs(d, exist_ok=True)


def find_config_in_dir(directory: str) -> str | None:
    """在指定目录中查找 issue-tracker.yaml."""
    path = os.path.join(directory, CONFIG_FILENAME)
    return path if os.path.isfile(path) else None
