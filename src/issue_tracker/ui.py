"""iss-ui — 分类管理菜单.

运行方式:
    iss-ui               # 在任意目录下运行

功能:
    - 查看当前路径
    - 全局工具配置 (globals.yaml)  — Submit/Cancel 模式
    - 版本与环境信息
    - 全局项目管理（查看 / 备份 / 恢复）
    - GitHub 连接配置（检查登录 / 绑定仓库）
    - [动态] 当前项目配置（仅当 cwd 有 issue-tracker.yaml 时显示）
"""

import copy
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
from issue_tracker.core.terminal import (
    C, banner_block, dim, err, input_line, label, menu, ok, section_header,
    value, wait_key, warn, yes_no,
)
from issue_tracker.project_init import edit_menu, load_yaml, save_config, _sanitize_name


def _banner():
    """返回当前版本的装饰行列表（作为 menu header 传入）."""
    return banner_block(__version__)


# ── 查看当前路径 ─────────────────────────────────────────


def _view_paths():
    config_dir = get_config_dir()
    data_dir = get_data_dir()
    backups_dir = get_backups_dir()
    cwd_config = find_config_in_dir(os.getcwd())

    def _flag(path: str, is_dir: bool = False) -> str:
        check = os.path.isdir if is_dir else os.path.isfile
        return ok("✓") if check(path) else err("✗")

    print()
    section_header("当前路径")
    print(f"  {label('配置目录:')}     {value(config_dir)}  [{_flag(config_dir, True)}]")
    print(f"  {label('数据目录:')}     {value(data_dir)}  [{_flag(data_dir, True)}]")
    print(f"  {label('备份目录:')}     {value(backups_dir)}  [{_flag(backups_dir, True)}]")
    print()
    print(f"  {label('当前工作目录:')} {value(os.getcwd())}")
    if cwd_config:
        print(f"  {label('项目配置:')}     {value(cwd_config)}  [{ok('✓')}]")
    else:
        print(f"  {label('项目配置:')}     {dim('(未找到)')}")
    print()
    print(f"  {label('XDG_CONFIG_HOME:')} {value(os.environ.get('XDG_CONFIG_HOME') or '(未设置，默认 ~/.config)')}")
    print(f"  {label('XDG_DATA_HOME:')}   {value(os.environ.get('XDG_DATA_HOME') or '(未设置，默认 ~/.local/share)')}")
    print()
    wait_key()


# ── 全局工具配置 (Submit/Cancel) ──────────────────────────


def _global_config_menu():
    gc = GlobalConfig()

    original = {
        "priorities": list(gc.default_priorities),
        "statuses": list(gc.default_statuses),
        "template": gc.default_github_comment_template,
    }
    working = copy.deepcopy(original)

    # 菜单索引常量
    IDX_PRIORITIES = 0
    IDX_STATUSES   = 1
    IDX_TEMPLATE   = 2
    IDX_SEP        = 3
    IDX_SUBMIT     = 4
    IDX_CANCEL     = 5

    while True:
        dirty = working != original
        title = "全局工具配置" + (" ●" if dirty else "")

        options = [
            f"默认优先级: {value(','.join(working['priorities']))}",
            f"默认状态:   {value(','.join(working['statuses']))}",
            f"GitHub 模板: {value(working['template'])}",
            "",  # separator
            f"{ok('✓ 提交保存')}",
            f"{err('✗ 取消')}",
        ]

        choice = menu(
            title, options,
            header=_banner(),
            footer="↑↓ 选择  Enter 确认  Esc 返回",
            separators={IDX_SEP},
            item_colors={IDX_SUBMIT: C.GREEN, IDX_CANCEL: C.RED},
        )

        if choice is None or choice == IDX_CANCEL:
            return

        if choice == IDX_SUBMIT:
            # 写盘
            if working["priorities"] != original["priorities"]:
                gc.set_default_priorities(working["priorities"])
            if working["statuses"] != original["statuses"]:
                gc.set_default_statuses(working["statuses"])
            if working["template"] != original["template"]:
                gc.set_default_github_comment_template(working["template"])
            print("  " + ok("✓ 已保存"))
            wait_key()
            return

        # 编辑项
        if choice == IDX_PRIORITIES:
            raw = input_line("默认优先级", ",".join(working["priorities"]))
            if raw is not None:
                new = [p.strip() for p in raw.split(",") if p.strip()]
                if new:
                    working["priorities"] = new
                else:
                    print("  " + err("✗ 列表不能为空"))
                    wait_key()
        elif choice == IDX_STATUSES:
            raw = input_line("默认状态", ",".join(working["statuses"]))
            if raw is not None:
                new = [s.strip() for s in raw.split(",") if s.strip()]
                if new:
                    working["statuses"] = new
                else:
                    print("  " + err("✗ 列表不能为空"))
                    wait_key()
        elif choice == IDX_TEMPLATE:
            raw = input_line("GitHub 评论模板", working["template"])
            if raw is not None:
                working["template"] = raw


# ── 版本与环境信息 ───────────────────────────────────────


def _view_env_info():
    print()
    section_header("版本与环境信息")
    print(f"  {label('issue-tracker 版本:')} {value(__version__)}")
    print(f"  {label('Python 版本:')}        {value(sys.version.split()[0])}")
    print(f"  {label('Python 路径:')}        {value(sys.executable)}")

    # 安装方式判断
    try:
        import issue_tracker
        pkg_file = getattr(issue_tracker, "__file__", "") or ""
        mode = "pip install" if "site-packages" in pkg_file else "开发模式"
    except Exception:
        mode = "未知"
    print(f"  {label('安装方式:')}           {value(mode)}")

    # 依赖检查
    print()
    print(f"  {label('依赖状态:')}")
    try:
        import yaml  # noqa: F401
        print(f"    {label('PyYAML:')}  {ok('✓')}")
    except ImportError:
        print(f"    {label('PyYAML:')}  {err('✗')}")
    try:
        r = subprocess.run(["gh", "--version"], capture_output=True, text=True, timeout=3)
        ver = r.stdout.strip().split("\n")[0] if r.returncode == 0 else "?"
        print(f"    {label('gh CLI:')}  {ok('✓')} ({ver})")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(f"    {label('gh CLI:')}  {err('✗ 未安装或不可用')}")
    print()
    wait_key()


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

    def _show_projects():
        projects = _scan_projects()
        print()
        if not projects:
            print("  " + dim("无项目配置。使用 iss-project 在项目目录创建。"))
            wait_key()
            return
        section_header("当前项目列表")
        for p in projects:
            db = _find_db(p)
            pid = p["id"]
            pname = p["name"]
            print(f"  {label('[' + pid + ']')} {value(pname)}")
            print(f"       {label('配置:')}   {value(p['path'])}")
            print(f"       {label('数据库:')} {value(db) if db else dim('(无)')}")
        print()
        wait_key()

    def _backup():
        projects = _scan_projects()
        if not projects:
            print("  " + dim("无项目可备份。"))
            wait_key()
            return

        proj_options = [f"[{p['id']}] {p['name']}" for p in projects]
        choice = menu("选择项目备份", proj_options, header=_banner(), footer="↑↓ 选择  Enter 确认  Esc 返回")
        if choice is None:
            return

        proj = projects[choice]
        db_path = _find_db(proj)
        if not db_path:
            print("  " + warn(f"⚠ 项目 [{proj['id']}] 无数据库文件，仅备份配置。"))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = _sanitize_name(proj['name'])
        backup_name = f"{proj['id']}_{safe_name}_{timestamp}.tar.gz"
        backup_path = os.path.join(get_backups_dir(), backup_name)

        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(proj["path"], arcname=os.path.basename(proj["path"]))
            if db_path:
                tar.add(db_path, arcname=os.path.basename(db_path))

        print("  " + ok(f"✓ 已备份: {backup_path}"))
        wait_key()

    def _restore():
        backups = sorted(glob_mod.glob(os.path.join(get_backups_dir(), "*.tar.gz")))
        if not backups:
            print("  " + dim("无备份文件。"))
            wait_key()
            return

        backup_options = [os.path.basename(bp) for bp in backups]
        choice = menu("选择备份恢复", backup_options, header=_banner(), footer="↑↓ 选择  Enter 确认  Esc 返回")
        if choice is None:
            return

        backup_path = backups[choice]

        # 预览内容（并验证路径安全性）
        print()
        section_header("备份内容预览")
        unsafe_members = []
        with tarfile.open(backup_path, "r:gz") as tar:
            members = tar.getnames()
            for m in members:
                dest_dir = get_config_dir() if m.endswith(".yaml") else get_data_dir()
                dest_path = os.path.realpath(os.path.join(dest_dir, m))
                safe_prefix = os.path.realpath(dest_dir) + os.sep
                if not dest_path.startswith(safe_prefix):
                    unsafe_members.append(m)
                    print(f"    {err('✗')} {value(m)} {err('(路径不安全，将跳过)')}")
                else:
                    print(f"    → {value(dest_path)}")
        print()

        # yes_no 确认
        confirmed = yes_no("确认恢复?", default=False)
        if not confirmed:
            return

        # 执行恢复（跳过不安全路径）
        with tarfile.open(backup_path, "r:gz") as tar:
            for member in tar.getmembers():
                # 安全检查：验证路径不会逃逸到目标目录之外
                dest_dir = get_config_dir() if member.name.endswith(".yaml") else get_data_dir()
                dest_path = os.path.realpath(os.path.join(dest_dir, member.name))
                safe_prefix = os.path.realpath(dest_dir) + os.sep
                if not dest_path.startswith(safe_prefix):
                    print("  " + err(f"✗ 跳过不安全路径: {member.name}"))
                    continue
                f = tar.extractfile(member)
                if f:
                    with open(dest_path, "wb") as out:
                        out.write(f.read())
                    print("  " + ok(f"✓ {dest_path}"))
        print()
        wait_key()

    while True:
        choice = menu(
            "全局项目管理",
            ["查看所有项目", "备份项目", "恢复项目"],
            header=_banner(),
            footer="↑↓ 选择  Enter 确认  Esc 返回",
        )
        if choice is None:
            return
        (_show_projects, _backup, _restore)[choice]()


# ── GitHub 连接配置 ──────────────────────────────────────


def _github_config_menu():

    def _check_gh_login():
        print()
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=5,
            )
            output = (result.stdout + result.stderr).strip()
            for line in output.split("\n"):
                if "logged in" in line.lower():
                    print("  " + ok(line.strip()))
                elif "not logged" in line.lower():
                    print("  " + err(line.strip()))
                else:
                    print(f"  {line.strip()}")
        except FileNotFoundError:
            print("  " + err("✗ gh CLI 未安装。请访问 https://cli.github.com/ 下载安装。"))
        except subprocess.TimeoutExpired:
            print("  " + err("✗ 超时。"))
        print()
        wait_key()

    def _bind_gh_repo():
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
            print("  " + dim("无项目可绑定。先使用 iss-project 创建项目。"))
            wait_key()
            return

        # 选择目标项目
        proj_options = [t[0] for t in targets]
        choice = menu("选择目标项目", proj_options, header=_banner(), footer="↑↓ 选择  Enter 确认  Esc 返回")
        if choice is None:
            return
        config_path = targets[choice][1]

        # 获取仓库列表
        print()
        try:
            result = subprocess.run(
                ["gh", "repo", "list", "--limit", "30",
                 "--json", "nameWithOwner", "-q", ".[].nameWithOwner"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                print("  " + err("✗ 无法获取仓库列表。请检查 gh 登录状态。"))
                wait_key()
                return
            repos = [r.strip() for r in result.stdout.strip().split("\n") if r.strip()]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("  " + err("✗ gh CLI 不可用或超时。"))
            wait_key()
            return

        if not repos:
            print("  " + dim("无可用仓库。"))
            wait_key()
            return

        # 仓库列表 menu，末项为手动输入
        repo_options = repos + ["手动输入..."]
        repo_choice = menu("选择仓库", repo_options, header=_banner(), footer="↑↓ 选择  Enter 确认  Esc 返回")
        if repo_choice is None:
            return

        if repo_choice == len(repos):
            # 手动输入
            repo_name = input_line("仓库 (owner/name)")
            if not repo_name:
                return
        else:
            repo_name = repos[repo_choice]

        # 写入配置
        data = load_yaml(config_path)
        if data is None:
            print("  " + err(f"✗ 无法读取 {config_path}"))
            wait_key()
            return
        data.setdefault("github", {})["repo"] = repo_name
        save_config(config_path, data)
        print("  " + ok(f"✓ 已绑定 {repo_name} → {os.path.basename(config_path)}"))
        wait_key()

    while True:
        choice = menu(
            "GitHub 连接配置",
            ["检查登录状态", "绑定仓库到项目"],
            header=_banner(),
            footer="↑↓ 选择  Enter 确认  Esc 返回",
        )
        if choice is None:
            return
        (_check_gh_login, _bind_gh_repo)[choice]()


# ── 主入口 ───────────────────────────────────────────────


def main_ui():
    """iss-ui 入口."""
    ensure_directories()

    options_list = [
        ("查看当前路径",    _view_paths),
        ("全局工具配置",    _global_config_menu),
        ("版本与环境信息",  _view_env_info),
        ("全局项目管理",    _project_mgmt_menu),
        ("GitHub 连接配置", _github_config_menu),
    ]

    # 动态添加: 当前目录有项目配置时显示编辑菜单
    cwd_config = find_config_in_dir(os.getcwd())
    if cwd_config:
        def _current_project():
            data = load_yaml(cwd_config)
            if data is None:
                print("  " + err(f"✗ 无法解析 {cwd_config}"))
                wait_key()
                return
            edit_menu(cwd_config, data)
        options_list.append(("当前项目配置", _current_project))

    labels  = [o[0] for o in options_list]
    handlers = [o[1] for o in options_list]

    try:
        while True:
            choice = menu(
                "Issue Tracker - 管理菜单",
                labels,
                header=_banner(),
                footer="↑↓ 选择  Enter 确认  Esc 退出",
            )
            if choice is None:
                break
            handlers[choice]()
    except KeyboardInterrupt:
        print()
        print("  " + dim("已退出。"))
