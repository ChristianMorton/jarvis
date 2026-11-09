"""Render captured CLI output as portfolio media (no microphone or desktop input).

Optional media dependencies: pip install pillow imageio-ffmpeg
Run from the repository root: python scripts/render-demo.py
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "docs" / "media"
MEDIA.mkdir(parents=True, exist_ok=True)
ENV = dict(os.environ, PYTHONUTF8="1")
SCENES = [
    ("01 / Parse and dispatch", ["scroll down five", "press control bravo"]),
    ("02 / App aliases and command chains", ["switch to terminal", "scroll down then next tab"]),
    ("03 / Wake-word state machine", ["--require-wake", "scroll down", "jarvis", "scroll down", "stand down"]),
]
font_path = Path("C:/Windows/Fonts/consola.ttf")
font = ImageFont.truetype(str(font_path), 24) if font_path.exists() else ImageFont.load_default(size=24)
small = ImageFont.truetype(str(font_path), 19) if font_path.exists() else ImageFont.load_default(size=19)
big = ImageFont.truetype(str(font_path), 37) if font_path.exists() else ImageFont.load_default(size=37)
symbol_path = Path("C:/Windows/Fonts/seguisym.ttf")
symbol = ImageFont.truetype(str(symbol_path), 24) if symbol_path.exists() else font
W, H = 1280, 800
captures = []
for title, args in SCENES:
    command = [sys.executable, "-m", "jarvis", "test", *args]
    result = subprocess.run(command, cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8")
    # The wake-word scene deliberately includes an ignored phrase; the CLI returns 1.
    expected = 1 if "--require-wake" in args else 0
    if result.returncode != expected:
        raise RuntimeError(result.stderr or result.stdout)
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout).rstrip()
    prompt = "python -m jarvis test " + " ".join(a if a.startswith("--") else f'"{a}"' for a in args)
    captures.append((title, prompt, output))
transcript = "\n\n".join(f"{title}\n$ {prompt}\n{output}" for title, prompt, output in captures)
(MEDIA / "terminal-demo.txt").write_text(transcript + "\n", encoding="utf-8")

def wrap(text, width=86):
    import textwrap
    return textwrap.wrap(text, width=width, subsequent_indent="  ") or [""]

def frame(title, prompt, lines, step):
    im = Image.new("RGB", (W, H), "#0b101a")
    d = ImageDraw.Draw(im)
    d.text((48, 35), "JARVIS", font=big, fill="#f0f4fa")
    d.text((48, 92), "Actual CLI output / microphone-free recording driver", font=small, fill="#80d4c3")
    d.rounded_rectangle((40, 145, W-40, 718), radius=18, fill="#121c2b", outline="#2a394d", width=2)
    d.text((65, 167), title, font=small, fill="#98aecb")
    y=215
    for line in wrap("$ " + prompt):
        d.text((65,y),line,font=font,fill="#f7d48b"); y+=31
    y+=17
    for line in lines[:step]:
        if line and line[0] in "✓◉·":
            d.text((65,y),line[0],font=symbol,fill="#80d4c3")
            d.text((81,y),line[1:],font=font,fill="#dce7f7")
        else:
            d.text((65,y),line,font=font,fill="#dce7f7")
        y+=32
    d.text((48, 749), "Simulated input actions. No live speech recognition or desktop control shown.", font=small, fill="#a7b6ca")
    return im
frames=[]; durations=[]
for title,prompt,output in captures:
    lines=output.splitlines()
    frames.append(frame(title,prompt,lines,0)); durations.append(1300)
    for i in range(1,len(lines)+1):
        frames.append(frame(title,prompt,lines,i)); durations.append(500)
    frames.append(frame(title,prompt,lines,len(lines))); durations.append(2500)
frames[1].save(MEDIA / "terminal-demo.png")
frames[0].save(MEDIA / "terminal-demo.gif",save_all=True,append_images=frames[1:],duration=durations,loop=0,optimize=True)
writer=imageio_ffmpeg.write_frames(str(MEDIA / "terminal-demo.mp4"),(W,H),fps=10,codec="libx264",pix_fmt_in="rgb24",pix_fmt_out="yuv420p",quality=8,macro_block_size=1)
writer.send(None)
for im,ms in zip(frames,durations):
    data=im.tobytes()
    for _ in range(round(ms/100)):
        writer.send(data)
writer.close()
# Use the completed first scene for the still.
title,prompt,output=captures[0]
frame(title,prompt,output.splitlines(),999).save(MEDIA / "terminal-demo.png")
print(f"Rendered {len(captures)} captured scenes to {MEDIA}")
