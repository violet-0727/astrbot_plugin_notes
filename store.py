"""笔记存储：单文件 JSONL + 轻量检索，零第三方依赖。

设计原则
--------
* 一个插件只碰自己的数据目录，不 import 其它插件。
* 存储就是一行一个 JSON，坏了只丢那一行，不会整个库读不出来。
* 检索用字符二元组（中文友好），不依赖分词器/向量库，几百条量级足够快。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid

_PUNCT = re.compile(
    r"[\s\u3000,，.。!！?？;；:：、\"'“”‘’()（）\[\]【】<>《》~～…—\-_/\\|*#`]+"
)


def normalize(text: str) -> str:
    return _PUNCT.sub("", (text or "").lower())


def grams(text: str) -> set[str]:
    """字符二元组集合，中文不需要分词。"""
    t = normalize(text)
    if not t:
        return set()
    if len(t) == 1:
        return {t}
    return {t[i : i + 2] for i in range(len(t) - 1)}


class NoteStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._notes: list[dict] = []
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.load()

    # ---------------- 持久化 ----------------

    def load(self) -> None:
        notes: list[dict] = []
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue  # 坏行跳过，不影响其它笔记
                    if isinstance(obj, dict) and obj.get("id"):
                        notes.append(obj)
        except FileNotFoundError:
            pass
        except Exception:
            pass
        with self._lock:
            self._notes = notes

    def _save_locked(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for note in self._notes:
                f.write(json.dumps(note, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)  # 原子替换，写一半崩了也不会毁掉旧库

    # ---------------- 读写 ----------------

    def add(
        self,
        title: str,
        body: str,
        source: str = "",
        trust: str = "unknown",
        tags: list[str] | None = None,
    ) -> dict:
        now = time.time()
        title = (title or "").strip()[:120]
        body = (body or "").strip()
        source = (source or "").strip()
        with self._lock:
            for note in self._notes:
                if source and note.get("source") == source:
                    note.update(
                        title=title or note.get("title", ""),
                        body=body or note.get("body", ""),
                        trust=trust or note.get("trust", "unknown"),
                        tags=tags or note.get("tags") or [],
                        updated_at=now,
                    )
                    self._save_locked()
                    return dict(note)
                if not source and title and note.get("title") == title:
                    note.update(body=body or note.get("body", ""), updated_at=now)
                    self._save_locked()
                    return dict(note)
            note = {
                "id": uuid.uuid4().hex[:12],
                "title": title,
                "body": body,
                "source": source,
                "trust": trust or "unknown",
                "tags": tags or [],
                "created_at": now,
                "updated_at": now,
                "hits": 0,
            }
            self._notes.append(note)
            self._save_locked()
            return dict(note)

    def update(self, note_id: str, **fields: object) -> dict | None:
        allowed = {"title", "body", "source", "trust", "tags"}
        with self._lock:
            for note in self._notes:
                if note.get("id") == note_id:
                    for key, value in fields.items():
                        if key in allowed and value is not None:
                            note[key] = value
                    note["updated_at"] = time.time()
                    self._save_locked()
                    return dict(note)
        return None

    def delete(self, note_id: str) -> bool:
        with self._lock:
            before = len(self._notes)
            self._notes = [n for n in self._notes if n.get("id") != note_id]
            changed = len(self._notes) != before
            if changed:
                self._save_locked()
            return changed

    def all(self) -> list[dict]:
        with self._lock:
            return [dict(n) for n in self._notes]

    def stats(self) -> dict:
        with self._lock:
            by_trust: dict[str, int] = {}
            for n in self._notes:
                key = str(n.get("trust") or "unknown")
                by_trust[key] = by_trust.get(key, 0) + 1
            return {"total": len(self._notes), "by_trust": by_trust, "path": self.path}

    # ---------------- 检索 ----------------

    def search(
        self,
        query: str,
        limit: int = 3,
        min_score: float = 0.0,
    ) -> list[tuple[float, dict]]:
        q = grams(query)
        if not q:
            return []
        qn = len(q) ** 0.5 or 1.0
        scored: list[tuple[float, dict]] = []
        with self._lock:
            notes = list(self._notes)
        for note in notes:
            body = " ".join(
                [
                    str(note.get("title") or ""),
                    str(note.get("body") or ""),
                    " ".join(str(t) for t in (note.get("tags") or [])),
                ]
            )
            ng = grams(body)
            if not ng:
                continue
            common = len(q & ng)
            if not common:
                continue
            score = common / qn
            if grams(str(note.get("title") or "")) & q:
                score += 1.0  # 标题命中加权
            if score >= min_score:
                scored.append((score, dict(note)))
        scored.sort(key=lambda item: (-item[0], -float(item[1].get("updated_at") or 0)))
        return scored[: max(1, limit)]

    def touch(self, note_id: str) -> None:
        with self._lock:
            for note in self._notes:
                if note.get("id") == note_id:
                    note["hits"] = int(note.get("hits") or 0) + 1
                    return
