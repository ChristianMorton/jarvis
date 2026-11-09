"""Recursive mouse grid: point anywhere on screen with two or three words.

"jarvis grid"  -> 3x3 numbered overlay over the whole screen
"five"         -> zoom into cell 5, mouse moves to its centre
"five"         -> zoom again; after three picks you are within ~70px
"click"        -> ordinary click action; "grid off" dismisses the overlay
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Optional

from .registry import ActionContext, action, arg


class GridOverlay:
    """Owns the overlay subprocess and the current zoom rectangle."""

    def __init__(self, rows: int = 3, cols: int = 3):
        self.rows, self.cols = rows, cols
        self.rect: Optional[tuple[int, int, int, int]] = None
        self._process: Optional[subprocess.Popen] = None

    def _ensure_process(self) -> Optional[subprocess.Popen]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        executable = sys.executable
        # pythonw keeps a console window from flashing up on Windows.
        if os.name == "nt":
            candidate = executable.replace("python.exe", "pythonw.exe")
            if os.path.exists(candidate):
                executable = candidate
        try:
            self._process = subprocess.Popen(
                [executable, "-m", "jarvis.overlay"],
                stdin=subprocess.PIPE, text=True, bufsize=1,
            )
        except OSError:
            self._process = None
        return self._process

    def _send(self, message: dict) -> None:
        process = self._ensure_process()
        if process is None or process.stdin is None:
            return
        try:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, ValueError):
            self._process = None

    def show(self, rect: tuple[int, int, int, int]) -> None:
        self.rect = rect
        x, y, w, h = rect
        self._send({"cmd": "show", "x": x, "y": y, "w": w, "h": h,
                    "rows": self.rows, "cols": self.cols})

    def hide(self) -> None:
        self.rect = None
        self._send({"cmd": "hide"})

    def close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._send({"cmd": "quit"})
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def cell_rect(self, cell: int) -> tuple[int, int, int, int]:
        if self.rect is None:
            raise ValueError("grid is not showing")
        if not 1 <= cell <= self.rows * self.cols:
            raise ValueError(f"cell {cell} is outside a {self.rows}x{self.cols} grid")
        x, y, w, h = self.rect
        index = cell - 1
        row, col = divmod(index, self.cols)
        cell_w, cell_h = w / self.cols, h / self.rows
        return (int(x + col * cell_w), int(y + row * cell_h),
                max(1, int(cell_w)), max(1, int(cell_h)))


def _grid(ctx: ActionContext) -> GridOverlay:
    if getattr(ctx.engine, "grid", None) is None:
        ctx.engine.grid = GridOverlay(
            rows=int(ctx.config.get("grid.rows", 3) or 3),
            cols=int(ctx.config.get("grid.cols", 3) or 3),
        )
    return ctx.engine.grid


@action("grid_show")
def grid_show(ctx: ActionContext, args: dict) -> str:
    grid = _grid(ctx)
    width, height = ctx.driver.screen_size()
    grid.show((0, 0, width, height))
    return "grid"


@action("grid_pick")
def grid_pick(ctx: ActionContext, args: dict) -> str:
    grid = _grid(ctx)
    cell = arg(args, "cell", None, int)
    if cell is None:
        raise ValueError("grid_pick: needs 'cell'")
    if grid.rect is None:
        grid_show(ctx, {})
    rect = grid.cell_rect(cell)
    grid.show(rect)
    x, y, w, h = rect
    ctx.driver.move_to(x + w // 2, y + h // 2)
    return f"grid {cell}"


@action("grid_hide")
def grid_hide(ctx: ActionContext, args: dict) -> str:
    grid = _grid(ctx)
    grid.hide()
    return "grid off"


@action("grid_click")
def grid_click(ctx: ActionContext, args: dict) -> str:
    """Pick a cell (optional), dismiss the overlay, then click."""
    grid = _grid(ctx)
    cell = arg(args, "cell", None, int)
    if cell is not None:
        grid_pick(ctx, {"cell": cell})
    grid.hide()
    ctx.driver.click(str(arg(args, "button", "left")), arg(args, "count", 1, int) or 1)
    return "grid click"
