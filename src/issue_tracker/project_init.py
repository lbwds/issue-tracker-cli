"""iss-project — 引导式项目配置创建与编辑.

运行方式:
    iss-project          # 在项目目录下运行

行为:
    - 目录中已有 issue-tracker.yaml → 进入编辑菜单
    - 目录中无配置文件              → 引导式创建流程
"""

import os
import re
import sys

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML。请执行: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

from issue_tracker.core.global_config import GlobalConfig
from issue_tracker.core.paths import CONFIG_FILENAME, ensure_directories


# ── 工具函数 ─────────────────────────────────────────────


def _sanitize_name(name: str) -> str:
    """清理名称用于文件名: 保留字母数字和下划线."""
    return re.sub(r'[^\w]', '_', name).strip('_')


def _read_input(prompt: str, default: str = "") -> str:
    """读取用户输入，显示默认值."""
    if default:
        raw = input(f"{prompt} [{default}]: ").strip()
        return raw if raw else default
    return input(f"{prompt}: ").strip()


def _yes_no(prompt: str, default_yes: bool = False) -> bool:
    """是/否确认输入."""
    hint = "[Y/n]" if default_yes else "[y/N]"
    raw = input(f"{prompt} {hint}: ").strip().lower()
    if not raw:
        return default_yes
    return raw in ("y", "yes")


def _edit_list(prompt: str, current: list[str]) -> list[str]:
    """编辑列表字段（逗号分隔输入）."""
    raw = _read_input(prompt, ",".join(current))
    result = [item.strip() for item in raw.split(",") if item.strip()]
    if not result:
        print("  ✗ 列表不能为空，保持原值")
        return current
    return result


# ── YAML 渲染与 IO ───────────────────────────────────────


def render_yaml(data: dict) -> str:
    """生成与项目配置风格一致的 YAML 字符串.

    列表使用流式风格 [a, b, c]，其余块式。
    """
    proj = data.get("project", {})
    gh = data.get("github", {})
    export = data.get("export", {})
    priorities = data.get("priorities", ["P0", "P1", "P2", "P3"])
    statuses = data.get("statuses", ["pending", "in_progress", "planned", "fixed", "n_a"])
    id_format = data.get("id_rules", {}).get("format", "{num:03d}")
    template = gh.get("comment_template", "自动同步: {issue_id} 已修复")

    lines = [
        'project:',
        f'  id: "{proj.get("id", "001")}"',
        f'  name: "{proj.get("name", "Project")}"',
        '',
        'id_rules:',
        f'  format: "{id_format}"',
        '',
        f'priorities: [{", ".join(priorities)}]',
        f'statuses: [{", ".join(statuses)}]',
        '',
        'github:',
        f'  enabled: {"true" if gh.get("enabled", False) else "false"}',
        f'  close_on_fix: {"true" if gh.get("close_on_fix", False) else "false"}',
        f'  comment_template: "{template}"',
    ]
    if gh.get("repo"):
        lines.append(f'  repo: "{gh["repo"]}"')
    lines.extend([
        '',
        'export:',
        f'  output: "{export.get("output", "exports/issues.md")}"',
        '',
    ])
    return "\n".join(lines)


def load_yaml(path: str) -> dict | None:
    """加载 YAML 文件为 dict."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def save_config(path: str, data: dict):
    """写入项目配置文件."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_yaml(data))


# ── 引导创建 ─────────────────────────────────────────────


def guided_create(config_path: str):
    """引导式创建新项目配置."""
    gc = GlobalConfig()

    print()
    print("=" * 50)
    print("  Issue Tracker - 新项目引导配置")
    print("=" * 50)
    print()

    # 项目 ID
    while True:
        project_id = input("项目 ID (纯数字, 如 001): ").strip()
        if project_id and project_id.isdigit():
            break
        print("  ✗ 项目 ID 必须为非空纯数字")

    # 项目名称
    while True:
        project_name = input("项目名称: ").strip()
        if project_name:
            break
        print("  ✗ 项目名称不能为空")

    # 优先级和状态 — 从全局默认值读取
    priorities = _edit_list("优先级列表", gc.default_priorities)
    statuses = _edit_list("状态列表", gc.default_statuses)

    # GitHub
    print()
    gh_enabled = _yes_no("启用 GitHub 同步?")
    gh: dict = {"enabled": gh_enabled, "close_on_fix": False, "comment_template": gc.default_github_comment_template}
    if gh_enabled:
        gh["close_on_fix"] = _yes_no("  修复时自动关闭 Issue?", default_yes=True)
        gh["comment_template"] = _read_input("  关闭评论模板", gc.default_github_comment_template)
        repo = input("  绑定 GitHub 仓库 (owner/name, 可空): ").strip()
        if repo:
            gh["repo"] = repo

    # 导出
    print()
    default_export = f"exports/{_sanitize_name(project_name).lower()}_issues.md"
    export_output = _read_input("导出文件名", default_export)

    # 构建配置
    config_data: dict = {
        "project": {"id": project_id, "name": project_name},
        "priorities": priorities,
        "statuses": statuses,
        "github": gh,
        "export": {"output": export_output},
    }

    # 预览
    print()
    print("-" * 50)
    print("  配置预览")
    print("-" * 50)
    print(render_yaml(config_data))
    print(f"写入路径: {config_path}")

    if os.path.isfile(config_path):
        print("\n  ⚠ 文件已存在，将被覆盖")

    if not _yes_no("\n确认写入?"):
        print("已取消。")
        return

    save_config(config_path, config_data)
    print()
    print(f"✓ 已创建: {config_path}")
    print(f"  验证: issue-tracker stats")


# ── 编辑菜单 ─────────────────────────────────────────────


def edit_menu(config_path: str, data: dict):
    """编辑已有项目配置的菜单."""
    while True:
        proj = data.get("project", {})
        print()
        print("=" * 50)
        print(f"  项目配置编辑 — {proj.get('name', '?')} ({proj.get('id', '?')})")
        print("=" * 50)
        print("  1) 查看当前配置")
        print("  2) 编辑项目信息（ID / 名称）")
        print("  3) 编辑优先级列表")
        print("  4) 编辑状态列表")
        print("  5) 编辑 GitHub 配置")
        print("  6) 编辑导出配置")
        print("  0) 退出")

        choice = input("\n请选择: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            print()
            print(render_yaml(data))
        elif choice == "2":
            _edit_project_info(config_path, data)
        elif choice == "3":
            data["priorities"] = _edit_list("优先级列表", data.get("priorities", []))
            save_config(config_path, data)
            print("  ✓ 已保存")
        elif choice == "4":
            data["statuses"] = _edit_list("状态列表", data.get("statuses", []))
            save_config(config_path, data)
            print("  ✓ 已保存")
        elif choice == "5":
            _edit_github(config_path, data)
        elif choice == "6":
            _edit_export(config_path, data)
        else:
            print("  无效选择")


def _edit_project_info(config_path: str, data: dict):
    """编辑项目 ID 和名称."""
    proj = data.setdefault("project", {})
    while True:
        new_id = _read_input("项目 ID", proj.get("id", ""))
        if new_id and new_id.isdigit():
            break
        print("  ✗ 项目 ID 必须为非空纯数字")
    while True:
        new_name = _read_input("项目名称", proj.get("name", ""))
        if new_name:
            break
        print("  ✗ 项目名称不能为空")
    proj["id"] = new_id
    proj["name"] = new_name
    save_config(config_path, data)
    print("  ✓ 已保存")


def _edit_github(config_path: str, data: dict):
    """GitHub 配置子菜单."""
    gh = data.setdefault("github", {})
    while True:
        print()
        print("  — GitHub 配置 —")
        print(f"    enabled:   {'true' if gh.get('enabled') else 'false'}")
        print(f"    repo:      {gh.get('repo', '(未绑定)')}")
        print(f"    close:     {'true' if gh.get('close_on_fix') else 'false'}")
        print(f"    模板:      {gh.get('comment_template', '(未设置)')}")
        print("  1) 开启/关闭同步")
        print("  2) 编辑绑定仓库")
        print("  3) 开启/关闭修复时自动关闭")
        print("  4) 编辑评论模板")
        print("  0) 返回")

        choice = input("\n  请选择: ").strip()
        if choice == "0":
            return
        elif choice == "1":
            gh["enabled"] = not gh.get("enabled", False)
        elif choice == "2":
            repo = input("  GitHub 仓库 (owner/name, 空清除): ").strip()
            if repo:
                gh["repo"] = repo
            elif "repo" in gh:
                del gh["repo"]
        elif choice == "3":
            gh["close_on_fix"] = not gh.get("close_on_fix", False)
        elif choice == "4":
            gc = GlobalConfig()
            gh["comment_template"] = _read_input(
                "  评论模板", gh.get("comment_template", gc.default_github_comment_template)
            )
        else:
            print("  无效选择")
            continue
        save_config(config_path, data)
        print("  ✓ 已保存")


def _edit_export(config_path: str, data: dict):
    """编辑导出配置."""
    export = data.setdefault("export", {})
    export["output"] = _read_input("导出文件名", export.get("output", "exports/issues.md"))
    save_config(config_path, data)
    print("  ✓ 已保存")


# ── 入口 ────────────────────────────────────────────────


def main_project():
    """iss-project 入口."""
    ensure_directories()

    config_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    if os.path.isfile(config_path):
        data = load_yaml(config_path)
        if data is None:
            print(f"错误: 无法解析 {config_path}", file=sys.stderr)
            sys.exit(1)
        edit_menu(config_path, data)
    else:
        guided_create(config_path)
