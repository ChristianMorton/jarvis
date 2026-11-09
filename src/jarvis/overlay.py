"""Fullscreen click-through grid overlay, run as its own process.

Tkinter insists on owning its thread's event loop, which would fight the audio
callback, so the overlay lives in a subprocess and takes JSON-line commands on
stdin:

    {"cmd": "show", "x": 0, "y": 0, "w": 1920, "h": 1080, "rows": 3, "cols": 3}
    {"cmd": "hide"}
    {"cmd": "quit"}
"""

from __future__ import annotations

import json
import sys
import threading

TRANSPARENT = "#010203"  # colour key: painted pixels of this shade vanish


def main() -> int:  # pragma: no cover - GUI process
    try:
        import tkinter as tk
    except ImportError:
        print("tkinter unavailable", file=sys.stderr)
        return 1

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-transparentcolor", TRANSPARENT)
    except tk.TclError:
        pass  # not Windows; fall back to a translucent window
    canvas = tk.Canvas(root, highlightthickness=0, bg=TRANSPARENT)
    canvas.pack(fill="both", expand=True)

    state: dict = {}

    def draw() -> None:
        canvas.delete("all")
        if not state.get("visible"):
            root.withdraw()
            return
        x, y = int(state["x"]), int(state["y"])
        w, h = int(state["w"]), int(state["h"])
        rows, cols = int(state.get("rows", 3)), int(state.get("cols", 3))
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.deiconify()
        root.lift()

        cell_w, cell_h = w / cols, h / rows
        for row in range(rows):
            for col in range(cols):
                left, top = col * cell_w, row * cell_h
                canvas.create_rectangle(
                    left + 1, top + 1, left + cell_w - 1, top + cell_h - 1,
                    outline="#00e5ff", width=2,
                )
                label = str(row * cols + col + 1)
                cx, cy = left + cell_w / 2, top + cell_h / 2
                size = max(14, int(min(cell_w, cell_h) / 4))
                # Dark halo first so the digit survives a light background.
                for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    canvas.create_text(cx + dx, cy + dy, text=label,
                                       fill="#001018", font=("Segoe UI", size, "bold"))
                canvas.create_text(cx, cy, text=label, fill="#00e5ff",
                                   font=("Segoe UI", size, "bold"))

    def reader() -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            command = message.get("cmd")
            if command == "quit":
                root.after(0, root.destroy)
                return
            if command == "hide":
                state["visible"] = False
            elif command == "show":
                state.update(message)
                state["visible"] = True
            root.after(0, draw)
        root.after(0, root.destroy)

    threading.Thread(target=reader, daemon=True).start()
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
