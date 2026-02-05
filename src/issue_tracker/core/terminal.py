"""终端交互基础模块.

提供 ANSI 配色、方向键菜单、是/否确认、彩色输入提示等组件。
仅依赖 stdlib: os, re, select, sys, termios, tty, unicodedata
"""

import os
import select
import sys
import termios
import tty
import unicodedata


# ── ANSI 转义常量 ─────────────────────────────────────────


class C:
    """ANSI 转义序列常量."""
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"


def c(text: str, *styles: str) -> str:
    """对文本施加样式，非 TTY 时原样返回."""
    if not sys.stdout.isatty():
        return text
    return "".join(styles) + text + C.RESET


# ── 键名常量 ──────────────────────────────────────────────


class Key:
    """键名常量."""
    UP    = "UP"
    DOWN  = "DOWN"
    LEFT  = "LEFT"
    RIGHT = "RIGHT"
    ENTER = "ENTER"
    ESC   = "ESC"
    TAB   = "TAB"
    BTAB  = "BTAB"   # Shift+Tab
    BS    = "BS"      # Backspace


# ── raw 单键读取 ──────────────────────────────────────────


def getch() -> str:
    """Raw 模式单键读取 + CSI 序列解析.

    Ctrl+C 抛出 KeyboardInterrupt。
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)

        if ch == "\x03":  # Ctrl+C
            raise KeyboardInterrupt

        if ch == "\x04":  # Ctrl+D
            return Key.ESC

        if ch == "\x0d" or ch == "\x0a":  # Enter
            return Key.ENTER

        if ch == "\x09":  # Tab
            return Key.TAB

        if ch == "\x7f":  # Backspace
            return Key.BS

        if ch == "\x1b":
            # 用 select 判断是否有后续字节（区分独立 ESC 与 CSI 序列前缀）
            if select.select([sys.stdin], [], [], 0.05)[0]:
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        ch3 = sys.stdin.read(1)
                        if ch3 == "A":
                            return Key.UP
                        elif ch3 == "B":
                            return Key.DOWN
                        elif ch3 == "C":
                            return Key.RIGHT
                        elif ch3 == "D":
                            return Key.LEFT
                        elif ch3 == "Z":
                            return Key.BTAB
                        # 其他 CSI 序列忽略
                        return ""
                    return ""
                # ESC + 非 '[' → 忽略
                return ""
            # 独立 ESC
            return Key.ESC

        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ── 宽度计算与终端尺寸 ────────────────────────────────────


def _visible_width(text: str) -> int:
    """计算可见宽度，CJK 全角字符计 2."""
    # 先剥离 ANSI 转义序列
    import re
    plain = re.sub(r"\033\[[0-9;]*m", "", text)
    w = 0
    for ch in plain:
        cat = unicodedata.east_asian_width(ch)
        w += 2 if cat in ("W", "F") else 1
    return w


def _term_width() -> int:
    """获取终端宽度，fallback 60."""
    try:
        return os.get_terminal_size().columns
    except (AttributeError, ValueError, OSError):
        return 60


# ── 光标操作 ──────────────────────────────────────────────


def _erase_above(n: int):
    """上移 n 行并逐行清除."""
    for _ in range(n):
        sys.stdout.write("\033[A\033[2K")
    sys.stdout.flush()


# ── 显示辅助 ──────────────────────────────────────────────


def hr(ch: str = "─", color: str = C.CYAN) -> str:
    """返回一行水平线字符串."""
    return c(ch * _term_width(), color)


def title_bar(title: str):
    """输出带 ━ 线的标题栏."""
    w = _term_width()
    title_text = f" {title} "
    title_w = _visible_width(title_text)
    left = 2
    right = max(1, w - left - title_w)
    line = "━" * left + title_text + "━" * right
    print(c(line, C.CYAN))


def label(text: str) -> str:
    """标签着色 (Cyan)."""
    return c(text, C.CYAN)


def value(text: str) -> str:
    """值着色 (White Bold)."""
    return c(text, C.WHITE, C.BOLD)


def ok(text: str) -> str:
    """成功绿色 (Green Bold)."""
    return c(text, C.GREEN, C.BOLD)


def warn(text: str) -> str:
    """警告黄色."""
    return c(text, C.YELLOW)


def err(text: str) -> str:
    """错误红色 (Red Bold)."""
    return c(text, C.RED, C.BOLD)


def dim(text: str) -> str:
    """暗灰色 (Dim Gray)."""
    return c(text, C.DIM, C.GRAY)


# ── 交互组件 ──────────────────────────────────────────────


def wait_key(msg: str = "按任意键继续..."):
    """dim 提示 + getch 阻塞 + 清除提示行."""
    sys.stdout.write("  " + dim(msg))
    sys.stdout.flush()
    try:
        getch()
    except KeyboardInterrupt:
        pass
    # 清除本行
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()


def input_line(prompt: str, default: str | None = None) -> str | None:
    """彩色 prompt + 系统 input().

    返回值:
        用户输入的字符串；回车无输入且有 default → 返回 default；
        回车无输入且无 default → 返回 None。
        EOFError → 返回 None。
    """
    if default is not None:
        display = "  " + c(prompt, C.CYAN) + " [" + c(default, C.WHITE, C.BOLD) + "]: "
    else:
        display = "  " + c(prompt, C.CYAN) + ": "
    sys.stdout.write(display)
    sys.stdout.flush()
    try:
        raw = input().strip()
    except EOFError:
        print()
        return None
    if not raw:
        return default
    return raw


def menu(
    title: str,
    options: list[str],
    *,
    footer: str | None = None,
    separators: set[int] | None = None,
    item_colors: dict[int, str] | None = None,
) -> int | None:
    """方向键菜单.

    参数:
        title: 菜单标题
        options: 选项文本列表
        footer: 底部提示文字
        separators: 不可选的分隔行索引集合
        item_colors: 指定索引的未选中状态颜色

    返回:
        Enter → 选中索引 (int)；Esc/Ctrl+C → None
    """
    seps = separators or set()
    colors = item_colors or {}

    # 初始 cursor 跳过 separators
    cursor = 0
    while cursor in seps and cursor < len(options):
        cursor += 1
    if cursor >= len(options):
        cursor = 0

    def _next_idx(cur: int, direction: int) -> int:
        """跳过 separator 的下一个索引."""
        n = len(options)
        nxt = (cur + direction) % n
        steps = 0
        while nxt in seps and steps < n:
            nxt = (nxt + direction) % n
            steps += 1
        return nxt

    def _render() -> int:
        """渲染菜单，返回输出行数."""
        lines = 0
        # title bar
        title_bar(title)
        lines += 1
        # 选项
        for i, opt in enumerate(options):
            if i in seps:
                # 分隔行
                print("  " + dim("─" * (_term_width() - 4)))
            elif i == cursor:
                # 选中行: ▸ Cyan Bold + 文字 White Bold
                print("  " + c("▸ ", C.CYAN, C.BOLD) + c(opt, C.WHITE, C.BOLD))
            else:
                # 未选中行
                col = colors.get(i, C.GRAY)
                print("  " + c("  ", C.GRAY) + c(opt, col))
            lines += 1
        # footer
        if footer:
            print("  " + dim(footer))
            lines += 1
        return lines

    total_lines = _render()

    while True:
        try:
            key = getch()
        except KeyboardInterrupt:
            _erase_above(total_lines)
            return None

        if key == Key.ENTER:
            _erase_above(total_lines)
            return cursor
        elif key == Key.ESC:
            _erase_above(total_lines)
            return None
        elif key in (Key.DOWN, Key.TAB):
            cursor = _next_idx(cursor, 1)
        elif key in (Key.UP, Key.BTAB):
            cursor = _next_idx(cursor, -1)
        else:
            continue

        # 重绘
        _erase_above(total_lines)
        total_lines = _render()


def yes_no(prompt: str, default: bool = True) -> bool | None:
    """←→ 实时切换确认.

    返回:
        Enter → bool；Esc/Ctrl+C → None
    """
    # choice: 0=是, 1=否
    choice = 0 if default else 1

    def _render() -> int:
        """渲染一行，返回行数(1)."""
        if choice == 0:
            yes_part = c("● 是", C.GREEN, C.BOLD)
            no_part  = c("○ 否", C.RED)
        else:
            yes_part = c("○ 是", C.GREEN)
            no_part  = c("● 否", C.RED, C.BOLD)
        line = "  " + c(prompt, C.CYAN) + "   " + yes_part + "    " + no_part
        print(line)
        return 1

    total_lines = _render()

    while True:
        try:
            key = getch()
        except KeyboardInterrupt:
            _erase_above(total_lines)
            return None

        if key == Key.ENTER:
            _erase_above(total_lines)
            return choice == 0
        elif key == Key.ESC:
            _erase_above(total_lines)
            return None
        elif key == Key.LEFT:
            choice = 0
        elif key == Key.RIGHT:
            choice = 1
        else:
            continue

        _erase_above(total_lines)
        total_lines = _render()
