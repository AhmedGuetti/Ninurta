from prompt_toolkit.application import Application
from prompt_toolkit.layout import Layout, Window, ScrollOffsets
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.key_binding import KeyBindings

ta = TextArea(text="line\n" * 100, scrollbar=True)
kb = KeyBindings()
@kb.add("q")
def _(event): event.app.exit()

app = Application(layout=Layout(ta), key_bindings=kb, mouse_support=True)
