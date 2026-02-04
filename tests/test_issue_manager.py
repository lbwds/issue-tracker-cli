"""Issue Tracker 单元测试.

覆盖: 配置加载校验、数据库 CRUD、自动编号、weldsmart_migrator 解析、export 格式、sync 逻辑。

运行方式:
    pip 模式: pytest tests/ -v
    本地模式: python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# ── 导入逻辑: 支持 pip 安装和本地开发模式 ────────────────────────────────

try:
    # pip 安装模式
    from issue_tracker.core.config import Config
    from issue_tracker.core.database import Database
    from issue_tracker.core.model import Issue
    from issue_tracker.core.exporter import Exporter
    from issue_tracker.core.github_sync import GithubSync
    from issue_tracker.migrators.weldsmart_migrator import WeldSmartMigrator
except ImportError:
    # 本地开发模式: 添加 src 到路径
    SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SRC_DIR = os.path.join(SCRIPT_DIR, "src")
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
    from issue_tracker.core.config import Config
    from issue_tracker.core.database import Database
    from issue_tracker.core.model import Issue
    from issue_tracker.core.exporter import Exporter
    from issue_tracker.core.github_sync import GithubSync
    from issue_tracker.migrators.weldsmart_migrator import WeldSmartMigrator


# ── 辅助: 生成临时配置和数据库 ────────────────────────────────────────────────

VALID_CONFIG_YAML = """\
project:
  id: "001"
  name: "TestProject"

id_rules:
  format: "{num:03d}"

priorities: [P0, P1, P2, P3]
statuses: [pending, in_progress, planned, fixed, n_a]

github:
  enabled: true
  close_on_fix: true
  comment_template: "自动同步: {issue_id} 已修复"

export:
  output: "all-issues.md"
"""

INVALID_CONFIG_MISSING_PROJECT = """\
id_rules:
  format: "{num:03d}"
priorities: [P0]
statuses: [pending]
"""

INVALID_CONFIG_MISSING_PROJECT_ID = """\
project:
  name: "Test"
id_rules:
  format: "{num:03d}"
priorities: [P0, P1]
statuses: [pending]
"""


def _write_temp_config(content: str) -> str:
    """写入临时配置文件并返回路径."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _make_db() -> Database:
    """创建内存数据库."""
    return Database(":memory:")


def _sample_issue(issue_id="001", title="测试问题", priority="P2", status="pending") -> Issue:
    return Issue(
        id=issue_id,
        title=title,
        priority=priority,
        status=status,
        discovery_date="2026-01-01",
        file_path="src/test.cpp",
        location="行 10",
        description="测试描述",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 配置测试
# ══════════════════════════════════════════════════════════════════════════════


class TestConfig(unittest.TestCase):
    """配置加载与校验测试."""

    def test_load_valid_config(self):
        path = _write_temp_config(VALID_CONFIG_YAML)
        try:
            config = Config(path)
            self.assertEqual(config.project_id, "001")
            self.assertEqual(config.project_name, "TestProject")
            self.assertEqual(config.id_format, "{num:03d}")
            self.assertTrue(config.is_valid_priority("P2"))
            self.assertFalse(config.is_valid_priority("P99"))
            self.assertTrue(config.is_valid_status("fixed"))
            self.assertFalse(config.is_valid_status("unknown"))
        finally:
            os.unlink(path)

    def test_config_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            Config("/nonexistent/path/config.yaml")

    def test_config_missing_required_section(self):
        path = _write_temp_config(INVALID_CONFIG_MISSING_PROJECT)
        try:
            with self.assertRaises(ValueError):
                Config(path)
        finally:
            os.unlink(path)

    def test_config_missing_project_id(self):
        path = _write_temp_config(INVALID_CONFIG_MISSING_PROJECT_ID)
        try:
            with self.assertRaises(ValueError):
                Config(path)
        finally:
            os.unlink(path)

    def test_is_valid_id(self):
        path = _write_temp_config(VALID_CONFIG_YAML)
        try:
            config = Config(path)
            self.assertTrue(config.is_valid_id("001"))
            self.assertTrue(config.is_valid_id("037"))
            self.assertTrue(config.is_valid_id("100"))
            self.assertFalse(config.is_valid_id("C-001"))  # 旧前缀格式不合法
            self.assertFalse(config.is_valid_id("abc"))    # 非数字
            self.assertFalse(config.is_valid_id(""))       # 空字符串
        finally:
            os.unlink(path)

    def test_id_format_rendering(self):
        path = _write_temp_config(VALID_CONFIG_YAML)
        try:
            config = Config(path)
            self.assertEqual(config.id_format.format(num=1), "001")
            self.assertEqual(config.id_format.format(num=42), "042")
            self.assertEqual(config.id_format.format(num=1000), "1000")
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════════════════
# 数据库 CRUD 测试
# ══════════════════════════════════════════════════════════════════════════════


class TestDatabaseCRUD(unittest.TestCase):
    """数据库增删改查测试."""

    def setUp(self):
        self.db = _make_db()

    def tearDown(self):
        self.db.close()

    def test_add_and_get(self):
        issue = _sample_issue("001", "临界问题", "P0", "pending")
        self.db.add_issue(issue)

        result = self.db.get_issue("001")
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "001")
        self.assertEqual(result.title, "临界问题")
        self.assertEqual(result.priority, "P0")

    def test_get_nonexistent(self):
        result = self.db.get_issue("999")
        self.assertIsNone(result)

    def test_add_duplicate_raises(self):
        import sqlite3
        issue = _sample_issue("001")
        self.db.add_issue(issue)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_issue(issue)

    def test_update_issue(self):
        self.db.add_issue(_sample_issue("001", status="pending"))
        success = self.db.update_issue("001", status="fixed", fix_date="2026-02-01")
        self.assertTrue(success)

        result = self.db.get_issue("001")
        self.assertEqual(result.status, "fixed")
        self.assertEqual(result.fix_date, "2026-02-01")

    def test_update_nonexistent(self):
        success = self.db.update_issue("999", status="fixed")
        self.assertFalse(success)

    def test_update_no_fields(self):
        self.db.add_issue(_sample_issue("001"))
        success = self.db.update_issue("001")
        self.assertFalse(success)

    def test_delete_issue(self):
        self.db.add_issue(_sample_issue("001"))
        self.assertTrue(self.db.delete_issue("001"))
        self.assertIsNone(self.db.get_issue("001"))

    def test_delete_nonexistent(self):
        self.assertFalse(self.db.delete_issue("999"))

    def test_issue_exists(self):
        self.db.add_issue(_sample_issue("001"))
        self.assertTrue(self.db.issue_exists("001"))
        self.assertFalse(self.db.issue_exists("002"))

    def test_upsert_insert(self):
        issue = _sample_issue("001", title="初始标题")
        self.db.upsert_issue(issue)
        result = self.db.get_issue("001")
        self.assertEqual(result.title, "初始标题")

    def test_upsert_update(self):
        self.db.upsert_issue(_sample_issue("001", title="初始"))
        self.db.upsert_issue(_sample_issue("001", title="更新后"))
        result = self.db.get_issue("001")
        self.assertEqual(result.title, "更新后")


# ══════════════════════════════════════════════════════════════════════════════
# 自动编号测试
# ══════════════════════════════════════════════════════════════════════════════


class TestDatabaseAutoId(unittest.TestCase):
    """自动编号 get_next_id() 测试."""

    def setUp(self):
        self.db = _make_db()

    def tearDown(self):
        self.db.close()

    def test_next_id_empty_db(self):
        """空数据库返回 1."""
        self.assertEqual(self.db.get_next_id(), 1)

    def test_next_id_sequential(self):
        """插入 001, 002 后返回 3."""
        self.db.add_issue(_sample_issue("001"))
        self.db.add_issue(_sample_issue("002"))
        self.assertEqual(self.db.get_next_id(), 3)

    def test_next_id_with_gap(self):
        """有间断时返回 max+1（不填补空缺）."""
        self.db.add_issue(_sample_issue("001"))
        self.db.add_issue(_sample_issue("005"))
        self.assertEqual(self.db.get_next_id(), 6)

    def test_next_id_after_delete(self):
        """删除最大编号后，max 变为次大值，返回次大值+1."""
        self.db.add_issue(_sample_issue("001"))
        self.db.add_issue(_sample_issue("002"))
        self.db.add_issue(_sample_issue("003"))
        self.db.delete_issue("003")
        self.assertEqual(self.db.get_next_id(), 3)

    def test_next_id_ignores_non_numeric(self):
        """非纯数字 ID（如迁移残留的旧格式）不影响计算."""
        self.db.add_issue(_sample_issue("001"))
        self.db.add_issue(_sample_issue("C-005", title="旧格式残留"))
        # C-005 不是纯数字，GLOB '[0-9]*' 不匹配，仅看 001
        self.assertEqual(self.db.get_next_id(), 2)

    def test_next_id_large_number(self):
        """超过3位数仍正确计算."""
        self.db.add_issue(_sample_issue("999"))
        self.assertEqual(self.db.get_next_id(), 1000)
        self.db.add_issue(_sample_issue("1000"))
        self.assertEqual(self.db.get_next_id(), 1001)


# ══════════════════════════════════════════════════════════════════════════════
# 查询测试
# ══════════════════════════════════════════════════════════════════════════════


class TestDatabaseQuery(unittest.TestCase):
    """查询与过滤测试."""

    def setUp(self):
        self.db = _make_db()
        # 插入测试数据
        self.db.add_issue(_sample_issue("001", "临界A", "P0", "fixed"))
        self.db.add_issue(_sample_issue("002", "中等A", "P2", "pending"))
        self.db.add_issue(_sample_issue("003", "中等B", "P2", "fixed"))
        self.db.add_issue(_sample_issue("004", "低等A", "P3", "planned"))
        # 添加带不同文件路径的条目
        issue_hal = Issue(
            id="005", title="HAL问题", priority="P1", status="pending",
            discovery_date="2026-01-15", file_path="src/hal/device/DeviceManager.cpp",
        )
        self.db.add_issue(issue_hal)

    def tearDown(self):
        self.db.close()

    def test_query_by_priority(self):
        results = self.db.query_issues(priority="P2")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(i.priority == "P2" for i in results))

    def test_query_by_status(self):
        results = self.db.query_issues(status="pending")
        self.assertEqual(len(results), 2)  # 002 和 005

    def test_query_by_id(self):
        results = self.db.query_issues(issue_id="001")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "001")

    def test_query_by_file_glob(self):
        results = self.db.query_issues(file_glob="src/hal/*")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "005")

    def test_query_no_match(self):
        results = self.db.query_issues(priority="P0", status="pending")
        self.assertEqual(len(results), 0)

    def test_query_all(self):
        results = self.db.query_issues()
        self.assertEqual(len(results), 5)


# ══════════════════════════════════════════════════════════════════════════════
# 统计测试
# ══════════════════════════════════════════════════════════════════════════════


class TestDatabaseStats(unittest.TestCase):
    """统计功能测试."""

    def setUp(self):
        self.db = _make_db()
        self.db.add_issue(_sample_issue("001", priority="P0", status="fixed"))
        self.db.add_issue(_sample_issue("002", priority="P0", status="fixed"))
        self.db.add_issue(_sample_issue("003", status="pending"))
        self.db.add_issue(_sample_issue("004", status="n_a"))

    def tearDown(self):
        self.db.close()

    def test_stats_total(self):
        stats = self.db.get_stats()
        self.assertEqual(stats["total"], 4)

    def test_stats_by_status(self):
        stats = self.db.get_stats()
        self.assertEqual(stats["by_status"]["fixed"], 2)
        self.assertEqual(stats["by_status"]["pending"], 1)
        self.assertEqual(stats["by_status"]["n_a"], 1)

    def test_stats_by_priority(self):
        stats = self.db.get_stats()
        self.assertEqual(stats["by_priority"]["P0"], 2)
        self.assertEqual(stats["by_priority"]["P2"], 2)


# ══════════════════════════════════════════════════════════════════════════════
# WeldSmart Migrator 测试
# ══════════════════════════════════════════════════════════════════════════════
# 注意: migrator 负责解析源文件，返回原始编号（如 C-001）。
# 编号重分配由 cmd_migrate 在写入数据库时执行，此处不测试。

SAMPLE_MD_NORMAL = """\
# 测试文档

## Critical Priority

### C-001: ModbusTCPClient 内存泄漏 - ✅ 已修复
**发现日期**: 2026-01-19
**文件**: `src/hal/communication/modbus/ModbusTCPClient.cpp`
**位置**: 行 139-152

**问题描述**:
`readCoil()` 方法内存管理错误。

**影响**:
导致内存泄漏和程序崩溃。

**修复方案**:
使用栈分配的数组替代动态分配。

**实际工时**: 6 小时
**状态**: ✅ 已修复 (2026-01-19)

---

### C-002: Config 回调通知死锁风险 - ✅ 已修复
**发现日期**: 2026-01-19
**文件**: `src/core/common/Config.cpp`
**位置**: 行 245-287

**问题描述**:
`notifyChange()` 在持有锁时调用用户回调，可能死锁。

**修复方案**: 将回调移到锁外执行

**状态**: ✅ 已修复 (2026-01-19)

---
"""

SAMPLE_MD_MULTI_STATUS = """\
### M-025: DeviceFactory 警告屏蔽 - ⚠️ 不适用
**发现日期**: 2026-01-31
**文件**: `src/hal/factory/DeviceFactory.cpp`

**问题描述**:
代码中未发现此问题。

**状态**: ⚠️ 不适用 - 代码中未发现此问题

---

### L-009: 测试覆盖率不足 - 🟢 进行中
**发现日期**: 2026-01-29
**文件**: `tests/unit/`

**问题描述**:
测试覆盖率不足。

**预计工时**: 8 小时
**状态**: 🟢 进行中 (已完成70%，目标80%)

---

### T-001: ThreadPoolTest 不稳定测试 - 📋 待规划
**发现日期**: 2026-02-03
**文件**: `tests/unit/core/test_thread_pool.cpp`
**位置**: 行 221-246

**问题描述**:
ConcurrentSubmit 测试概率性失败。

**预计工时**: 2 小时
**优先级**: P3

---
"""

SAMPLE_MD_MULTI_FILE = """\
### L-020: 函数参数注释不完整 - ✅ 已修复
**发现日期**: 2026-02-01
**文件**: `src/hal/device/IDeviceParameter.h`, `src/hal/device/IDeviceLifecycle.h`, `src/business/recipe/RecipeManager.h`

**问题描述**: 部分函数缺少失败情况的说明

**预计工时**: 8 小时
**实际工时**: 3 小时
**状态**: ✅ 已修复 (2026-02-02)

---
"""


class TestWeldSmartMigrator(unittest.TestCase):
    """WeldSmart migrator 解析测试.

    migrator 解析返回原始编号(如 C-001)。
    编号重分配由 cmd_migrate 在写入数据库时执行。
    """

    def setUp(self):
        self.migrator = WeldSmartMigrator()

    def _parse_from_str(self, content: str) -> list[dict]:
        """写入临时文件并解析."""
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            return self.migrator.parse(path)
        finally:
            os.unlink(path)

    def test_parse_normal_entries(self):
        issues = self._parse_from_str(SAMPLE_MD_NORMAL)
        self.assertEqual(len(issues), 2)

        # 检查第一条（解析阶段仍保留原始编号）
        c001 = issues[0]
        self.assertEqual(c001["id"], "C-001")
        self.assertEqual(c001["title"], "ModbusTCPClient 内存泄漏")
        self.assertEqual(c001["status"], "fixed")
        self.assertEqual(c001["priority"], "P0")
        self.assertEqual(c001["discovery_date"], "2026-01-19")
        self.assertEqual(c001["fix_date"], "2026-01-19")
        self.assertIn("ModbusTCPClient.cpp", c001["file_path"])
        self.assertEqual(c001["actual_hours"], 6.0)
        self.assertIn("readCoil()", c001["description"])
        self.assertIn("内存泄漏", c001["impact"])
        self.assertIn("栈分配", c001["fix_plan"])

    def test_parse_n_a_status(self):
        issues = self._parse_from_str(SAMPLE_MD_MULTI_STATUS)
        m025 = next(i for i in issues if i["id"] == "M-025")
        self.assertEqual(m025["status"], "n_a")

    def test_parse_in_progress_status(self):
        issues = self._parse_from_str(SAMPLE_MD_MULTI_STATUS)
        l009 = next(i for i in issues if i["id"] == "L-009")
        self.assertEqual(l009["status"], "in_progress")
        self.assertEqual(l009["estimated_hours"], 8.0)

    def test_parse_planned_status(self):
        issues = self._parse_from_str(SAMPLE_MD_MULTI_STATUS)
        t001 = next(i for i in issues if i["id"] == "T-001")
        self.assertEqual(t001["status"], "planned")
        self.assertEqual(t001["priority"], "P3")  # 由 **优先级** 字段覆盖
        self.assertEqual(t001["estimated_hours"], 2.0)

    def test_parse_multi_file_paths(self):
        issues = self._parse_from_str(SAMPLE_MD_MULTI_FILE)
        l020 = issues[0]
        self.assertEqual(l020["id"], "L-020")
        # 多个文件路径逗号分隔
        self.assertIn("IDeviceParameter.h", l020["file_path"])
        self.assertIn("IDeviceLifecycle.h", l020["file_path"])
        self.assertIn("RecipeManager.h", l020["file_path"])
        self.assertEqual(l020["estimated_hours"], 8.0)
        self.assertEqual(l020["actual_hours"], 3.0)
        self.assertEqual(l020["fix_date"], "2026-02-02")

    def test_validate_detects_duplicates(self):
        issues = [
            {"id": "C-001", "title": "A", "priority": "P0", "status": "fixed", "discovery_date": "2026-01-01"},
            {"id": "C-001", "title": "B", "priority": "P0", "status": "fixed", "discovery_date": "2026-01-01"},
        ]
        warnings = self.migrator.validate(issues)
        self.assertTrue(any("重复" in w for w in warnings))

    def test_validate_detects_missing_fields(self):
        issues = [{"id": "C-001", "title": ""}]  # 缺少 priority, status, discovery_date; title 为空
        warnings = self.migrator.validate(issues)
        self.assertTrue(len(warnings) >= 1)

    def test_validate_clean_data(self):
        issues = [
            {"id": "C-001", "title": "A", "priority": "P0", "status": "fixed", "discovery_date": "2026-01-01"},
        ]
        warnings = self.migrator.validate(issues)
        self.assertEqual(len(warnings), 0)


# ══════════════════════════════════════════════════════════════════════════════
# Export 测试
# ══════════════════════════════════════════════════════════════════════════════


class TestExporter(unittest.TestCase):
    """Export 输出格式测试."""

    def setUp(self):
        self.config_path = _write_temp_config(VALID_CONFIG_YAML)
        self.config = Config(self.config_path)
        self.db = _make_db()

        # 插入测试数据（纯数字编号）
        self.db.add_issue(Issue(
            id="001", title="临界问题", priority="P0", status="fixed",
            discovery_date="2026-01-19", fix_date="2026-01-19",
            file_path="src/core/test.cpp", description="临界描述",
        ))
        self.db.add_issue(Issue(
            id="002", title="中等问题", priority="P2", status="pending",
            discovery_date="2026-02-01", file_path="src/hal/test.cpp",
            description="中等描述", estimated_hours=2.0,
        ))
        self.db.add_issue(Issue(
            id="003", title="架构问题", priority="P2", status="fixed",
            discovery_date="2026-02-01", fix_date="2026-02-02",
            description="架构描述", actual_hours=4.0,
        ))
        self.db.add_issue(Issue(
            id="004", title="测试问题", priority="P3", status="planned",
            discovery_date="2026-02-03", description="测试描述",
        ))

    def tearDown(self):
        self.db.close()
        os.unlink(self.config_path)

    def test_export_contains_all_issues(self):
        exporter = Exporter(self.config, self.db)
        fd, output_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            exporter.export(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 所有编号应出现
            self.assertIn("001", content)
            self.assertIn("002", content)
            self.assertIn("003", content)
            self.assertIn("004", content)
        finally:
            os.unlink(output_path)

    def test_export_has_statistics_section(self):
        exporter = Exporter(self.config, self.db)
        fd, output_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            exporter.export(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("## 总体统计", content)
            self.assertIn("按优先级统计", content)
            self.assertIn("问题概要汇总", content)
        finally:
            os.unlink(output_path)

    def test_export_has_priority_sections(self):
        exporter = Exporter(self.config, self.db)
        fd, output_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            exporter.export(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("Critical Priority", content)
            self.assertIn("Medium Priority", content)
            self.assertIn("Low Priority", content)
            # 不再有 Architecture/Test 独立段
            self.assertNotIn("Architecture Issues", content)
            self.assertNotIn("Test Issues", content)
        finally:
            os.unlink(output_path)

    def test_export_status_emojis(self):
        exporter = Exporter(self.config, self.db)
        fd, output_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            exporter.export(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("✅ 已修复", content)
            self.assertIn("❌ 待修复", content)
            self.assertIn("📋 待规划", content)
        finally:
            os.unlink(output_path)

    def test_export_header_uses_project_name(self):
        exporter = Exporter(self.config, self.db)
        fd, output_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            exporter.export(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("TestProject", content)
            # 不应出现硬编码的项目名
            self.assertNotIn("WeldSmart Pro", content)
        finally:
            os.unlink(output_path)

    def test_export_sequential_numbering_spec(self):
        exporter = Exporter(self.config, self.db)
        fd, output_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            exporter.export(output_path)
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 编号规则说明应为序号模式
            self.assertIn("全局自动递增序号", content)
        finally:
            os.unlink(output_path)


# ══════════════════════════════════════════════════════════════════════════════
# GitHub Sync 测试 (mock subprocess)
# ══════════════════════════════════════════════════════════════════════════════


class TestGithubSync(unittest.TestCase):
    """GitHub 同步逻辑测试（mock gh 命令）."""

    def setUp(self):
        self.config_path = _write_temp_config(VALID_CONFIG_YAML)
        self.config = Config(self.config_path)
        self.db = _make_db()

    def tearDown(self):
        self.db.close()
        os.unlink(self.config_path)

    def test_sync_dry_run_no_pending(self):
        """无待同步条目时，dry-run 输出正确."""
        syncer = GithubSync(self.config, self.db)
        result = syncer.sync(dry_run=True)
        self.assertEqual(result["pending"], 0)

    def test_sync_dry_run_with_pending(self):
        """有待同步条目时，dry-run 列出条目但不执行."""
        self.db.add_issue(Issue(
            id="001", title="已修复问题", priority="P2", status="fixed",
            discovery_date="2026-01-01", github_issue_id=42,
        ))
        syncer = GithubSync(self.config, self.db)
        result = syncer.sync(dry_run=True)
        self.assertEqual(result["pending"], 1)
        # dry-run 不会记录成功/失败
        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 0)

    @patch("issue_tracker.core.github_sync.GithubSync._close_github_issue")
    def test_sync_success(self, mock_close):
        """模拟 gh 关闭成功."""
        mock_close.return_value = (True, None)

        self.db.add_issue(Issue(
            id="001", title="已修复", priority="P2", status="fixed",
            discovery_date="2026-01-01", github_issue_id=42,
        ))

        syncer = GithubSync(self.config, self.db)
        result = syncer.sync(dry_run=False)

        self.assertEqual(result["success"], 1)
        self.assertEqual(result["failed"], 0)
        mock_close.assert_called_once_with(42, "自动同步: 001 已修复")

        # 再次同步应无待处理（已记录日志）
        result2 = syncer.sync(dry_run=True)
        self.assertEqual(result2["pending"], 0)

    @patch("issue_tracker.core.github_sync.GithubSync._close_github_issue")
    def test_sync_failure(self, mock_close):
        """模拟 gh 关闭失败."""
        mock_close.return_value = (False, "网络超时")

        self.db.add_issue(Issue(
            id="001", title="已修复", priority="P2", status="fixed",
            discovery_date="2026-01-01", github_issue_id=42,
        ))

        syncer = GithubSync(self.config, self.db)
        result = syncer.sync(dry_run=False)

        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 1)

        # 失败后再次同步仍应待处理（未记录 success）
        result2 = syncer.sync(dry_run=True)
        self.assertEqual(result2["pending"], 1)

    def test_sync_github_disabled(self):
        """GitHub 禁用时应直接返回."""
        # 修改配置禁用 github
        disabled_yaml = VALID_CONFIG_YAML.replace("enabled: true", "enabled: false")
        path = _write_temp_config(disabled_yaml)
        try:
            config = Config(path)
            syncer = GithubSync(config, self.db)
            result = syncer.sync()
            self.assertEqual(result["pending"], 0)
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════════════════
# GitHub Sync 查询逻辑测试
# ══════════════════════════════════════════════════════════════════════════════


class TestGithubSyncQuery(unittest.TestCase):
    """测试 get_pending_github_sync 查询条件."""

    def setUp(self):
        self.db = _make_db()

    def tearDown(self):
        self.db.close()

    def test_pending_sync_excludes_no_github_id(self):
        """无 github_issue_id 的 fixed 条目不应出现."""
        self.db.add_issue(Issue(
            id="001", title="无GH", priority="P2", status="fixed",
            discovery_date="2026-01-01", github_issue_id=None,
        ))
        pending = self.db.get_pending_github_sync()
        self.assertEqual(len(pending), 0)

    def test_pending_sync_excludes_non_fixed(self):
        """非 fixed 状态的条目不应出现."""
        self.db.add_issue(Issue(
            id="001", title="未修复", priority="P2", status="pending",
            discovery_date="2026-01-01", github_issue_id=42,
        ))
        pending = self.db.get_pending_github_sync()
        self.assertEqual(len(pending), 0)

    def test_pending_sync_includes_fixed_with_gh_id(self):
        """fixed + 有 github_issue_id + 未同步 → 应出现."""
        self.db.add_issue(Issue(
            id="001", title="待同步", priority="P2", status="fixed",
            discovery_date="2026-01-01", github_issue_id=42,
        ))
        pending = self.db.get_pending_github_sync()
        self.assertEqual(len(pending), 1)

    def test_pending_sync_excludes_already_synced(self):
        """已成功同步过的条目不应再次出现."""
        self.db.add_issue(Issue(
            id="001", title="已同步", priority="P2", status="fixed",
            discovery_date="2026-01-01", github_issue_id=42,
        ))
        # 记录同步成功日志
        self.db.log_github_sync("001", 42, "close", "success")

        pending = self.db.get_pending_github_sync()
        self.assertEqual(len(pending), 0)


if __name__ == "__main__":
    unittest.main()
