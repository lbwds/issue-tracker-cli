# UI 交互升级设计规范

> **状态**: 已实现 (v2.2.0)
> **日期**: 2026-02-05
> **适用于**: `iss-ui`（ui.py）和 `iss-project`（project_init.py）的交互层

---

## 目录

1. [目标](#1-目标)
2. [技术决策](#2-技术决策)
3. [新增模块 `core/terminal.py`](#3-新增模块-coreterminalpy)
4. [配色方案](#4-配色方案)
5. [Submit/Cancel 模式](#5-submitcancel-模式)
6. [ui.py 改造映射](#6-uipy-改造映射)
7. [project_init.py 改造映射](#7-project_initpy-改造映射)
8. [分步实现路径](#8-分步实现路径)
9. [约束与兼容性](#9-约束与兼容性)

---

## 1. 目标

1. 所有菜单、信息展示加入 ANSI 配色，重点元素突出
2. 菜单选择改为 ↑↓ 方向键 + Enter 确认 + Esc 回退（主页 Esc 退出）
3. 是/否确认改为 ←→ 方向键切换
4. 编辑配置后提供 **提交 / 取消** 选择（变更不立即写盘）

---

## 2. 技术决策

| 交互类型 | 输入方式 | 原因 |
|---------|---------|------|
| 菜单选择 | raw `getch()` + ↑↓ + Tab | 无需文本输入，raw 完全安全 |
| 是/否确认 | raw `getch()` + ←→ | 无需文本输入 |
| 文本输入（项目名、模板等） | 系统 `input()` + 彩色 prompt | **保持 IME 兼容**，中文输入正常 |
| 等待任意键 | raw `getch()` 单次读 | 简单阻塞 |

**键别名**: Tab = Down（下一项），Shift+Tab = Up（上一项）。

**依赖约束**: 仅依赖 stdlib — `termios`, `tty`, `select`, `os`, `sys`, `re`。`setup.py` 无需修改。

---

## 3. 新增模块 `core/terminal.py`

### 3.1 模块结构

```
core/terminal.py
├── C 类              — ANSI 转义常量汇总
├── c(text, *styles)  — 施加样式（非 TTY 自动静默跳过）
├── Key 类            — 键名常量
├── getch()           — raw 读单键 + CSI 序列解析
├── _erase_above(n)   — 上移并清空 N 行（菜单重绘用）
│
├── 显示辅助
│   ├── hr(ch, color)       — 水平线
│   ├── title_bar(title)    — 带 ━ 线的标题栏
│   ├── label(text)         — 标签着色
│   ├── value(text)         — 值着色
│   ├── ok(text)            — 成功绿色
│   ├── warn(text)          — 警告黄色
│   ├── err(text)           — 错误红色
│   └── dim(text)           — 暗灰色
│
└── 交互组件
    ├── wait_key(msg)                                        → None
    ├── menu(title, options, *, footer, separators, item_colors) → int | None
    ├── input_line(prompt, default)                          → str | None
    └── yes_no(prompt, default)                              → bool | None
```

### 3.2 API 详解

#### `C` 类 — ANSI 常量

所有常量为字符串，可直接拼接使用。模块内不需要外部引用，`c()` 是首选接口。

```python
class C:
    RESET       = "\033[0m"
    BOLD        = "\033[1m"
    DIM         = "\033[2m"
    # 前景色
    RED         = "\033[91m"    # bright red
    GREEN       = "\033[92m"    # bright green
    YELLOW      = "\033[93m"    # bright yellow
    CYAN        = "\033[96m"    # bright cyan
    WHITE       = "\033[97m"    # bright white
    GRAY        = "\033[90m"    # dark gray
```

#### `c(text, *styles) → str`

对文本施加一组样式，非 TTY 时原样返回。

```python
c("提交", C.GREEN, C.BOLD)   # → "\033[92m\033[1m提交\033[0m"
```

#### `Key` 类 — 键名常量

```python
class Key:
    UP      = "UP"
    DOWN    = "DOWN"
    LEFT    = "LEFT"
    RIGHT   = "RIGHT"
    ENTER   = "ENTER"
    ESC     = "ESC"
    TAB     = "TAB"        # \x09
    BTAB    = "BTAB"       # Shift+Tab  \x1b[Z
    BS      = "BS"         # Backspace  \x7f
```

#### `getch() → str`

Raw 模式单键读取。解析规则：

| 输入序列 | 返回值 |
|---------|--------|
| `\x1b[A` | `Key.UP` |
| `\x1b[B` | `Key.DOWN` |
| `\x1b[C` | `Key.RIGHT` |
| `\x1b[D` | `Key.LEFT` |
| `\x1b[Z` | `Key.BTAB` |
| `\x0d` / `\x0a` | `Key.ENTER` |
| `\x1b`（无后续字节） | `Key.ESC` |
| `\x09` | `Key.TAB` |
| `\x7f` | `Key.BS` |
| `\x03` (Ctrl+C) | 抛出 `KeyboardInterrupt` |
| `\x04` (Ctrl+D) | 返回 `Key.ESC` |
| 其他单字节 | 原字符返回 |

使用 `select` 实现非阻塞等待后续字节（判断 ESC 是独立按键还是 CSI 序列前缀）。

#### `_erase_above(n)`

将光标上移 `n` 行并逐行清除，用于菜单重绘时擦去上一次的输出。

#### `wait_key(msg)`

以 dim 灰色打印 `msg`，然后调 `getch()` 阻塞等待任意键，返回前清除提示行。

#### `menu(title, options, *, footer=None, separators=None, item_colors=None) → int | None`

箭头键菜单，核心交互组件。

**参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `title` | `str` | 菜单标题（含 `●` dirty 标记时传入） |
| `options` | `list[str]` | 选项文本列表 |
| `footer` | `str \| None` | 底部提示文字（暗色渲染） |
| `separators` | `set[int] \| None` | 不可选的分隔行索引集合（渲染为 `──────`） |
| `item_colors` | `dict[int, str] \| None` | 指定索引的未选中状态颜色（如末项 Submit=绿、Cancel=红） |

**行为**:

```
┌ title ━━━━━━━━━━━━━━━━━━━━━━━━━━┐
│  ▸ 查看当前配置                  │  ← 选中行: ▸ Cyan Bold，文字 White Bold
│    编辑默认优先级列表             │  ← 未选中: Gray
│  ─────────────────────────────── │  ← separators 索引渲染为分隔行
│    ✓ 提交保存                    │  ← item_colors 绿色
│    ✗ 取消                        │  ← item_colors 红色
│  ↑↓ 选择  Enter 确认  Esc 返回   │  ← footer (dim)
└──────────────────────────────────┘
```

- Enter → 返回当前选中索引（`int`）
- Esc → 返回 `None`
- ↑↓ / Tab / Shift+Tab → 移动光标（自动跳过 `separators`）
- 每次键入后重绘整个菜单（`_erase_above` 擦旧 + 重新输出）

#### `input_line(prompt, default=None) → str | None`

用 `sys.stdout.write` 打印彩色 prompt（标签 Cyan + 默认值 White Bold），再调系统 `input()` 读取用户输入。

- 用户回车且无输入 + 有 default → 返回 default
- 用户回车且无输入 + 无 default → 返回 `None`
- 非 TTY 时也正常工作（颜色静默跳过）

#### `yes_no(prompt, default=True) → bool | None`

Raw 模式交互，实时切换渲染。

```
  启用 GitHub 同步?   ● 是    ○ 否    ← default=True, 选中"是"
                      ← 绿色Bold      ← 红色
```

- ←→ 切换 是/否，实时重绘
- Enter → 返回 `bool`
- Esc → 返回 `None`（调用方按需处理为"取消"）

---

## 4. 配色方案

| 元素 | 样式描述 | ANSI 序列 |
|------|---------|-----------|
| 标题栏文字 | Bold White | `\033[1m\033[97m` |
| 栏线 ━━━ | Cyan | `\033[96m` |
| 选中项 ▸ | Cyan Bold | `\033[96m\033[1m` |
| 选中项文字 | White Bold | `\033[1m\033[97m` |
| 未选中项 | Gray | `\033[90m` |
| 标签 (Label) | Cyan | `\033[96m` |
| 值 (Value) | White Bold | `\033[1m\033[97m` |
| ✓ 成功 | Green Bold | `\033[92m\033[1m` |
| ⚠ 警告 | Yellow | `\033[93m` |
| ✗ 错误 | Red Bold | `\033[91m\033[1m` |
| 提交选项(未选中) | Green | `\033[92m` |
| 取消选项(未选中) | Red | `\033[91m` |
| ● 是 (选中) | Green Bold | `\033[92m\033[1m` |
| ● 否 (选中) | Red Bold | `\033[91m\033[1m` |
| 页脚提示 | Dim Gray | `\033[2m\033[90m` |
| 分隔行 | Dim Gray | `\033[2m\033[90m` |

所有样式均通过 `c()` 函数施加，非 TTY 环境自动跳过。

---

## 5. Submit/Cancel 模式

适用于所有编辑子菜单。核心思路：编辑过程不写盘，仅在用户明确确认时写入。

### 5.1 流程

```
进入编辑菜单
    │
    ▼
deep copy(data) → working_copy          ← 快照原始状态
    │
    ▼
菜单循环 (使用 working_copy)
    │  用户编辑 → 修改 working_copy
    │  dirty = (working_copy != 原始快照)
    │  标题显示: "项目配置编辑 ●"        ← dirty 时附加 ●
    │
    ├── 选 "✓ 提交保存"
    │       │
    │       ▼
    │   save_config(path, working_copy)  ← 写盘
    │   返回上层菜单
    │
    └── 选 "✗ 取消" / 按 Esc
            │
            ▼
        丢弃 working_copy               ← 不写盘
        返回上层菜单
```

### 5.2 实现要点

- `menu()` 选项列表末尾固定追加两项，通过 `separators` 在前面加一条分隔线
- 提交项用 `item_colors={N: C.GREEN}` 绿色标注；取消项用红色标注
- dirty 检测：对 `working_copy` 做 `copy.deepcopy` 保存为 `original`，每次循环开头比较 `working_copy != original`

### 5.3 适用范围

| 入口 | 所在文件 | 编辑对象 |
|------|---------|---------|
| `_global_config_menu` | `ui.py` | GlobalConfig 默认值（优先级、状态、模板） |
| `edit_menu` | `project_init.py` | 项目配置 dict（项目信息、优先级、状态、导出） |
| `_edit_github` | `project_init.py` | `data["github"]` 子树 |

---

## 6. ui.py 改造映射

删除旧 `_menu()` 引擎函数（数字输入菜单），全部替换为 `terminal.menu()`。

| 函数 | 改造要点 |
|------|---------|
| `main_ui()` | `menu()` 循环，ESC 退出。动态选项（当前项目配置）保持条件追加逻辑 |
| `_view_paths()` | `title_bar` + `label`/`value`/`ok`/`err` 格式化路径信息 + `wait_key()` 结尾 |
| `_global_config_menu()` | deep copy → 编辑循环 menu（选项含当前值预览）→ Submit/Cancel；dirty 时标题附加 `●` |
| `_view_env_info()` | 彩色 `label`/`value` 信息展示 + `wait_key()` 结尾 |
| `_project_mgmt_menu()` | `menu()` 子菜单，选项为查看/备份/恢复 |
| `backup()` | 项目列表 → `menu()` 选择 → 执行备份 → `ok()` 消息 + `wait_key()` |
| `restore()` | 备份列表 → `menu()` 选择 → 内容预览 → `yes_no()` 确认 → 执行恢复 |
| `_github_config_menu()` | `menu()` 子菜单，选项为检查登录/绑定仓库 |
| `_check_gh_login()` | 原地彩色输出 gh 状态 + `wait_key()` 结尾 |
| `_bind_gh_repo()` | 项目 `menu()` → 仓库 `menu()`（末项"手动输入"）→ `input_line()` 读仓库名 |

---

## 7. project_init.py 改造映射

### 删除

| 函数 | 原因 |
|------|------|
| `_read_input()` | 替换为 `input_line()` |
| `_yes_no()` | 替换为 `yes_no()` |
| `_edit_list()` | 替换为 `input_line()` + 逗号分割 |

### 保留不变

| 函数 | 原因 |
|------|------|
| `render_yaml()` | 公开接口，ui.py 依赖 |
| `load_yaml()` | 公开接口 |
| `save_config()` | 公开接口 |
| `_sanitize_name()` | 纯工具函数 |

### 改造

| 函数 | 改造要点 |
|------|---------|
| `guided_create()` | `input_line()` 逐步输入项目 ID / 名称 / 列表；`yes_no()` 布尔字段；末尾 menu 三项：`查看预览` / `✓ 提交` / `✗ 取消` |
| `edit_menu()` | deep copy → menu（选项含当前值预览）→ Submit/Cancel；dirty `●` 标记。子菜单项返回后回到本 menu 继续循环 |
| `_edit_project_info()` | `input_line()` 分别输入 ID（带纯数字校验重试）和名称；修改传入的 working copy dict |
| `_edit_github()` | menu 子菜单；切换项（enabled / close_on_fix）直接标注 `[开启]`/`[关闭]`；文本项用 `input_line()`。修改传入的 dict，**不写盘**（由上层 Submit 写盘） |
| `_edit_export()` | `input_line()` 输入导出路径；修改传入的 dict，不写盘 |

---

## 8. 分步实现路径

### Step 1: 创建 `core/terminal.py`

实现 [§3 全部 API](#3-新增模块-coreterminalpy)。此模块独立，不依赖项目其他代码，可单独验证：

```bash
PYTHONPATH=src python3 -c "
from issue_tracker.core.terminal import menu, yes_no, input_line, C, c
print(c('import OK', C.GREEN, C.BOLD))
"
```

### Step 2: 改写 `ui.py`

按 [§6 改造映射](#6-uipy-改造映射) 逐函数替换。删除旧 `_menu()` 引擎。

### Step 3: 改写 `project_init.py`

按 [§7 改造映射](#7-project_initpy-改造映射) 执行删除/改造/保留。

### Step 4: 测试与冒烟

```bash
# 回归测试（不涉及交互 UI，应全部通过）
python3 -m unittest discover -s tests -v   # 55 tests

# import 验证
PYTHONPATH=src python3 -c "from issue_tracker.core.terminal import menu, yes_no, input_line; print('import OK')"

# 手动冒烟（需 TTY）
PYTHONPATH=src python3 -m issue_tracker.ui            # 验证 iss-ui 菜单
PYTHONPATH=src python3 -m issue_tracker.project_init  # 验证 iss-project
```

---

## 9. 约束与兼容性

| 约束 | 说明 |
|------|------|
| 仅 stdlib | `termios`, `tty`, `select`, `os`, `sys`, `re` 均为 Linux stdlib |
| setup.py 不变 | 无新外部依赖 |
| 非 TTY 安全 | `c()` 静默跳过颜色；`menu()`/`yes_no()` 需 TTY 才能 raw 读键 |
| 公开接口稳定 | `render_yaml()` / `load_yaml()` / `save_config()` 签名和行为不变 |
| IME 兼容 | 所有需要中文输入的场景使用系统 `input()`，不走 raw 模式 |

---

**文档结束**
