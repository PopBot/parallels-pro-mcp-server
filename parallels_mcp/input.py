"""Synthetic keyboard input and hotkey automation for Parallels virtual machines."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from .prl import CommandResult, PrlCommandError, run_prlctl
from .vm import VmService


Runner = Callable[..., Awaitable[CommandResult]]

# Parallels Desktop virtual key codes from the Parallels Desktop Developer's Guide
KEY_CODES: dict[str, int] = {
    # Modifiers
    "ctrl": 37,
    "control": 37,
    "left_ctrl": 37,
    "rctrl": 37,
    "shift": 50,
    "left_shift": 50,
    "rshift": 62,
    "right_shift": 62,
    "alt": 64,
    "opt": 64,
    "option": 64,
    "left_alt": 64,
    "ralt": 64,
    "win": 7,
    "cmd": 7,
    "command": 7,
    "meta": 7,
    "super": 7,
    # Navigation and basic keys
    "enter": 36,
    "return": 36,
    "esc": 9,
    "escape": 9,
    "tab": 23,
    "space": 65,
    "backspace": 22,
    "delete": 106,
    "del": 106,
    "caps_lock": 66,
    "capslock": 66,
    "up": 98,
    "arrow_up": 98,
    "down": 104,
    "arrow_down": 104,
    "left": 100,
    "arrow_left": 100,
    "right": 102,
    "arrow_right": 102,
    "home": 97,
    "end": 103,
    # Function keys F1-F12
    "f1": 67,
    "f2": 68,
    "f3": 69,
    "f4": 70,
    "f5": 71,
    "f6": 72,
    "f7": 73,
    "f8": 74,
    "f9": 75,
    "f10": 76,
    "f11": 95,
    "f12": 96,
    # Digits 0-9
    "0": 19,
    "1": 10,
    "2": 11,
    "3": 12,
    "4": 13,
    "5": 14,
    "6": 15,
    "7": 16,
    "8": 17,
    "9": 18,
    # Letters a-z
    "a": 38,
    "b": 56,
    "c": 54,
    "d": 40,
    "e": 26,
    "f": 41,
    "g": 42,
    "h": 43,
    "i": 31,
    "j": 44,
    "k": 45,
    "l": 46,
    "m": 58,
    "n": 57,
    "o": 32,
    "p": 33,
    "q": 24,
    "r": 27,
    "s": 39,
    "t": 28,
    "u": 30,
    "v": 55,
    "w": 25,
    "x": 53,
    "y": 29,
    "z": 52,
    # Punctuation & symbols
    "-": 20,
    "minus": 20,
    "=": 21,
    "equal": 21,
    "[": 34,
    "]": 35,
    ";": 47,
    "semicolon": 47,
    "'": 48,
    "quote": 48,
    "`": 49,
    "~": 49,
    "\\": 51,
    "backslash": 51,
    ",": 59,
    "comma": 59,
    ".": 60,
    "dot": 60,
    "period": 60,
    "/": 61,
    "slash": 61,
}


class KeyEventResult(BaseModel):
    """Result of sending key events to a VM."""

    model_config = ConfigDict(extra="forbid")

    vm: str
    uuid: str
    events_sent: int
    keys: list[str]
    message: str


def _resolve_code(token: str) -> int:
    norm = token.strip().lower()
    if norm in KEY_CODES:
        return KEY_CODES[norm]
    raise ValueError(f"Unrecognized key token: {token!r}")


def _build_events_for_chord(chord: str, delay_ms: int) -> list[dict[str, Any]]:
    tokens = [t.strip() for t in chord.split("+") if t.strip()]
    if not tokens:
        raise ValueError("Key chord cannot be empty")
    codes = [_resolve_code(t) for t in tokens]

    events: list[dict[str, Any]] = []
    # Press each key in order
    for code in codes:
        events.append({"key": code, "event": "press", "delay": delay_ms})
    # Release each key in reverse order
    for code in reversed(codes):
        events.append({"key": code, "event": "release", "delay": delay_ms})
    return events


class InputService:
    def __init__(self, vms: VmService, runner: Runner = run_prlctl) -> None:
        self._vms = vms
        self._runner = runner

    async def send_keys(
        self,
        vm: str,
        keys: list[str] | str,
        *,
        delay_ms: int = 50,
        timeout: float = 30.0,
    ) -> KeyEventResult:
        if isinstance(keys, str):
            key_list = [keys]
        else:
            key_list = list(keys)

        if not key_list:
            raise ValueError("keys must not be empty")

        uuid = await self._vms.resolve(vm)

        all_events: list[dict[str, Any]] = []
        for item in key_list:
            item_str = str(item).strip()
            if not item_str:
                continue
            # If item is a chord or recognized single token (e.g. "ctrl+alt+del" or "enter")
            if "+" in item_str or item_str.lower() in KEY_CODES:
                all_events.extend(_build_events_for_chord(item_str, delay_ms))
            else:
                # Type string character by character
                for ch in item_str:
                    if ch.isupper():
                        # Shift + lower letter
                        lower_ch = ch.lower()
                        chord = f"shift+{lower_ch}"
                        all_events.extend(_build_events_for_chord(chord, delay_ms))
                    else:
                        all_events.extend(_build_events_for_chord(ch, delay_ms))

        if not all_events:
            raise ValueError("No valid key events were generated from input")

        payload = json.dumps(all_events)
        result = await self._runner(
            "send-key-event",
            uuid,
            "-j",
            stdin=payload,
            timeout=timeout,
        )
        if not result.ok:
            raise PrlCommandError(result)

        return KeyEventResult(
            vm=vm,
            uuid=uuid,
            events_sent=len(all_events),
            keys=key_list,
            message=f"Sent {len(all_events)} key events to VM {vm!r}",
        )
