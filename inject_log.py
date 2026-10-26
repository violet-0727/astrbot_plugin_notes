"""把每轮注入的内容记一行，方便回看。

只写自己的目录，不影响任何行为；写失败就算了。
"""

from __future__ import annotations

import io
import json
import os
import time

MAX_LINES = 300
MAX_TEXT = 1000


def _plugin_name() -> str:
    return os.path.basename(os.path.dirname(os.path.abspath(__file__)))


def log_dir() -> str:
    name = _plugin_name()
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        base = get_astrbot_plugin_data_path()
    except Exception:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugin_data")
    path = os.path.join(base, name)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def log_inject(text: str, who: str = "") -> None:
    try:
        path = os.path.join(log_dir(), "inject.log")
        line = json.dumps(
            {"t": round(time.time(), 1), "who": str(who or ""), "text": str(text or "")[:MAX_TEXT]},
            ensure_ascii=False,
        )
        rows = []
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as f:
                rows = f.readlines()
        rows.append(line + "\n")
        if len(rows) > MAX_LINES:
            rows = rows[-MAX_LINES:]
        with io.open(path, "w", encoding="utf-8") as f:
            f.writelines(rows)
    except Exception:
        pass
