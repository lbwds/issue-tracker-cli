# Issue Tracker CLI

> 通用 Issue 追踪命令行工具，支持 SQLite 本地存储和 Markdown 导出

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 特性

- **多项目支持** - 通过 `-p project_id` 切换不同项目，数据独立存储
- **编号自动分配** - 全局自动递增序号，无需手动管理
- **📦 零依赖外部数据库** - 使用 SQLite，无需额外服务
- **🔄 双向同步** - Markdown ↔ SQLite 双向转换
- **🔌 插件化架构** - 通过 migrator 插件支持不同格式
- **🐙 GitHub 集成** - 自动关闭已修复的 GitHub Issue

## 安装

### 从 PyPI 安装（推荐）

```bash
pip install issue-tracker-cli
```

### 从 GitHub 安装

**使用 SSH**（推荐，已配置 SSH 密钥）：
```bash
pip install git+ssh://git@github.com/lbwds/issue-tracker-cli.git@v1.2.2
```

**使用 HTTPS + Personal Access Token**：
```bash
# 1. 生成 Token: GitHub Settings → Developer settings → Personal access tokens
# 2. 使用 Token 安装
pip install git+https://YOUR_TOKEN@github.com/lbwds/issue-tracker-cli.git@v1.2.2
```

### 开发模式安装

```bash
git clone git@github.com:lbwds/issue-tracker-cli.git
cd issue-tracker-cli
pip install -e .
```

## 快速开始

### 推荐方式：项目目录配置（无需 `-p` 参数）

在你的项目根目录创建 `config.yaml`：

```bash
cd /path/to/your/project

cat > config.yaml << 'EOF'
project:
  id: "001"
  name: "YourProject"

id_rules:
  format: "{num:03d}"

priorities: [P0, P1, P2, P3]
statuses: [pending, in_progress, planned, fixed, n_a]

github:
  enabled: true
  close_on_fix: true
  comment_template: "自动同步: {issue_id} 已修复"

export:
  output: "exports/issues.md"
EOF
```

然后直接在项目目录中使用命令（无需指定 `-p` 参数）：

```bash
# 新增问题
issue-tracker add --title "登录功能异常" --priority P0

# 查询问题
issue-tracker query --status pending

# 统计
issue-tracker stats
```

**工作原理**：工具会自动查找当前目录下的 `config.yaml`，无需每次指定项目。

---

### 其他使用方式

#### 方式 2: 使用 `-p` 参数切换项目

适合需要管理多个独立项目的场景：

```bash
# 设置环境变量（可选，默认: ~/issue-tracker-cli）
export ISSUE_TRACKER_HOME=$HOME/issue-tracker-cli
mkdir -p $ISSUE_TRACKER_HOME/.config

# 创建项目配置文件
cat > $ISSUE_TRACKER_HOME/.config/001_ProjectA.yaml << 'EOF'
project:
  id: "001"
  name: "ProjectA"
...
EOF

# 使用 -p 参数切换项目
issue-tracker -p 001 add --title "..." --priority P2
issue-tracker -p 002 add --title "..." --priority P1
```

#### 方式 3: 使用 `-c` 参数指定配置路径

```bash
issue-tracker -c /path/to/config.yaml add --title "..." --priority P2
```

---

### 配置文件查找逻辑

工具按以下优先级查找配置文件：

```
1. -c <config> 参数         → 直接使用指定路径
2. -p <project_id> 参数     → 搜索 ISSUE_TRACKER_HOME/.config/{project_id}_*.yaml
3. (无参数) 自动查找:
   a) 当前目录/config.yaml   → 推荐方式，适合单项目使用
   b) .config/ 唯一配置文件  → 多项目时自动使用唯一配置
   c) git root/config.yaml   → 兼容旧模式
```

## 命令概览

| 命令 | 功能 | 示例 |
|------|------|------|
| `add` | 新增问题 | `issue-tracker add --title "..." --priority P2` |
| `update` | 更新字段/状态 | `issue-tracker update 001 --status fixed` |
| `query` | 多条件查询 | `issue-tracker query --priority P2 --status pending` |
| `list` | 简洁列表 | `issue-tracker list --status pending` |
| `stats` | 统计概览 | `issue-tracker stats` |
| `export` | 生成 Markdown | `issue-tracker export` |
| `sync` | 同步到 GitHub | `issue-tracker sync --dry-run` |
| `migrate` | 导入数据 | `issue-tracker migrate --source file.md --migrator weldsmart` |

详见 [使用指导](docs/使用指导.md)。

## 多项目管理

### 目录结构

```
~/issue-tracker-cli/              # ISSUE_TRACKER_HOME
├── .config/                      # 项目配置目录
│   ├── 001_WeldSmart.yaml        # 项目 001 配置
│   └── 002_AnotherProject.yaml   # 项目 002 配置
└── data/                         # 数据库目录
    ├── 001_WeldSmart_Pro.db      # 项目 001 数据库
    └── 002_Another_Project.db    # 项目 002 数据库
```

### 项目切换

```bash
# 切换到项目 001
issue-tracker -p 001 stats

# 切换到项目 002
issue-tracker -p 002 query --status pending

# 手动指定配置文件
issue-tracker -c /path/to/config.yaml query
```

## 配置文件

```yaml
project:
  id: "001"                      # 项目编号（纯数字）
  name: "MyProject"

id_rules:
  format: "{num:03d}"            # 编号格式（全局自动递增）

priorities: [P0, P1, P2, P3]     # 优先级列表
statuses: [pending, in_progress, planned, fixed, n_a]  # 状态列表

github:
  enabled: true                  # 是否启用 GitHub 同步
  close_on_fix: true             # 修复后自动关闭 Issue
  comment_template: "自动同步: {issue_id} 已修复"

export:
  output: "exports/issues.md"    # 导出路径（相对于 ISSUE_TRACKER_HOME）
```

## 迁移现有数据

如果已有 Issue 数据在 Markdown 文件中，可以使用 migrate 命令导入：

```bash
issue-tracker migrate \
    --source all-issues.md \
    --migrator weldsmart
```

导入后，编号会自动重新分配为全局递增序号。

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
