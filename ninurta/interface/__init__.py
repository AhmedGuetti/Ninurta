"""Interface helpers — stdin reader, CSV writer, document extraction."""

from ninurta.interface.io import read_stdin_until_double_enter, append_csv_row
from ninurta.interface.documents import extract_text

__all__ = ["read_stdin_until_double_enter", "append_csv_row", "extract_text"]
