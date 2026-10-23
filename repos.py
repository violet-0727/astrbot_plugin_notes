"""仓库：把笔记分到不同主题下，避免全挤在一起。

数据在 data/plugin_data/astrbot_plugin_notes/repos.json：

    {"repos": [
      {"id": "main", "name": "主仓库", "icon": "📚", "order": 0, "created_at": 1792...}
    ]}
"""

from __future__ import annotations

import json
import os
import time
import uuid

DEFAULT = {"id": "main", "name": "主仓库", "icon": "📚", "order": 0}


class RepoStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._repos: list[dict] = []
        self.load()
        if not self._repos:
            self._repos = [dict(DEFAULT, created_at=time.time())]
            self.save()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("repos") if isinstance(data, dict) else data
            self._repos = [r for r in (rows or []) if isinstance(r, dict) and r.get("id")]
        except FileNotFoundError:
            self._repos = []
        except Exception:
            self._repos = []
        if not any(r.get("id") == "main" for r in self._repos):
            self._repos.insert(0, dict(DEFAULT, created_at=time.time()))
        self._sort()

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"repos": self._repos}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _sort(self) -> None:
        self._repos.sort(key=lambda r: (int(r.get("order") or 0), str(r.get("name") or "")))

    def all(self) -> list[dict]:
        return [dict(r) for r in self._repos]

    def get(self, repo_id: str) -> dict | None:
        for r in self._repos:
            if r.get("id") == repo_id:
                return dict(r)
        return None

    def create(self, name: str, icon: str = "📁") -> dict:
        name = (name or "").strip()[:40] or "新仓库"
        repo = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "icon": (icon or "📁").strip()[:4] or "📁",
            "order": len(self._repos),
            "created_at": time.time(),
        }
        self._repos.append(repo)
        self.save()
        return dict(repo)

    def update(self, repo_id: str, name: str | None = None, icon: str | None = None, order: int | None = None) -> dict | None:
        for r in self._repos:
            if r.get("id") == repo_id:
                if name is not None and str(name).strip():
                    r["name"] = str(name).strip()[:40]
                if icon is not None and str(icon).strip():
                    r["icon"] = str(icon).strip()[:4]
                if order is not None:
                    r["order"] = int(order)
                self._sort()
                self.save()
                return dict(r)
        return None

    def delete(self, repo_id: str) -> bool:
        """主仓库不能删；其余删掉后，笔记由调用方搬回主仓库。"""
        if repo_id == "main":
            return False
        before = len(self._repos)
        self._repos = [r for r in self._repos if r.get("id") != repo_id]
        if len(self._repos) == before:
            return False
        self.save()
        return True
