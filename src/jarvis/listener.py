"""Microphone capture and Vosk decoding.

Kept behind lazy imports so the rest of Jarvis — matching, config, the CLI's
``test`` and ``commands`` subcommands, the whole test-suite — runs on a machine
with neither vosk nor a sound card.
"""

from __future__ import annotations

import json
import logging
import queue
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

log = logging.getLogger("jarvis.listener")


@dataclass
class Utterance:
    text: str
    partial: bool = False
    confidence: Optional[float] = None


class MissingModel(RuntimeError):
    pass


def resolve_model_path(raw: str) -> Path:
    """Find the acoustic model, trying the path as given and then relative to
    the project root (so a config can say ``models/vosk-model-small-en-us-0.15``
    and still work from any working directory)."""
    path = Path(raw).expanduser()
    if path.is_dir():
        return path
    project_root = Path(__file__).resolve().parents[2]
    candidate = project_root / raw
    if candidate.is_dir():
        return candidate
    raise MissingModel(
        f"No Vosk model at {path} (also tried {candidate}).\n"
        f"Download one with:  python -m jarvis download-model\n"
        f"or set model.path in your jarvis.yaml."
    )


def list_devices() -> list[dict]:
    import sounddevice

    return [
        {
            "index": index,
            "name": device["name"],
            "inputs": device["max_input_channels"],
            "default_rate": int(device["default_samplerate"]),
        }
        for index, device in enumerate(sounddevice.query_devices())
        if device["max_input_channels"] > 0
    ]


class Listener:
    """Yields recognised utterances from the default (or configured) mic."""

    def __init__(
        self,
        model_path: str,
        samplerate: int = 16000,
        device=None,
        blocksize: int = 4000,
        grammar: Optional[str] = None,
        emit_partials: bool = False,
    ) -> None:
        self.model_path = resolve_model_path(model_path)
        self.samplerate = samplerate
        self.device = device
        self.blocksize = blocksize
        self.grammar = grammar
        self.emit_partials = emit_partials
        self._queue: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self._recognizer = None
        self._running = False

    def _build_recognizer(self):
        import vosk

        vosk.SetLogLevel(-1)  # the C++ layer is extremely chatty otherwise
        model = vosk.Model(str(self.model_path))
        if self.grammar:
            try:
                recognizer = vosk.KaldiRecognizer(model, self.samplerate, self.grammar)
            except Exception as exc:
                log.warning(
                    "model %s rejected the restricted grammar (%s); "
                    "falling back to open recognition — expect more misfires",
                    self.model_path.name, exc,
                )
                recognizer = vosk.KaldiRecognizer(model, self.samplerate)
        else:
            recognizer = vosk.KaldiRecognizer(model, self.samplerate)
        recognizer.SetWords(False)
        return recognizer

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("audio status: %s", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            # Dropping a block beats blocking the audio thread; a backed-up
            # queue means decoding is behind and stale audio helps nobody.
            log.debug("audio queue full, dropping a block")

    def stop(self) -> None:
        self._running = False

    def listen(self) -> Iterator[Utterance]:
        import sounddevice

        self._recognizer = self._build_recognizer()
        self._running = True
        last_partial = ""

        with sounddevice.RawInputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            device=self.device,
            dtype="int16",
            channels=1,
            callback=self._callback,
        ):
            while self._running:
                try:
                    data = self._queue.get(timeout=0.25)
                except queue.Empty:
                    continue

                if self._recognizer.AcceptWaveform(data):
                    result = json.loads(self._recognizer.Result())
                    text = (result.get("text") or "").strip()
                    last_partial = ""
                    if text:
                        yield Utterance(text=text, partial=False)
                elif self.emit_partials:
                    partial = json.loads(self._recognizer.PartialResult())
                    text = (partial.get("partial") or "").strip()
                    if text and text != last_partial:
                        last_partial = text
                        yield Utterance(text=text, partial=True)

            final = json.loads(self._recognizer.FinalResult())
            text = (final.get("text") or "").strip()
            if text:
                yield Utterance(text=text, partial=False)
