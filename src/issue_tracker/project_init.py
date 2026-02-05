"""iss-project — 引导式项目配置创建与编辑.

运行方式:
    iss-project          # 在项目目录下运行

行为:
    - 目录中已有 issue-tracker.yaml → 进入编辑菜单（Submit/Cancel 模式）
    - 目录中无配置文件              → 引导式创建流程
"""

import copy
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
from issue_tracker.core.terminal import (
    C, dim, err, input_line, menu, ok, title_bar, value, wait_key, yes_no,
)


# ── 工具函数 ─────────────────────────────────────────────


def _sanitize_name(name: str) -> str:
    """清理名称用于文件名: 保留字母数字和下划线."""
    return re.sub(r'[^\w]', '_', name).strip('_')


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
    title_bar("Issue Tracker - 新项目引导配置")
    print()

    # 项目 ID
    while True:
        project_id = input_line("项目 ID (纯数字, 如 001)")
        if project_id and project_id.isdigit():
            break
        print("  " + err("✗ 项目 ID 必须为非空纯数字"))

    # 项目名称
    while True:
        project_name = input_line("项目名称")
        if project_name:
            break
        print("  " + err("✗ 项目名称不能为空"))

    # 优先级列表
    raw = input_line("优先级列表", ",".join(gc.default_priorities))
    priorities = [p.strip() for p in (raw or "").split(",") if p.strip()] if raw else gc.default_priorities
    if not priorities:
        priorities = gc.default_priorities

    # 状态列表
    raw = input_line("状态列表", ",".join(gc.default_statuses))
    statuses = [s.strip() for s in (raw or "").split(",") if s.strip()] if raw else gc.default_statuses
    if not statuses:
        statuses = gc.default_statuses

    # GitHub
    print()
    gh_enabled = yes_no("启用 GitHub 同步?", default=False)
    if gh_enabled is None:
        gh_enabled = False

    gh: dict = {"enabled": gh_enabled, "close_on_fix": False, "comment_template": gc.default_github_comment_template}
    if gh_enabled:
        close = yes_no("修复时自动关闭 Issue?", default=True)
        gh["close_on_fix"] = close if close is not None else True
        template = input_line("关闭评论模板", gc.default_github_comment_template)
        if template:
            gh["comment_template"] = template
        repo = input_line("绑定 GitHub 仓库 (owner/name, 可空)")
        if repo:
            gh["repo"] = repo

    # 导出
    print()
    default_export = f"exports/{_sanitize_name(project_name).lower()}_issues.md"
    export_output = input_line("导出文件名", default_export)
    if not export_output:
        export_output = default_export

    # 构建配置
    config_data: dict = {
        "project": {"id": project_id, "name": project_name},
        "priorities": priorities,
        "statuses": statuses,
        "github": gh,
        "export": {"output": export_output},
    }

    # 末尾三项 menu: 查看预览 / 提交创建 / 取消
    IDX_PREVIEW = 0
    IDX_SUBMIT  = 1
    IDX_CANCEL  = 2

    while True:
        choice = menu(
            "新项目配置",
            ["查看预览", f"{ok('✓ 提交创建')}", f"{err('✗ 取消')}"],
            footer="↑↓ 选择  Enter 确认  Esc 取消",
            item_colors={IDX_SUBMIT: C.GREEN, IDX_CANCEL: C.RED},
        )

        if choice is None or choice == IDX_CANCEL:
            print("  " + dim("已取消。"))
            return

        if choice == IDX_PREVIEW:
            print()
            title_bar("配置预览")
            print(render_yaml(config_data))
            print(f"  {dim('写入路径:')} {value(config_path)}")
            if os.path.isfile(config_path):
                print("  " + err("⚠ 文件已存在，将被覆盖"))
            print()
            wait_key()
            continue

        if choice == IDX_SUBMIT:
            save_config(config_path, config_data)
            print("  " + ok(f"✓ 已创建: {config_path}"))
            print(f"  {dim('验证: issue-tracker stats')}")
            return


# ── 编辑菜单 (Submit/Cancel) ─────────────────────────────


def edit_menu(config_path: str, data: dict):
    """编辑已有项目配置的菜单（Submit/Cancel 模式）."""
    original = copy.deepcopy(data)
    working  = copy.deepcopy(data)

    # 菜单索引常量
    IDX_VIEW       = 0
    IDX_PROJ_INFO  = 1
    IDX_PRIORITIES = 2
    IDX_STATUSES   = 3
    IDX_GITHUB     = 4
    IDX_EXPORT     = 5
    IDX_SEP        = 6
    IDX_SUBMIT     = 7
    IDX_CANCEL     = 8

    while True:
        dirty = working != original
        proj  = working.get("project", {})
        title = f"项目配置编辑 — {proj.get('name', '?')} ({proj.get('id', '?')})" + (" ●" if dirty else "")

        gh_label = "开启" if working.get("github", {}).get("enabled") else "关闭"

        options = [
            "查看当前配置",
            f"项目信息: {value(proj.get('name', '?'))} / {value(proj.get('id', '?'))}",
            f"优先级: {value(','.join(working.get('priorities', [])))}",
            f"状态: {value(','.join(working.get('statuses', [])))}",
            f"GitHub: {value(gh_label)}",
            f"导出路径: {value(working.get('export', {}).get('output', 'exports/issues.md'))}",
            "",  # separator
            f"{ok('✓ 提交保存')}",
            f"{err('✗ 取消')}",
        ]

        choice = menu(
            title, options,
            footer="↑↓ 选择  Enter 确认  Esc 返回",
            separators={IDX_SEP},
            item_colors={IDX_SUBMIT: C.GREEN, IDX_CANCEL: C.RED},
        )

        if choice is None or choice == IDX_CANCEL:
            return

        if choice == IDX_SUBMIT:
            save_config(config_path, working)
            print("  " + ok("✓ 已保存"))
            wait_key()
            return

        if choice == IDX_VIEW:
            print()
            title_bar("当前配置")
            print(render_yaml(working))
            wait_key()
        elif choice == IDX_PROJ_INFO:
            _edit_project_info(working)
        elif choice == IDX_PRIORITIES:
            raw = input_line("优先级列表", ",".join(working.get("priorities", [])))
            if raw is not None:
                new = [p.strip() for p in raw.split(",") if p.strip()]
                if new:
                    working["priorities"] = new
                else:
                    print("  " + err("✗ 列表不能为空"))
                    wait_key()
        elif choice == IDX_STATUSES:
            raw = input_line("状态列表", ",".join(working.get("statuses", [])))
            if raw is not None:
                new = [s.strip() for s in raw.split(",") if s.strip()]
                if new:
                    working["statuses"] = new
                else:
                    print("  " + err("✗ 列表不能为空"))
                    wait_key()
        elif choice == IDX_GITHUB:
            _edit_github(working)
        elif choice == IDX_EXPORT:
            _edit_export(working)


def _edit_project_info(data: dict):
    """编辑项目 ID 和名称（仅修改传入的 working copy，不写盘）."""
    proj = data.setdefault("project", {})
    while True:
        new_id = input_line("项目 ID", proj.get("id", ""))
        if new_id is None:
            return
        if new_id and new_id.isdigit():
            break
        print("  " + err("✗ 项目 ID 必须为非空纯数字"))

    while True:
        new_name = input_line("项目名称", proj.get("name", ""))
        if new_name is None:
            return
        if new_name:
            break
        print("  " + err("✗ 项目名称不能为空"))

    proj["id"] = new_id
    proj["name"] = new_name


def _edit_github(data: dict):
    """GitHub 配置子菜单（仅修改传入的 dict，不写盘）."""
    gh = data.setdefault("github", {})

    while True:
        enabled_label  = "开启" if gh.get("enabled") else "关闭"
        close_label    = "开启" if gh.get("close_on_fix") else "关闭"
        repo_label     = gh.get("repo", "(未绑定)")
        template_label = gh.get("comment_template", "(未设置)")

        options = [
            f"[{enabled_label}] GitHub 同步",
            f"[{close_label}] 修复时自动关闭",
            f"绑定仓库: {value(repo_label)}",
            f"评论模板: {value(template_label)}",
        ]

        choice = menu(
            "GitHub 配置",
            options,
            footer="↑↓ 选择  Enter 确认  Esc 返回",
        )

        if choice is None:
            return

        if choice == 0:
            gh["enabled"] = not gh.get("enabled", False)
        elif choice == 1:
            gh["close_on_fix"] = not gh.get("close_on_fix", False)
        elif choice == 2:
            repo = input_line("GitHub 仓库 (owner/name, 空清除)", gh.get("repo", ""))
            if repo is not None:
                if repo:
                    gh["repo"] = repo
                elif "repo" in gh:
                    del gh["repo"]
        elif choice == 3:
            gc = GlobalConfig()
            template = input_line("评论模板", gh.get("comment_template", gc.default_github_comment_template))
            if template is not None:
                gh["comment_template"] = template


def _edit_export(data: dict):
    """编辑导出配置（仅修改传入的 dict，不写盘）."""
    export = data.setdefault("export", {})
    output = input_line("导出文件名", export.get("output", "exports/issues.md"))
    if output is not None:
        export["output"] = output


# ── 入口 ────────────────────────────────────────────────


def main_project():
    """iss-project 入口."""
    ensure_directories()

    config_path = os.path.join(os.getcwd(), CONFIG_FILENAME)
    try:
        if os.path.isfile(config_path):
            data = load_yaml(config_path)
            if data is None:
                print(f"错误: 无法解析 {config_path}", file=sys.stderr)
                sys.exit(1)
            edit_menu(config_path, data)
        else:
            guided_create(config_path)
    except KeyboardInterrupt:
        print()
        print("  " + dim("已取消。"))
