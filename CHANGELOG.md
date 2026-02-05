# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式。

---

## [2.2.0] — 2026-02-05

### 新增
- `core/terminal.py` — 终端交互基础模块（仅 stdlib 依赖）
  - `menu()`: ↑↓ / Tab 方向键菜单，支持分隔行和项颜色自定义
  - `yes_no()`: ←→ 实时切换确认
  - `input_line()`: 彩色 prompt + 系统 `input()`，保持 IME 兼容
  - `getch()`: raw 单键读 + CSI 序列解析，`select` 判断独立 ESC
  - ANSI 配色套件：`C` 常量类 + `c()` 着色函数（非 TTY 静默跳过）
  - 显示辅助：`title_bar`, `label`, `value`, `ok`, `warn`, `err`, `dim`, `hr`
- `docs/UI交互设计.md` — 交互层设计规范文档

### 改造
- `ui.py`: 删除旧数字输入菜单 `_menu()`，全部替换为方向键 `menu()`；`_global_config_menu` 改为 Submit/Cancel 模式（dirty 时标题附 ` ●`）；备份/恢复用 `menu()` 选择，恢复用 `yes_no(default=False)` 确认；顶层入口捕获 KeyboardInterrupt 优雅退出
- `project_init.py`: 删除 `_read_input` / `_yes_no` / `_edit_list`；`guided_create()` 末尾三项 menu（预览/提交/取消）；`edit_menu()` 为 9 项 Submit/Cancel 菜单，子菜单编辑仅修改 working copy；`_edit_github()` 为 4 项循环子菜单，toggle 项动态标注 `[开启]/[关闭]`
- 公开接口 `render_yaml` / `load_yaml` / `save_config` 签名和行为不变
- 55 个回归测试全部通过

---

## [2.1.0] — 2026-02-05

### 新增
- `iss-project` 命令：在项目目录下引导创建或编辑 `issue-tracker.yaml`
- `iss-ui` 命令：全局管理菜单，可在任意目录下运行
  - 查看当前路径（配置/数据/备份目录及存在状态）
  - 全局工具配置（编辑 `globals.yaml` 默认优先级、状态、GitHub 评论模板）
  - 版本与环境信息（依赖检查）
  - 全局项目管理（列出、tar.gz 备份与恢复）
  - GitHub 连接配置（检查 `gh` 登录、绑定仓库到项目）
  - 当前项目配置（动态，仅当 cwd 含配置文件时显示）
- `core/paths.py`: 统一 XDG 路径解析与配置查找逻辑
- `core/global_config.py`: `globals.yaml` 全局默认值读写

### 改进
- `cli.py` 路径工具统一引用 `core/paths.py`，移除重复定义
- 文档同步更新

---

## [2.0.1] — 2026-02-04

### 新增
- 首次运行时自动创建数据存储目录（`.config/` / `data/` / `exports/`）

### 改进
- 更新安装说明，明确目录创建时机
- 添加环境变量配置说明

---

## [2.0.0] — 2026-02-04

### 新增
- **多项目支持**：通过 `-p project_id` 切换项目，每个项目独立配置和数据库
- **全局自动递增编号**：编号格式改为纯数字（001, 002, 003…），新增时自动分配，迁移时按日期排序后重分配
- **项目目录配置**：在项目根目录创建 `config.yaml` 即可使用，无需每次指定 `-p`

### 改变（Breaking）
- 配置文件格式重写：引入 `project.id` / `project.name`，`id_rules.format` 改为纯数字模板，移除旧版 prefix 机制
- 数据库和配置存储路径迁移至 `ISSUE_TRACKER_HOME`

---

## [1.2.2] — 2026-02-04

### 修复
- 配置文件查找改为运行时动态查找，修复 pip 普通安装模式下路径错误

---

## [1.2.1] — 2026-02-04

### 修复
- 导出文档生成时间精确到分钟（`YYYY-MM-DD HH:MM`），标题改为"生成时间"

---

## [1.2.0] — 2026-02-03

### 新增
- 相对时间显示：今天 / 昨天 / N 天前（超过 3 天显示具体日期）

---

## [1.1.0] — 2026-02-03

### 新增
- 配置文件自动查找：支持在当前目录和 git root 中自动查找 `config.yaml`
- `CLAUDE.md`：供 Claude Code 使用的项目指导文档

### 修复
- 修复 pip 安装后无法找到项目配置文件的问题

---

## [1.0.0] — 2026-02-03

- 初始版本，支持 WeldSmart Pro 格式迁移
- SQLite 本地存储 + Markdown 导出
- GitHub 同步（`gh` CLI）
- `add` / `update` / `query` / `list` / `stats` / `export` / `sync` / `migrate` 命令
