"""`python -m net_hud` 入口。"""

from __future__ import annotations

import sys

from .app import main
from .win32ui_ext import set_dpi_awareness

if __name__ == "__main__":
    set_dpi_awareness()
    sys.exit(main())
