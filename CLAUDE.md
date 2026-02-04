# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

**Issue Tracker CLI** 是一个通用的 Issue 追踪命令行工具，支持 SQLite 本地存储和 Markdown 导出。设计目标是通用性 - 换项目只需替换 `config.yaml` 和对应的 migrator 插件即可复用。

- **语言**: Python 3.10+
- **数据库**: SQLite3 (内置)
- **外部依赖**: 仅 PyYAML + `gh` CLI (GitHub 同步可选)

---

## 构建与测试

### 安装
```bash
# 开发模式安装（推荐）
pip install -e .

# 构建分发包
pip install build
python3 -m build
```

### 运行测试
```bash
# 使用 pytest
python3 -m pytest tests/ -v

# 使用 unittest
python3 -m unittest discover -s tests -v

# 带覆盖率
python3 -m pytest tests/ --cov=src/issue_tracker
```

### 本地运行（未安装时）
```bash
python3 src/issue_tracker/cli.py <命令>
```

---

## 代码架构

### 目录结构
```
src/issue_tracker/
├── cli.py                  # CLI 入口（参数解析、命令分发）
├── core/
│   ├── model.py           # Issue 数据类
│   ├── config.py          # 配置加载与校验
│   ├── database.py        # SQLite CRUD 封装
│   ├── exporter.py        # Markdown 导出器
│   └── github_sync.py     # GitHub 同步 (gh CLI)
└── migrators/
    ├── __init__.py        # BaseMigrator 抽象基类
    └── weldsmart_migrator.py  # WeldSmart 格式解析器
```

### 数据模型（Issue 数据类）
```python
@dataclass
class Issue:
    id: str                      # 问题编号 (如 C-001)
    title: str                   # 标题
    priority: str                # 优先级 (P0/P1/P2/P3)
    status: str                  # 状态 (pending/in_progress/planned/fixed/n_a)
    discovery_date: str          # 发现日期 YYYY-MM-DD
    fix_date: str | None         # 修复日期
    file_path: str | None        # 文件路径（逗号分隔）
    location: str | None         # 位置描述
    description: str | None      # 问题描述
    impact: str | None           # 影响
    fix_plan: str | None         # 修复方案
    estimated_hours: float | None
    actual_hours: float | None
    phase: str | None
    github_issue_id: int | None  # GitHub Issue 编号
```

### 数据库 Schema
核心表 `issues`，带索引：`priority`, `status`, `discovery_date`, `github_issue_id`

视图：
- `v_pending`: 待处理问题 (`status IN ('pending', 'in_progress', 'planned')`)
- `v_summary`: 概要汇总

同步日志表 `github_sync_log`: 记录 GitHub 同步历史，避免重复操作。

---

## 通用化设计

### 核心思想
| 组成部分 | 是否通用 | 处理方式 |
|---------|---------|---------|
| 核心表结构 | ✅ 通用 | 直接用 |
| CLI 命令集 | ✅ 通用 | 直接用 |
| GitHub 同步逻辑 | ✅ 通用 | 直接用 |
| 编号体系 | ❌ 项目特定 | `config.yaml` |
| 优先级/状态枚举 | ❌ 项目特定 | `config.yaml` |
| 迁移脚本 | ❌ 项目特定 | migrator 插件 |
| Export 格式 | ❌ 项目特定 | 参数化 |

### 新项目接入步骤
1. 复制 `config.example.yaml` 为 `config.yaml`，修改项目配置
2. 实现 `BaseMigrator` 子类解析项目特定格式
3. 使用 `migrate --migrator <name>` 导入数据

---

## 常用命令

| 命令 | 功能 | 示例 |
|------|------|------|
| `add` | 新增问题 | `issue-tracker add --id M-037 --title "..."` |
| `update` | 更新字段/状态 | `issue-tracker update M-037 --status fixed` |
| `query` | 多条件查询 | `issue-tracker query --status pending --priority P2` |
| `list` | 简洁列表 | `issue-tracker list --status pending` |
| `stats` | 统计概览 | `issue-tracker stats` |
| `export` | 生成 Markdown | `issue-tracker export` |
| `sync` | 同步到 GitHub | `issue-tracker sync --dry-run` |
| `migrate` | 导入数据 | `issue-tracker migrate --source file.md --migrator weldsmart` |

### Migrator 插件接口
```python
class BaseMigrator(ABC):
    @abstractmethod
    def parse(self, source_path: str) -> list[dict]:
        """解析源文件，返回 issue 字典列表."""
        raise NotImplementedError
```

---

## 配置文件（config.yaml）

```yaml
project:
  name: "Project Name"
  db_path: "path/to/issues.db"  # 相对于 git root

id_rules:
  format: "{prefix}-{num:03d}"
  prefixes:
    C: { priority: P0, label: "Critical" }
    H: { priority: P1, label: "High" }
    M: { priority: P2, label: "Medium" }
    L: { priority: P3, label: "Low" }

priorities: [P0, P1, P2, P3]
statuses: [pending, in_progress, planned, fixed, n_a]

github:
  enabled: true
  close_on_fix: true
  comment_template: "自动同步: {issue_id} 已修复"

export:
  output: "docs/project/issues.md"
```

---

## 相关文档

- 技术设计: `docs/技术设计方案.md` - 完整架构设计
- 用户手册: `docs/使用指导.md` - 详细使用说明
