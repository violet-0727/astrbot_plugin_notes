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
    # 从插件自己的位置推：<data>/plugins/<name> -> <data>/plugin_data/<name>
    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.dirname(os.path.dirname(here))
    path = os.path.join(data_dir, "plugin_data", name)
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        pass
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

        fallback = os.path.join(get_astrbot_plugin_data_path(), name)
        os.makedirs(fallback, exist_ok=True)
        return fallback
    except Exception:
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
