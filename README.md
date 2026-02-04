# Issue Tracker CLI

> 通用 Issue 追踪命令行工具，支持 SQLite 本地存储和 Markdown 导出

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 特性

- **📦 零依赖外部数据库** - 使用 SQLite，无需额外服务
- **🔄 双向同步** - Markdown ↔ SQLite 双向转换
- **🔌 插件化架构** - 通过 migrator 插件支持不同格式
- **🐙 GitHub 集成** - 自动关闭已修复的 GitHub Issue
- **⚡ 通用设计** - 换项目只需替换 `config.yaml`

## 安装

### 方式 1: pip 安装（推荐）

```bash
pip install issue-tracker-cli
```

### 方式 2: Git Submodule

```bash
git submodule add https://github.com/your-org/issue-tracker-cli.git tools/issue-tracker
cd tools/issue-tracker
pip install -e .
```

### 方式 3: 直接运行

```bash
git clone https://github.com/your-org/issue-tracker-cli.git
cd issue-tracker-cli
python3 src/issue_tracker/cli.py --help
```

## 快速开始

### 1. 创建配置文件

从示例复制并修改：

```bash
cp config.example.yaml config.yaml
```

### 2. 迁移现有数据

```bash
issue-tracker migrate \
    --source all-issues.md \
    --migrator weldsmart
```

### 3. 查询问题

```bash
# 查看统计
issue-tracker stats

# 查询待处理问题
issue-tracker query --status pending

# 详细模式
issue-tracker query --id M-037 --detail
```

## 命令概览

| 命令 | 功能 | 示例 |
|------|------|------|
| `add` | 新增问题 | `issue-tracker add --id M-037 --title "..."` |
| `update` | 更新字段/状态 | `issue-tracker update M-037 --status fixed` |
| `query` | 多条件查询 | `issue-tracker query --priority P2 --status pending` |
| `list` | 简洁列表 | `issue-tracker list --status pending` |
| `stats` | 统计概览 | `issue-tracker stats` |
| `export` | 生成 Markdown | `issue-tracker export` |
| `sync` | 同步到 GitHub | `issue-tracker sync --dry-run` |
| `migrate` | 导入数据 | `issue-tracker migrate --source file.md --migrator name` |

详见 [使用指导](docs/使用指导.md)。

## 配置文件

```yaml
project:
  name: "Your Project"
  db_path: "issues.db"

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
  comment_template: "Auto-sync: {issue_id} fixed"

export:
  output: "all-issues.md"
```

## 新项目接入

1. **创建 `config.yaml`** - 定义编号规则和优先级映射
2. **实现 Migrator 插件** - 继承 `BaseMigrator` 解析你的格式

```python
from issue_tracker.migrators.base import BaseMigrator

class MyMigrator(BaseMigrator):
    def parse(self, source_path: str) -> list[dict]:
        # 实现解析逻辑
        return issues
```

3. **使用自定义 migrator**:

```bash
issue-tracker migrate --source my-issues.md --migrator mymigrator
```

## 开发

### 运行测试

```bash
python3 -m pytest tests/ -v
```

### 构建

```bash
pip install build
python3 -m build
```

## 文档

- [技术设计方案](docs/技术设计方案.md) - 架构设计与实现细节
- [使用指导](docs/使用指导.md) - 完整使用手册

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

## 贡献

欢迎提交 Issue 和 Pull Request！
