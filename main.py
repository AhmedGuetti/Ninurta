"""Dev launcher — run the Ninurta CLI without installing the package.

Usage (from project root):
    python main.py extract
    python main.py tui
    python main.py --help
"""

import sys
import os

# Make the ninurta/ tree importable when running directly
sys.path.insert(0, os.path.dirname(__file__))

from ninurta.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
