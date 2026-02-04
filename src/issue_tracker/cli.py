#!/usr/bin/env python3
"""Issue Tracker CLI 入口.

通用开发工具，换项目只需替换 config.yaml 和对应的 migrator 即可复用。

支持两种使用方式:
1. pip install: issue-tracker ...
2. 直接运行: python3 cli.py ...

用法:
    issue-tracker [-c CONFIG] <command> [options]

命令:
    add       新增问题
    update    更新问题字段/状态
    query     多条件过滤查询
    list      简洁表格列出
    stats     统计概览
    export    生成 markdown
    sync      同步到 GitHub
    migrate   导入外部数据
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


# ── 全局常量 ─────────────────────────────────────────────────────────────────

def _find_default_config() -> str:
    """查找默认配置文件.

    查找优先级:
    1. 当前目录的 config.yaml
    2. git root 目录的 config.yaml
    3. 包安装目录的 config.yaml (pip install 模式)

    Returns:
        找到的配置文件路径，如果都不存在则返回包安装目录的 config.yaml 路径
    """
    import subprocess

    # 1. 当前目录
    current_config = os.path.join(os.getcwd(), "config.yaml")
    if os.path.isfile(current_config):
        return current_config

    # 2. git root 目录
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        git_root = result.stdout.strip()
        git_config = os.path.join(git_root, "config.yaml")
        if os.path.isfile(git_config):
            return git_config
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. 包安装目录（回退到原有逻辑）
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config.yaml"
    )

DEFAULT_CONFIG = _find_default_config()


def _find_git_root() -> str:
    """查找当前工作目录所在的 git 仓库根目录."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 回退到当前工作目录
        return os.getcwd()


def _resolve_db_path(config: Config) -> str:
    """将 config 中的 db_path (相对 git root) 解析为绝对路径."""
    git_root = _find_git_root()
    return os.path.join(git_root, config.db_path)


# ── 命令实现 ─────────────────────────────────────────────────────────────────


def cmd_add(args, config: Config, db: Database):
    """新增问题条目."""
    from issue_tracker.core.model import Issue

    # 校验必填字段
    if not args.id:
        print("错误: --id 是必填参数", file=sys.stderr)
        sys.exit(1)
    if not args.title:
        print("错误: --title 是必填参数", file=sys.stderr)
        sys.exit(1)

    # 校验编号格式
    if not config.is_valid_id(args.id):
        print(f"错误: 编号 '{args.id}' 格式无效。合法前缀: {list(config.prefixes.keys())}", file=sys.stderr)
        sys.exit(1)

    # 编号已存在检查
    if db.issue_exists(args.id):
        print(f"错误: 编号 '{args.id}' 已存在", file=sys.stderr)
        sys.exit(1)

    # 优先级校验
    priority = args.priority
    if not priority:
        # 根据前缀自动推断
        prefix = args.id.split("-")[0]
        priority = config.priority_for_prefix(prefix)
    if not config.is_valid_priority(priority):
        print(f"错误: 优先级 '{priority}' 无效。合法值: {config.valid_priorities}", file=sys.stderr)
        sys.exit(1)

    # 状态校验
    status = args.status or "pending"
    if not config.is_valid_status(status):
        print(f"错误: 状态 '{status}' 无效。合法值: {config.valid_statuses}", file=sys.stderr)
        sys.exit(1)

    # 发现日期
    from datetime import date
    discovery_date = args.discovery_date or date.today().isoformat()

    issue = Issue(
        id=args.id,
        title=args.title,
        priority=priority,
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

    # 特殊前缀 A/T 的统计（如果数据库中有的话）
    all_issues = db.query_issues()
    a_issues = [i for i in all_issues if i.id.startswith("A-")]
    t_issues = [i for i in all_issues if i.id.startswith("T-")]
    if a_issues:
        total = len(a_issues)
        fixed = sum(1 for i in a_issues if i.status == "fixed")
        pending = total - fixed
        pct = f"{int(fixed / total * 100)}%" if total > 0 else "N/A"
        print(f"  {'A(Arch)':<10} {total:>5} {fixed:>6} {pending:>6} {pct:>6}")
    if t_issues:
        total = len(t_issues)
        fixed = sum(1 for i in t_issues if i.status == "fixed")
        pending = total - fixed
        pct = f"{int(fixed / total * 100)}%" if total > 0 else "N/A"
        print(f"  {'T(Test)':<10} {total:>5} {fixed:>6} {pending:>6} {pct:>6}")

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
    output = args.output or None
    path = exporter.export(output)
    print(f"已导出至: {path}")


def cmd_sync(args, config: Config, db: Database):
    """同步到 GitHub."""
    syncer = GithubSync(config, db)
    syncer.sync(dry_run=args.dry_run)


def cmd_migrate(args, config: Config, db: Database):
    """导入外部数据."""
    # 加载 migrator 插件
    migrator = _load_migrator(args.migrator)
    if migrator is None:
        print(f"错误: 未知 migrator '{args.migrator}'。可用: weldsmart", file=sys.stderr)
        sys.exit(1)

    source_path = args.source
    if not os.path.isfile(source_path):
        print(f"错误: 源文件不存在: {source_path}", file=sys.stderr)
        sys.exit(1)

    # 检查数据库是否已有数据
    if not args.force:
        existing = db.query_issues()
        if existing:
            print(f"数据库已有 {len(existing)} 条记录。使用 --force 强制覆盖，或不传该参数将跳过已存在的条目。")

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

    if args.dry_run:
        print("[dry-run] 仅解析，不写入数据库。")
        print("\n前10条预览:")
        for item in raw_issues[:10]:
            print(f"  {item['id']}: {item['title']} [{item['priority']}/{item['status']}]")
        return

    # 写入数据库
    from issue_tracker.core.model import Issue

    inserted = 0
    skipped = 0
    for raw in raw_issues:
        issue = Issue(
            id=raw["id"],
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

        if args.force:
            db.upsert_issue(issue)
            inserted += 1
        else:
            if db.issue_exists(issue.id):
                skipped += 1
            else:
                db.add_issue(issue)
                inserted += 1

    print(f"迁移完成: 插入 {inserted} 条, 跳过 {skipped} 条")


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
        print(fmt.format(i.id, title, i.priority, i.discovery_date, status))


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
    print(f"  优先级: {issue.priority}  |  状态: {STATUS_LABEL.get(issue.status, issue.status)}  |  发现日期: {issue.discovery_date}")
    if issue.fix_date:
        print(f"  修复日期: {issue.fix_date}")
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
        description="Issue Tracker CLI - 通用开发工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="配置文件路径（默认: 同目录 config.yaml）")

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # ── add ──
    p_add = subparsers.add_parser("add", help="新增问题")
    p_add.add_argument("--id", required=True, help="问题编号 (如 M-037)")
    p_add.add_argument("--title", required=True, help="问题标题")
    p_add.add_argument("--priority", help="优先级 (P0/P1/P2/P3)，未指定时根据编号前缀推断")
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
    p_exp.add_argument("--output", help="输出路径（默认: config 中 export.output）")

    # ── sync ──
    p_sync = subparsers.add_parser("sync", help="同步到 GitHub")
    p_sync.add_argument("--dry-run", action="store_true", help="仅预览，不实际执行")

    # ── migrate ──
    p_mig = subparsers.add_parser("migrate", help="导入外部数据")
    p_mig.add_argument("--source", required=True, help="源文件路径")
    p_mig.add_argument("--migrator", required=True, help="migrator 名称 (如 weldsmart)")
    p_mig.add_argument("--force", action="store_true", help="强制覆盖已有数据")
    p_mig.add_argument("--dry-run", action="store_true", help="仅解析，不写入数据库")

    return parser


# ── 主入口 ───────────────────────────────────────────────────────────────────


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 加载配置
    try:
        config = Config(args.config)
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
