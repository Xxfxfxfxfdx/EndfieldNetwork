"""无控制台启动入口（双击本文件，或用 pythonw.exe run.pyw）。

等价于 `python -m net_hud`，只是不弹控制台窗口。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from net_hud.app import main  # noqa: E402
from net_hud.win32ui_ext import set_dpi_awareness  # noqa: E402

if __name__ == "__main__":
    set_dpi_awareness()
    sys.exit(main())
