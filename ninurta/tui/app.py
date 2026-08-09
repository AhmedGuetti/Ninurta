"""Ninurta TUI — terminal-native chat interface with a fixed bottom prompt.

Built with prompt_toolkit:

  * violet-gradient ``NINURTA`` banner (fixed at top)
  * a bordered box with bow art + system info, inside a scrollable area
  * a scrollable chat log (mouse wheel / PageUp / PageDown / arrow keys)
  * a status bar (fixed at bottom)
  * an input prompt fixed at the very bottom of the screen
"""

from __future__ import annotations

import os

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.layout.containers import (
    HSplit,
    VSplit,
    Window,
)
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from ninurta import __version__
from ninurta.config import get_default_model_id
from ninurta.tui.art import load_banner, load_bow_art
from ninurta.tui.palette import ACCENT, ACCENT_LIGHT, MUTED, TAGLINE, TEXT

# ── Violet gradient colors for the banner ───────────────────────────────────
_VIOLET_GRADIENT = [
    "#e9d5ff",  # violet-200 (lightest)
    "#c084fc",  # purple-400
    "#a855f7",  # purple-500
    "#9333ea",  # purple-600
    "#7c3aed",  # violet-600
    "#6d28d9",  # violet-700 (deepest)
]

# ── Style map ───────────────────────────────────────────────────────────────
_style_dict = {
    "tagline": f"bold {TAGLINE}",
    "border": ACCENT,
    "box-content": ACCENT_LIGHT,
    "bow": ACCENT_LIGHT,
    "title": f"bold {ACCENT}",
    "item": "#f0abfc",
    "hint": MUTED,
    "you": f"bold {TAGLINE}",
    "ninurta": ACCENT_LIGHT,
    "chat": TEXT,
    "status-ready": "bold #00ff7f",
    "status": MUTED,
    "prompt": f"bold {ACCENT}",
    "input": TEXT,
    "scrollbar.background": "#3b0764",
    "scrollbar.button": "#9333ea",
    "scrollbar.arrow": "bold #c084fc",
}
for _i, _color in enumerate(_VIOLET_GRADIENT):
    _style_dict[f"banner-v{_i}"] = f"bold {_color}"

_STYLE = Style.from_dict(_style_dict)


# ── Build the bordered box as plain text ────────────────────────────────────

def _build_box_text(model_id: str, cwd: str) -> str:
    """Build the bordered info box + intro as plain text for the TextArea."""
    lines: list[str] = []

    # Left column: bow art + sysinfo
    bow = load_bow_art()
    left_lines: list[str] = []
    if bow:
        left_lines.extend(bow.splitlines())
    left_lines.append("")
    left_lines.append(f"{model_id} · Nous Research")
    left_lines.append(cwd)
    left_lines.append(f"Session: {__version__}")

    # Right column: version + pipelines + commands
    right_lines: list[str] = []
    right_lines.append(f"Ninurta v{__version__}")
    right_lines.append("")
    right_lines.append("▼ Pipelines")
    right_lines.append("  extract → extractor")
    right_lines.append("  resume  → reader · validator · reviewer · saver")
    right_lines.append("")
    right_lines.append("▼ Commands")
    right_lines.append("  ninurta tui      interactive chat interface")
    right_lines.append("  ninurta extract  parse a job description")
    right_lines.append("  ninurta resume   parse + validate + save resume")
    right_lines.append("  ninurta models   list available models")

    left_w = max((len(ln) for ln in left_lines), default=0)
    right_w = max((len(ln) for ln in right_lines), default=0)
    gap = 4

    max_rows = max(len(left_lines), len(right_lines))
    while len(left_lines) < max_rows:
        left_lines.append("")
    while len(right_lines) < max_rows:
        right_lines.append("")

    inner_w = left_w + gap + right_w
    box_w = inner_w + 4  # │ + space + content + space + │

    title = f" NINURTA v{__version__} "
    top_pad = box_w - 2 - len(title)
    lines.append("╭" + title + "─" * max(0, top_pad) + "╮")

    for l_ln, r_ln in zip(left_lines, right_lines):
        l_padded = l_ln.ljust(left_w)
        r_padded = r_ln.ljust(right_w)
        row = f"{l_padded}{' ' * gap}{r_padded}".ljust(inner_w)
        lines.append(f"│ {row} │")

    lines.append("╰" + "─" * (box_w - 2) + "╯")
    lines.append("")
    lines.append("Type below and press Enter — it echoes back.  quit / Ctrl+D to exit.")
    lines.append("")

    return "\n".join(lines)


class NinurtaTUI:
    """A prompt_toolkit application: colored banner + scrollable box/chat + fixed prompt."""

    def __init__(self) -> None:
        self.model_id = get_default_model_id()
        self.cwd = os.getcwd()

        # Scrollable area: box + chat — TextArea has built-in working scroll
        box_text = _build_box_text(self.model_id, self.cwd)
        self.chat_area = TextArea(
            text=box_text,
            read_only=True,
            scrollbar=True,
            wrap_lines=True,
            focus_on_click=True,
        )

        self.input_buffer = Buffer(accept_handler=self._on_accept, multiline=False)
        self._build()

    # ── Focus-on-click helper ─────────────────────────────────────────────
    @staticmethod
    def _add_click_focus(target, control):
        """Wrap the control's mouse handler to focus *target* on left-click 
        while preserving the original mouse behavior (scrolling, selecting).
        """
        orig_handler = control.mouse_handler

        def _handler(mouse_event):
            if mouse_event.event_type == MouseEventType.SCROLL_UP:
                if hasattr(control, "buffer"):
                    control.buffer.cursor_up(count=3)
                else:
                    target._scroll_up()
                get_app().invalidate()
                return None
            elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
                if hasattr(control, "buffer"):
                    control.buffer.cursor_down(count=3)
                else:
                    target._scroll_down()
                get_app().invalidate()
                return None
            elif mouse_event.event_type == MouseEventType.MOUSE_UP:
                get_app().layout.focus(target)
            
            if orig_handler:
                return orig_handler(mouse_event)
            return NotImplemented

        control.mouse_handler = _handler

    def _build(self) -> None:
        # --- Colored banner (fixed at top) ---
        banner_ctrl = FormattedTextControl(
            self._banner_fragments, focusable=True  # pyright: ignore[reportArgumentType]
        )
        banner_win = Window(
            content=banner_ctrl,
            dont_extend_height=True,
        )
        self._add_click_focus(banner_win, banner_ctrl)

        # --- Fixed chrome at bottom ---
        status_ctrl = FormattedTextControl(
            self._status_text, focusable=True  # pyright: ignore[reportArgumentType]
        )
        status_win = Window(
            content=status_ctrl,
            height=1,
        )
        self._add_click_focus(status_win, status_ctrl)

        prompt_ctrl = FormattedTextControl(
            [("class:prompt", "❯ ")], focusable=True
        )
        prompt_char = Window(
            content=prompt_ctrl,
            width=3,
            height=1,
        )
        self._add_click_focus(prompt_char, prompt_ctrl)

        input_ctrl = BufferControl(
            buffer=self.input_buffer,
            focusable=True,
            focus_on_click=True,
        )
        self._input_win = Window(
            content=input_ctrl,
            height=1,
            style="class:input",
        )
        self._add_click_focus(self._input_win, input_ctrl)

        prompt_row = VSplit([prompt_char, self._input_win])

        # TextArea's internal window + control — make it click-to-focus and scrollable
        chat_win = self.chat_area.window
        chat_ctrl = self.chat_area.control
        self._add_click_focus(chat_win, chat_ctrl)

        root = HSplit(
            [
                banner_win,       # fixed: click-to-focus, selectable
                self.chat_area,   # scrollable: click-to-focus, selectable
                status_win,       # fixed: click-to-focus, selectable
                prompt_row,       # fixed: click-to-focus, selectable
            ]
        )

        kb = self._bindings()
        self.app = Application(
            layout=Layout(root, focused_element=self._input_win),
            key_bindings=merge_key_bindings([load_key_bindings(), kb]),
            style=_STYLE,
            full_screen=True,
            mouse_support=True,
        )

    # ── Banner renderer (violet gradient) ───────────────────────────────────
    def _banner_fragments(self) -> list[tuple[str, str]]:
        frags: list[tuple[str, str]] = []
        banner = load_banner()
        if banner:
            lines = banner.splitlines()
            n = len(lines)
            for i, ln in enumerate(lines):
                step = min(
                    int(i / max(n, 1) * len(_VIOLET_GRADIENT)),
                    len(_VIOLET_GRADIENT) - 1,
                )
                frags.append((f"class:banner-v{step}", ln + "\n"))
        frags.append(("class:tagline", "§ Ninurta · God of War and the Hunt — Lord of the Bow\n"))
        return frags

    def _status_text(self) -> list[tuple[str, str]]:
        return [
            ("class:status-ready", "– ready "),
            (
                "class:status",
                f"| {self.model_id.replace('gemini:', '')} | 0s | voice off | 1 session",
            ),
            ("", " " * 20),
            ("class:status", f"~ {self.cwd}"),
        ]

    # ── Key bindings ────────────────────────────────────────────────────────
    def _on_accept(self, buf: Buffer) -> None:
        text = buf.text.strip()
        if not text:
            return
        buf.reset()

        low = text.lower()
        if low in ("quit", "exit", "q", "/exit", "/quit"):
            self.app.exit()
            return

        new_text = self.chat_area.text + f"you: {text}\nninurta: You said — {text}\n"
        self.chat_area.text = new_text
        self.app.invalidate()

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-d")
        def _exit(event) -> None:
            event.app.exit()

        @kb.add("pageup")
        def _pgup(event) -> None:
            for _ in range(5):
                self.chat_area.window._scroll_up()

        @kb.add("pagedown")
        def _pgdown(event) -> None:
            for _ in range(5):
                self.chat_area.window._scroll_down()

        @kb.add("up")
        def _up(event) -> None:
            self.chat_area.window._scroll_up()

        @kb.add("down")
        def _down(event) -> None:
            self.chat_area.window._scroll_down()

        return kb

    # ── Lifecycle ───────────────────────────────────────────────────────────
    def run(self) -> None:
        try:
            self.app.run()
        except KeyboardInterrupt:
            pass
        finally:
            print()


def run() -> None:
    """Launch the Ninurta TUI."""
    NinurtaTUI().run()


if __name__ == "__main__":
    run()
