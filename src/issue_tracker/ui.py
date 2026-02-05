"""iss-ui — 分类管理菜单.

运行方式:
    iss-ui               # 在任意目录下运行

功能:
    - 查看当前路径
    - 全局工具配置 (globals.yaml)
    - 版本与环境信息
    - 全局项目管理（查看 / 备份 / 恢复）
    - GitHub 连接配置（检查登录 / 绑定仓库）
    - [动态] 当前项目配置（仅当 cwd 有 issue-tracker.yaml 时显示）
"""

import glob as glob_mod
import os
import subprocess
import sys
import tarfile
from datetime import datetime

from issue_tracker.__version__ import __version__
from issue_tracker.core.global_config import GlobalConfig
from issue_tracker.core.paths import (
    ensure_directories,
    find_config_in_dir,
    get_backups_dir,
    get_config_dir,
    get_data_dir,
)
from issue_tracker.project_init import edit_menu, load_yaml, save_config


# ── 菜单引擎 ─────────────────────────────────────────────


def _menu(title: str, options: list, exit_label: str = "退出") -> None:
    """通用菜单循环.

    options: [(标签, 回调函数), ...]
    选 0 退出当前菜单层。
    """
    while True:
        print()
        print("=" * 50)
        print(f"  {title}")
        print("=" * 50)
        for i, (label, _) in enumerate(options, 1):
            print(f"  {i}) {label}")
        print(f"  0) {exit_label}")

        choice = input("\n请选择: ").strip()
        if choice == "0":
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                options[idx][1]()
            else:
                print("  无效选择")
        except ValueError:
            print("  无效选择")


# ── 查看当前路径 ─────────────────────────────────────────


def _view_paths():
    config_dir = get_config_dir()
    data_dir = get_data_dir()
    backups_dir = get_backups_dir()
    cwd_config = find_config_in_dir(os.getcwd())

    def _flag(path: str, is_dir: bool = False) -> str:
        check = os.path.isdir if is_dir else os.path.isfile
        return "✓" if check(path) else "✗"

    print()
    print("-" * 50)
    print("  当前路径")
    print("-" * 50)
    print(f"  配置目录:     {config_dir}  [{_flag(config_dir, True)}]")
    print(f"  数据目录:     {data_dir}  [{_flag(data_dir, True)}]")
    print(f"  备份目录:     {backups_dir}  [{_flag(backups_dir, True)}]")
    print()
    print(f"  当前工作目录: {os.getcwd()}")
    if cwd_config:
        print(f"  项目配置:     {cwd_config}  [✓]")
    else:
        print(f"  项目配置:     (未找到)")
    print()
    print(f"  XDG_CONFIG_HOME: {os.environ.get('XDG_CONFIG_HOME') or '(未设置，默认 ~/.config)'}")
    print(f"  XDG_DATA_HOME:   {os.environ.get('XDG_DATA_HOME') or '(未设置，默认 ~/.local/share)'}")


# ── 全局工具配置 ─────────────────────────────────────────


def _global_config_menu():
    gc = GlobalConfig()

    def show():
        print()
        print("-" * 50)
        print("  当前全局配置")
        print("-" * 50)
        print(f"  默认优先级:  {gc.default_priorities}")
        print(f"  默认状态:    {gc.default_statuses}")
        print(f"  GitHub 模板: {gc.default_github_comment_template}")
        print(f"  配置文件:    {gc.path}  [{'✓' if os.path.isfile(gc.path) else '✗ 首次写入时自动创建'}]")

    def edit_priorities():
        raw = input(f"  默认优先级 [{','.join(gc.default_priorities)}]: ").strip()
        if not raw:
            print("  未修改"); return
        new = [p.strip() for p in raw.split(",") if p.strip()]
        if new:
            gc.set_default_priorities(new)
            print("  ✓ 已保存")
        else:
            print("  ✗ 列表不能为空")

    def edit_statuses():
        raw = input(f"  默认状态 [{','.join(gc.default_statuses)}]: ").strip()
        if not raw:
            print("  未修改"); return
        new = [s.strip() for s in raw.split(",") if s.strip()]
        if new:
            gc.set_default_statuses(new)
            print("  ✓ 已保存")
        else:
            print("  ✗ 列表不能为空")

    def edit_template():
        raw = input(f"  GitHub 评论模板 [{gc.default_github_comment_template}]: ").strip()
        if raw:
            gc.set_default_github_comment_template(raw)
            print("  ✓ 已保存")
        else:
            print("  未修改")

    _menu("全局工具配置", [
        ("查看当前配置", show),
        ("编辑默认优先级列表", edit_priorities),
        ("编辑默认状态列表", edit_statuses),
        ("编辑 GitHub 评论模板", edit_template),
    ], exit_label="返回")


# ── 版本与环境信息 ───────────────────────────────────────


def _view_env_info():
    print()
    print("-" * 50)
    print("  版本与环境信息")
    print("-" * 50)
    print(f"  issue-tracker 版本: {__version__}")
    print(f"  Python 版本:        {sys.version.split()[0]}")
    print(f"  Python 路径:        {sys.executable}")

    # 安装方式判断
    try:
        import issue_tracker
        pkg_file = getattr(issue_tracker, "__file__", "") or ""
        mode = "pip install" if "site-packages" in pkg_file else "开发模式"
    except Exception:
        mode = "未知"
    print(f"  安装方式:           {mode}")

    # 依赖检查
    print()
    print("  依赖状态:")
    try:
        import yaml  # noqa: F401
        print("    PyYAML:  ✓")
    except ImportError:
        print("    PyYAML:  ✗")
    try:
        r = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=3)
        ver = r.stdout.strip().split("\n")[0] if r.returncode == 0 else "?"
        print(f"    gh CLI:  ✓ ({ver})")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("    gh CLI:  ✗ 未安装或不可用")


# ── 全局项目管理 ─────────────────────────────────────────


def _scan_projects() -> list[dict]:
    """扫描 XDG 配置目录中的所有项目配置."""
    projects = []
    for path in sorted(glob_mod.glob(os.path.join(get_config_dir(), "*.yaml"))):
        if os.path.basename(path) == "globals.yaml":
            continue
        data = load_yaml(path)
        proj = (data or {}).get("project", {})
        projects.append({
            "path": path,
            "id": proj.get("id", "?"),
            "name": proj.get("name", os.path.basename(path)),
        })
    return projects


def _find_db(proj: dict) -> str | None:
    """查找项目对应的数据库文件."""
    matches = glob_mod.glob(os.path.join(get_data_dir(), f"{proj['id']}_*.db"))
    return matches[0] if matches else None


def _project_mgmt_menu():

    def show():
        projects = _scan_projects()
        print()
        if not projects:
            print("  无项目配置。使用 iss-project 在项目目录创建。")
            return
        print("  当前项目列表:")
        for p in projects:
            db = _find_db(p)
            print(f"    [{p['id']}] {p['name']}")
            print(f"         配置:   {p['path']}")
            print(f"         数据库: {db or '(无)'}")

    def backup():
        projects = _scan_projects()
        if not projects:
            print("  无项目可备份。"); return
        print()
        print("  选择项目:")
        for i, p in enumerate(projects, 1):
            print(f"    {i}) [{p['id']}] {p['name']}")
        print("    0) 取消")

        choice = input("\n  请选择: ").strip()
        if choice == "0":
            return
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(projects)):
                print("  无效选择"); return
        except ValueError:
            print("  无效选择"); return

        proj = projects[idx]
        db_path = _find_db(proj)
        if not db_path:
            print(f"  ⚠ 项目 [{proj['id']}] 无数据库文件，仅备份配置。")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{proj['id']}_{proj['name']}_{timestamp}.tar.gz"
        backup_path = os.path.join(get_backups_dir(), backup_name)

        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(proj["path"], arcname=os.path.basename(proj["path"]))
            if db_path:
                tar.add(db_path, arcname=os.path.basename(db_path))

        print(f"  ✓ 已备份: {backup_path}")

    def restore():
        backups = sorted(glob_mod.glob(os.path.join(get_backups_dir(), "*.tar.gz")))
        if not backups:
            print("  无备份文件。"); return
        print()
        print("  可用备份:")
        for i, bp in enumerate(backups, 1):
            print(f"    {i}) {os.path.basename(bp)}")
        print("    0) 取消")

        choice = input("\n  请选择: ").strip()
        if choice == "0":
            return
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(backups)):
                print("  无效选择"); return
        except ValueError:
            print("  无效选择"); return

        backup_path = backups[idx]
        with tarfile.open(backup_path, "r:gz") as tar:
            members = tar.getnames()
            print(f"\n  备份内容:")
            for m in members:
                dest = get_config_dir() if m.endswith(".yaml") else get_data_dir()
                print(f"    → {os.path.join(dest, m)}")

            if input("\n  确认恢复? [y/N]: ").strip().lower() not in ("y", "yes"):
                print("  已取消。"); return

            for member in tar.getmembers():
                dest_dir = get_config_dir() if member.name.endswith(".yaml") else get_data_dir()
                f = tar.extractfile(member)
                if f:
                    dest_path = os.path.join(dest_dir, member.name)
                    with open(dest_path, "wb") as out:
                        out.write(f.read())
                    print(f"  ✓ {dest_path}")

    _menu("全局项目管理", [
        ("查看所有项目", show),
        ("备份项目", backup),
        ("恢复项目", restore),
    ], exit_label="返回")


# ── GitHub 连接配置 ──────────────────────────────────────


def _github_config_menu():

    def check_login():
        print()
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=5,
            )
            # gh auth status 输出到 stderr
            output = (result.stdout + result.stderr).strip()
            for line in output.split("\n"):
                print(f"  {line}")
        except FileNotFoundError:
            print("  ✗ gh CLI 未安装。请访问 https://cli.github.com/ 下载安装。")
        except subprocess.TimeoutExpired:
            print("  ✗ 超时。")

    def bind_repo():
        # 构建目标项目列表
        targets: list[tuple[str, str]] = []
        cwd_config = find_config_in_dir(os.getcwd())
        if cwd_config:
            targets.append(("当前目录项目", cwd_config))
        for p in _scan_projects():
            if cwd_config and os.path.abspath(p["path"]) == os.path.abspath(cwd_config):
                continue
            targets.append((f"[{p['id']}] {p['name']}", p["path"]))

        if not targets:
            print("  无项目可绑定。先使用 iss-project 创建项目。"); return

        print()
        print("  选择目标项目:")
        for i, (label, _) in enumerate(targets, 1):
            print(f"    {i}) {label}")
        print("    0) 取消")

        choice = input("\n  请选择: ").strip()
        if choice == "0":
            return
        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(targets)):
                print("  无效选择"); return
        except ValueError:
            print("  无效选择"); return

        config_path = targets[idx][1]

        # 获取仓库列表
        print()
        try:
            result = subprocess.run(
                ["gh", "repo", "list", "--limit", "30",
                 "--json", "nameWithOwner", "-q", ".[].nameWithOwner"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                print("  ✗ 无法获取仓库列表。请检查 gh 登录状态。"); return
            repos = [r.strip() for r in result.stdout.strip().split("\n") if r.strip()]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("  ✗ gh CLI 不可用或超时。"); return

        if not repos:
            print("  无可用仓库。"); return

        print("  可用仓库:")
        for i, repo in enumerate(repos, 1):
            print(f"    {i}) {repo}")
        print("    0) 取消 / 手动输入")

        choice = input("\n  请选择: ").strip()
        if choice == "0":
            repo_name = input("  手动输入仓库 (owner/name): ").strip()
            if not repo_name:
                print("  已取消。"); return
        else:
            try:
                idx = int(choice) - 1
                if not (0 <= idx < len(repos)):
                    print("  无效选择"); return
                repo_name = repos[idx]
            except ValueError:
                print("  无效选择"); return

        # 写入配置
        data = load_yaml(config_path)
        if data is None:
            print(f"  ✗ 无法读取 {config_path}"); return
        data.setdefault("github", {})["repo"] = repo_name
        save_config(config_path, data)
        print(f"  ✓ 已绑定 {repo_name} → {os.path.basename(config_path)}")

    _menu("GitHub 连接配置", [
        ("检查登录状态", check_login),
        ("绑定仓库到项目", bind_repo),
    ], exit_label="返回")


# ── 主入口 ───────────────────────────────────────────────


def main_ui():
    """iss-ui 入口."""
    ensure_directories()

    options: list = [
        ("查看当前路径", _view_paths),
        ("全局工具配置", _global_config_menu),
        ("版本与环境信息", _view_env_info),
        ("全局项目管理", _project_mgmt_menu),
        ("GitHub 连接配置", _github_config_menu),
    ]

    # 动态添加: 当前目录有项目配置时显示编辑菜单
    cwd_config = find_config_in_dir(os.getcwd())
    if cwd_config:
        def _current_project():
            data = load_yaml(cwd_config)
            if data is None:
                print(f"  ✗ 无法解析 {cwd_config}"); return
            edit_menu(cwd_config, data)
        options.append(("当前项目配置", _current_project))

    _menu("Issue Tracker - 管理菜单", options)
