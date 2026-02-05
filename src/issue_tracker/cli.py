#!/usr/bin/env python3
"""Issue Tracker CLI 入口.

通用开发工具，支持多项目独立运行。
通过 -p project_id 切换项目，配置和数据分别按 XDG Base Directory Specification 存储。

支持两种使用方式:
1. pip install: issue-tracker ...
2. 直接运行: python3 cli.py ...

用法:
    issue-tracker [-p PROJECT_ID] [-c CONFIG] <command> [options]

命令:
    add       新增问题（编号自动分配）
    update    更新问题字段/状态
    query     多条件过滤查询
    list      简洁表格列出
    stats     统计概览
    export    生成 markdown
    sync      同步到 GitHub
    migrate   导入外部数据（编号自动重分配）
"""

import argparse
import os
import sys

# ── 导入逻辑: 支持 pip 安装和本地开发模式 ────────────────────────────────

try:
    # pip 安装模式: from issue_tracker.xxx import ...
    from issue_tracker.core.config import Config
    from issue_tracker.core.database import Database
    from issue_tracker.core.exporter import Exporter
    from issue_tracker.core.github_sync import GithubSync
    from issue_tracker.core.paths import get_config_dir as _get_config_dir, get_data_dir as _get_data_dir, ensure_directories, find_config_in_dir, CONFIG_FILENAME
    from issue_tracker.migrators.weldsmart_migrator import WeldSmartMigrator
except ImportError:
    # 本地开发模式: 添加 src 到路径后导入
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    SRC_DIR = os.path.dirname(SCRIPT_DIR)
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
    from issue_tracker.core.config import Config
    from issue_tracker.core.database import Database
    from issue_tracker.core.exporter import Exporter
    from issue_tracker.core.github_sync import GithubSync
    from issue_tracker.migrators.weldsmart_migrator import WeldSmartMigrator
    from issue_tracker.core.paths import get_config_dir as _get_config_dir, get_data_dir as _get_data_dir, ensure_directories, find_config_in_dir, CONFIG_FILENAME


# ── 工具函数 ─────────────────────────────────────────────────────────────────


def _sanitize_name(name: str) -> str:
    """清理名称用于文件名: 保留字母数字和下划线，其余替换为下划线."""
    import re
    return re.sub(r'[^\w]', '_', name).strip('_')


def _find_project_config(project_id: str) -> str:
    """根据 project_id 在 $XDG_CONFIG_HOME/issue-tracker/ 中查找配置文件.

    匹配规则: {project_id}_*.yaml
    """
    import glob as glob_mod

    config_dir = _get_config_dir()

    pattern = os.path.join(config_dir, f"{project_id}_*.yaml")
    matches = glob_mod.glob(pattern)
    if not matches:
        all_configs = glob_mod.glob(os.path.join(config_dir, "*.yaml"))
        available = [os.path.basename(c) for c in all_configs] if all_configs else ["(无)"]
        raise FileNotFoundError(
            f"未找到项目 '{project_id}' 的配置文件\n"
            f"搜索路径: {config_dir}\n"
            f"可用项目: {available}\n"
            f"\n提示: 在项目目录创建 config.yaml，或在 {config_dir} 创建 {project_id}_ProjectName.yaml"
        )
    if len(matches) > 1:
        raise ValueError(
            f"项目 '{project_id}' 匹配到多个配置文件: {[os.path.basename(m) for m in matches]}"
        )
    return matches[0]


def _get_default_config() -> str:
    """查找默认配置文件.

    查找优先级:
    1. 当前目录的 issue-tracker.yaml
    2. $XDG_CONFIG_HOME/issue-tracker/ 中唯一的项目配置（仅一个项目时自动使用）
    3. git root 目录的 issue-tracker.yaml

    Returns:
        找到的配置文件路径
    """
    import subprocess
    import glob as glob_mod

    # 1. 当前目录
    cwd_config = find_config_in_dir(os.getcwd())
    if cwd_config:
        return cwd_config

    # 2. XDG 配置目录中唯一项目配置（排除 globals.yaml）
    config_dir = _get_config_dir()
    if os.path.isdir(config_dir):
        configs = [c for c in glob_mod.glob(os.path.join(config_dir, "*.yaml"))
                   if os.path.basename(c) != "globals.yaml"]
        if len(configs) == 1:
            return configs[0]

    # 3. git root 目录
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        git_root = result.stdout.strip()
        git_config = find_config_in_dir(git_root)
        if git_config:
            return git_config
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 回退: 返回当前目录下的 issue-tracker.yaml（即使不存在，后续会报错）
    return os.path.join(os.getcwd(), CONFIG_FILENAME)


def _resolve_db_path(config: Config) -> str:
    """解析数据库路径.

    路径: $XDG_DATA_HOME/issue-tracker/{project_id}_{project_name}.db
    """
    data_dir = _get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    db_name = f"{config.project_id}_{_sanitize_name(config.project_name)}.db"
    return os.path.join(data_dir, db_name)


# ── 命令实现 ─────────────────────────────────────────────────────────────────


def cmd_add(args, config: Config, db: Database):
    """新增问题条目（编号自动分配）."""
    from issue_tracker.core.model import Issue

    # 校验必填字段
    if not args.title:
        print("错误: --title 是必填参数", file=sys.stderr)
        sys.exit(1)
    if not args.priority:
        print("错误: --priority 是必填参数", file=sys.stderr)
        sys.exit(1)

    # 优先级校验
    if not config.is_valid_priority(args.priority):
        print(f"错误: 优先级 '{args.priority}' 无效。合法值: {config.valid_priorities}", file=sys.stderr)
        sys.exit(1)

    # 状态校验
    status = args.status or "pending"
    if not config.is_valid_status(status):
        print(f"错误: 状态 '{status}' 无效。合法值: {config.valid_statuses}", file=sys.stderr)
        sys.exit(1)

    # 确定编号
    if args.id:
        # 手动指定编号
        if not config.is_valid_id(args.id):
            print(f"错误: 编号 '{args.id}' 格式无效（应为纯数字）", file=sys.stderr)
            sys.exit(1)
        if db.issue_exists(args.id):
            print(f"错误: 编号 '{args.id}' 已存在", file=sys.stderr)
            sys.exit(1)
        issue_id = args.id
    else:
        # 自动分配编号
        next_num = db.get_next_id()
        issue_id = config.id_format.format(num=next_num)

    # 发现日期
    from datetime import date
    discovery_date = args.discovery_date or date.today().isoformat()

    issue = Issue(
        id=issue_id,
        title=args.title,
        priority=args.priority,
        status=status,
        discovery_date=discovery_date,
        fix_date=args.fix_date,
        file_path=args.file,
        location=args.location,
        description=args.description,
        impact=args.impact,
        fix_plan=args.fix_plan,
        estimated_hours=_parse_float(args.estimated_hours),
        actual_hours=_parse_float(args.actual_hours),
        phase=args.phase,
        github_issue_id=_parse_int(args.github_issue_id),
    )

    db.add_issue(issue)
    print(f"已新增: {issue.id} - {issue.title} [{issue.priority}/{issue.status}]")


def cmd_update(args, config: Config, db: Database):
    """更新问题条目."""
    issue_id = args.id

    if not db.issue_exists(issue_id):
        print(f"错误: 编号 '{issue_id}' 不存在", file=sys.stderr)
        sys.exit(1)

    # 收集待更新字段
    updates = {}
    field_map = {
        "title": "title",
        "priority": "priority",
        "status": "status",
        "fix_date": "fix_date",
        "file": "file_path",
        "location": "location",
        "description": "description",
        "impact": "impact",
        "fix_plan": "fix_plan",
        "estimated_hours": "estimated_hours",
        "actual_hours": "actual_hours",
        "phase": "phase",
        "github_issue_id": "github_issue_id",
    }

    for arg_name, db_field in field_map.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            if db_field in ("estimated_hours", "actual_hours"):
                updates[db_field] = _parse_float(val)
            elif db_field == "github_issue_id":
                updates[db_field] = _parse_int(val)
            else:
                updates[db_field] = val

    # 校验 status 和 priority
    if "status" in updates and not config.is_valid_status(updates["status"]):
        print(f"错误: 状态 '{updates['status']}' 无效。合法值: {config.valid_statuses}", file=sys.stderr)
        sys.exit(1)
    if "priority" in updates and not config.is_valid_priority(updates["priority"]):
        print(f"错误: 优先级 '{updates['priority']}' 无效。合法值: {config.valid_priorities}", file=sys.stderr)
        sys.exit(1)

    if not updates:
        print("警告: 没有字段待更新", file=sys.stderr)
        return

    success = db.update_issue(issue_id, **updates)
    if success:
        print(f"已更新: {issue_id} → {updates}")
    else:
        print(f"错误: 更新 '{issue_id}' 失败", file=sys.stderr)


def cmd_query(args, config: Config, db: Database):
    """多条件过滤查询."""
    issues = db.query_issues(
        issue_id=args.id,
        priority=args.priority,
        status=args.status,
        phase=args.phase,
        file_glob=args.file,
        github_issue_id=_parse_int(args.github),
    )

    if not issues:
        print("无匹配条目。")
        return

    if args.detail:
        # 详细模式：逐条展开
        for issue in issues:
            _print_issue_detail(issue)
            print("-" * 60)
    else:
        # 概要模式：表格
        _print_issue_table(issues)

    print(f"\n共 {len(issues)} 条")


def cmd_list(args, config: Config, db: Database):
    """简洁表格列出."""
    issues = db.query_issues(
        status=args.status,
        priority=args.priority,
    )

    if not issues:
        print("无匹配条目。")
        return

    _print_issue_table(issues)
    print(f"\n共 {len(issues)} 条")


def cmd_stats(args, config: Config, db: Database):
    """统计概览."""
    stats = db.get_stats()

    print("=" * 50)
    print(f"  {config.project_name} - 问题统计")
    print("=" * 50)
    print(f"  总数: {stats['total']}")
    print()

    # 按优先级统计
    print("  按优先级:")
    print(f"  {'优先级':<10} {'总数':>5} {'已修复':>6} {'待处理':>6} {'进度':>6}")
    print(f"  {'-'*10} {'-'*5} {'-'*6} {'-'*6} {'-'*6}")

    for p in config.valid_priorities:
        detail = stats["by_priority_detail"].get(p, {})
        total = sum(detail.values())
        fixed = detail.get("fixed", 0)
        na = detail.get("n_a", 0)
        pending = total - fixed - na
        pct = f"{int(fixed / total * 100)}%" if total > 0 else "N/A"
        print(f"  {p:<10} {total:>5} {fixed:>6} {pending:>6} {pct:>6}")

    print()

    # 按状态统计
    print("  按状态:")
    for status, count in sorted(stats["by_status"].items(), key=lambda x: -x[1]):
        bar = "█" * int(count / stats["total"] * 30) if stats["total"] > 0 else ""
        print(f"    {status:<15} {count:>4}  {bar}")

    print("=" * 50)


def cmd_export(args, config: Config, db: Database):
    """生成 markdown 文件."""
    exporter = Exporter(config, db)
    if args.output:
        output = args.output
    else:
        # export.output 相对于 XDG 数据目录
        output = os.path.join(_get_data_dir(), config.export_output)
    path = exporter.export(output)
    print(f"已导出至: {path}")


def cmd_sync(args, config: Config, db: Database):
    """同步到 GitHub."""
    syncer = GithubSync(config, db)
    syncer.sync(dry_run=args.dry_run)


def cmd_migrate(args, config: Config, db: Database):
    """导入外部数据（编号自动重分配）."""
    # 加载 migrator 插件
    migrator = _load_migrator(args.migrator)
    if migrator is None:
        print(f"错误: 未知 migrator '{args.migrator}'。可用: weldsmart", file=sys.stderr)
        sys.exit(1)

    source_path = args.source
    if not os.path.isfile(source_path):
        print(f"错误: 源文件不存在: {source_path}", file=sys.stderr)
        sys.exit(1)

    # 解析源文件
    print(f"解析: {source_path}")
    raw_issues = migrator.parse(source_path)
    print(f"解析得到: {len(raw_issues)} 条")

    # 校验
    warnings = migrator.validate(raw_issues)
    if warnings:
        print(f"\n警告 ({len(warnings)} 条):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    # 按发现日期排序，同日期按原编号字典序（保证编号分配顺序确定）
    raw_issues.sort(key=lambda x: (x.get("discovery_date", ""), x.get("id", "")))

    if args.dry_run:
        print("[dry-run] 仅预览，不写入数据库。编号为预计自动分配值。\n")
        next_num = db.get_next_id()
        print("前10条预览:")
        for item in raw_issues[:10]:
            preview_id = config.id_format.format(num=next_num)
            next_num += 1
            print(f"  {preview_id}: {item['title']} [{item['priority']}/{item['status']}]  (原编号: {item['id']})")
        return

    # --force: 清空现有数据后导入
    if args.force:
        existing = db.query_issues()
        for e in existing:
            db.delete_issue(e.id)
        print(f"已清空 {len(existing)} 条现有记录")

    # 写入数据库，编号自动分配
    from issue_tracker.core.model import Issue

    next_num = db.get_next_id()
    inserted = 0
    for raw in raw_issues:
        new_id = config.id_format.format(num=next_num)
        next_num += 1

        issue = Issue(
            id=new_id,
            title=raw["title"],
            priority=raw["priority"],
            status=raw["status"],
            discovery_date=raw["discovery_date"],
            fix_date=raw.get("fix_date"),
            file_path=raw.get("file_path"),
            location=raw.get("location"),
            description=raw.get("description"),
            impact=raw.get("impact"),
            fix_plan=raw.get("fix_plan"),
            estimated_hours=raw.get("estimated_hours"),
            actual_hours=raw.get("actual_hours"),
            phase=raw.get("phase"),
            github_issue_id=raw.get("github_issue_id"),
        )

        db.add_issue(issue)
        inserted += 1

    first_id = config.id_format.format(num=next_num - inserted)
    last_id = config.id_format.format(num=next_num - 1)
    print(f"迁移完成: 插入 {inserted} 条 (编号范围: {first_id} ~ {last_id})")


# ── 辅助函数 ─────────────────────────────────────────────────────────────────


def _load_migrator(name: str):
    """根据名称加载 migrator 插件."""
    if name == "weldsmart":
        return WeldSmartMigrator()
    return None


def _parse_float(val) -> float | None:
    """安全转换为 float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int(val) -> int | None:
    """安全转换为 int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _format_relative_date(date_str: str | None) -> str:
    """将日期格式化为相对时间（今天/昨天/N天前）或具体日期."""
    if not date_str:
        return ""

    from datetime import date

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        return date_str

    today = date.today()
    delta = today - target_date

    if delta.days == 0:
        return "今天"
    elif delta.days == 1:
        return "昨天"
    elif delta.days == -1:
        return "明天"
    elif delta.days == 2:
        return "2天前"
    elif delta.days == -2:
        return "2天后"
    elif delta.days == 3:
        return "3天前"
    elif delta.days == -3:
        return "3天后"
    else:
        # 超过3天显示具体日期
        return date_str


def _print_issue_table(issues):
    """打印问题概要表格."""
    STATUS_LABEL = {
        "fixed": "✅ 已修复",
        "pending": "❌ 待修复",
        "in_progress": "🟢 进行中",
        "planned": "📋 待规划",
        "n_a": "⚠️ 不适用",
    }

    # 计算列宽
    id_w = max(len("编号"), max((len(i.id) for i in issues), default=0))
    title_w = min(50, max(len("问题描述"), max((len(i.title) for i in issues), default=0)))

    fmt = f"  {{:<{id_w}}}  {{:<{title_w}}}  {{:<6}}  {{:<12}}  {{}}"
    print(fmt.format("编号", "问题描述", "优先级", "发现日期", "状态"))
    print(fmt.format("-" * id_w, "-" * title_w, "-" * 6, "-" * 12, "-" * 8))

    for i in issues:
        title = i.title if len(i.title) <= title_w else i.title[: title_w - 2] + ".."
        status = STATUS_LABEL.get(i.status, i.status)
        discovery_display = _format_relative_date(i.discovery_date) or i.discovery_date
        print(fmt.format(i.id, title, i.priority, discovery_display, status))


def _print_issue_detail(issue):
    """打印单条问题详情."""
    STATUS_LABEL = {
        "fixed": "✅ 已修复",
        "pending": "❌ 待修复",
        "in_progress": "🟢 进行中",
        "planned": "📋 待规划",
        "n_a": "⚠️ 不适用",
    }
    print(f"\n  [{issue.id}] {issue.title}")
    discovery_display = _format_relative_date(issue.discovery_date) or issue.discovery_date
    print(f"  优先级: {issue.priority}  |  状态: {STATUS_LABEL.get(issue.status, issue.status)}  |  发现日期: {discovery_display}")
    if issue.fix_date:
        fix_display = _format_relative_date(issue.fix_date) or issue.fix_date
        print(f"  修复日期: {fix_display}")
    if issue.file_path:
        print(f"  文件: {issue.file_path}")
    if issue.location:
        print(f"  位置: {issue.location}")
    if issue.description:
        print(f"  描述: {issue.description[:200]}{'...' if len(issue.description) > 200 else ''}")
    if issue.impact:
        print(f"  影响: {issue.impact[:150]}{'...' if len(issue.impact) > 150 else ''}")
    if issue.fix_plan:
        print(f"  修复方案: {issue.fix_plan[:150]}{'...' if len(issue.fix_plan) > 150 else ''}")
    hours = []
    if issue.estimated_hours is not None:
        hours.append(f"预计 {issue.estimated_hours}h")
    if issue.actual_hours is not None:
        hours.append(f"实际 {issue.actual_hours}h")
    if hours:
        print(f"  工时: {', '.join(hours)}")
    if issue.github_issue_id:
        print(f"  GitHub Issue: #{issue.github_issue_id}")


# ── Argument Parser 构建 ────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issue-tracker",
        description="Issue Tracker CLI - 通用开发工具（支持多项目）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-p", "--project", help="项目ID（纯数字），从 $XDG_CONFIG_HOME/issue-tracker/ 查找配置")
    parser.add_argument("-c", "--config", default=None, help="手动指定配置文件路径")

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # ── add ──
    p_add = subparsers.add_parser("add", help="新增问题（编号自动分配）")
    p_add.add_argument("--id", help="手动指定编号（纯数字，默认自动分配）")
    p_add.add_argument("--title", required=True, help="问题标题")
    p_add.add_argument("--priority", required=True, help="优先级 (P0/P1/P2/P3)")
    p_add.add_argument("--status", default="pending", help="状态 (默认: pending)")
    p_add.add_argument("--discovery-date", help="发现日期 YYYY-MM-DD (默认: 今天)")
    p_add.add_argument("--fix-date", help="修复日期 YYYY-MM-DD")
    p_add.add_argument("--file", help="文件路径（多个用逗号分隔）")
    p_add.add_argument("--location", help="位置描述")
    p_add.add_argument("--description", help="问题描述")
    p_add.add_argument("--impact", help="影响")
    p_add.add_argument("--fix-plan", help="修复方案")
    p_add.add_argument("--estimated-hours", help="预计工时（小时）")
    p_add.add_argument("--actual-hours", help="实际工时（小时）")
    p_add.add_argument("--phase", help="所属阶段")
    p_add.add_argument("--github-issue-id", help="关联 GitHub Issue 编号")

    # ── update ──
    p_upd = subparsers.add_parser("update", help="更新问题字段")
    p_upd.add_argument("id", help="问题编号")
    p_upd.add_argument("--title", help="新标题")
    p_upd.add_argument("--priority", help="新优先级")
    p_upd.add_argument("--status", help="新状态")
    p_upd.add_argument("--fix-date", help="修复日期")
    p_upd.add_argument("--file", help="文件路径")
    p_upd.add_argument("--location", help="位置描述")
    p_upd.add_argument("--description", help="问题描述")
    p_upd.add_argument("--impact", help="影响")
    p_upd.add_argument("--fix-plan", help="修复方案")
    p_upd.add_argument("--estimated-hours", help="预计工时")
    p_upd.add_argument("--actual-hours", help="实际工时")
    p_upd.add_argument("--phase", help="阶段")
    p_upd.add_argument("--github-issue-id", help="GitHub Issue 编号")

    # ── query ──
    p_qry = subparsers.add_parser("query", help="多条件过滤查询")
    p_qry.add_argument("--id", help="精确匹配编号")
    p_qry.add_argument("--priority", help="优先级过滤")
    p_qry.add_argument("--status", help="状态过滤")
    p_qry.add_argument("--phase", help="阶段过滤")
    p_qry.add_argument("--file", help="文件路径 glob 匹配 (如 src/hal/*)")
    p_qry.add_argument("--github", help="GitHub Issue 编号过滤")
    p_qry.add_argument("--detail", action="store_true", help="展开显示完整描述")

    # ── list ──
    p_lst = subparsers.add_parser("list", help="简洁表格列出")
    p_lst.add_argument("--status", help="状态过滤")
    p_lst.add_argument("--priority", help="优先级过滤")

    # ── stats ──
    subparsers.add_parser("stats", help="统计概览")

    # ── export ──
    p_exp = subparsers.add_parser("export", help="生成 markdown")
    p_exp.add_argument("--output", help="输出路径（默认: 相对于 ISSUE_TRACKER_HOME 的 export.output）")

    # ── sync ──
    p_sync = subparsers.add_parser("sync", help="同步到 GitHub")
    p_sync.add_argument("--dry-run", action="store_true", help="仅预览，不实际执行")

    # ── migrate ──
    p_mig = subparsers.add_parser("migrate", help="导入外部数据（编号自动重分配）")
    p_mig.add_argument("--source", required=True, help="源文件路径")
    p_mig.add_argument("--migrator", required=True, help="migrator 名称 (如 weldsmart)")
    p_mig.add_argument("--force", action="store_true", help="清空现有数据后导入")
    p_mig.add_argument("--dry-run", action="store_true", help="仅解析预览，不写入数据库")

    return parser


# ── 主入口 ───────────────────────────────────────────────────────────────────


def main():
    # 确保必要的目录存在
    ensure_directories()

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 解析配置文件路径
    config_path = None
    if args.project:
        # -p 模式: 从 ISSUE_TRACKER_HOME/.config/ 查找
        try:
            config_path = _find_project_config(args.project)
        except (FileNotFoundError, ValueError) as e:
            print(f"项目查找失败: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.config:
        # -c 模式: 手动指定配置文件
        config_path = args.config
    else:
        # 回退: 自动查找
        config_path = _get_default_config()

    try:
        config = Config(config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"配置加载失败: {e}", file=sys.stderr)
        sys.exit(1)

    # 初始化数据库
    db_path = _resolve_db_path(config)
    db = Database(db_path)

    # 分发到对应的命令处理函数
    command_map = {
        "add": cmd_add,
        "update": cmd_update,
        "query": cmd_query,
        "list": cmd_list,
        "stats": cmd_stats,
        "export": cmd_export,
        "sync": cmd_sync,
        "migrate": cmd_migrate,
    }

    try:
        command_map[args.command](args, config, db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
