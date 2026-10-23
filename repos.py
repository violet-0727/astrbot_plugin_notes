"""仓库：主题分桶 + 每个仓库自己的展示/记录参数。

数据在 data/plugin_data/astrbot_plugin_notes/repos.json：

    {"repos": [{
        "id": "main", "name": "主仓库", "icon": "📚", "order": 0,
        "max_notes": 0,            # 记录阈值：0 = 不限，超过只提醒不删除
        "tree_depth": 2,           # 分类级数 1~3
        "cluster_threshold": 0.6   # 标签合并松紧
    }]}
"""

from __future__ import annotations

import json
import os
import time
import uuid

DEFAULT = {
    "id": "main",
    "name": "主仓库",
    "icon": "📚",
    "order": 0,
    "max_notes": 0,
    "tree_depth": 2,
    "cluster_threshold": 0.6,
}

NUM_RULES = {
    "max_notes": (0, 5000, int),
    "tree_depth": (1, 3, int),
    "cluster_threshold": (0.3, 0.95, float),
    "order": (0, 9999, int),
}


def _clean(row: dict) -> dict:
    out = dict(DEFAULT)
    out.update({k: row[k] for k in DEFAULT if k in row})
    out["id"] = str(out.get("id") or "").strip()
    out["name"] = (str(out.get("name") or "未命名").strip() or "未命名")[:40]
    out["icon"] = (str(out.get("icon") or "📁").strip() or "📁")[:4]
    for key, (low, high, typ) in NUM_RULES.items():
        try:
            value = typ(out.get(key, DEFAULT[key]))
        except Exception:
            value = DEFAULT[key]
        out[key] = max(low, min(high, value))
    return out


class RepoStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._repos: list[dict] = []
        self.load()
        if not self._repos:
            self._repos = [_clean(dict(DEFAULT, created_at=time.time()))]
            self.save()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            rows = data.get("repos") if isinstance(data, dict) else data
            self._repos = [_clean(r) for r in (rows or []) if isinstance(r, dict) and r.get("id")]
        except FileNotFoundError:
            self._repos = []
        except Exception:
            self._repos = []
        if not any(r.get("id") == "main" for r in self._repos):
            self._repos.insert(0, _clean(dict(DEFAULT, created_at=time.time())))
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

    def create(self, name: str, icon: str = "📁", **opts) -> dict:
        name = (name or "").strip()[:40] or "新仓库"
        repo = dict(DEFAULT)
        repo.update(
            {
                "id": uuid.uuid4().hex[:8],
                "name": name,
                "icon": (icon or "📁").strip()[:4] or "📁",
                "order": len(self._repos),
                "created_at": time.time(),
            }
        )
        for key in ("max_notes", "tree_depth", "cluster_threshold"):
            if opts.get(key) is not None:
                repo[key] = opts[key]
        repo = _clean(repo)
        self._repos.append(repo)
        self.save()
        return dict(repo)

    def update(self, repo_id: str, **fields) -> dict | None:
        for index, row in enumerate(self._repos):
            if row.get("id") != repo_id:
                continue
            merged = dict(row)
            for key in ("name", "icon", "max_notes", "tree_depth", "cluster_threshold", "order"):
                if key in fields and fields[key] is not None:
                    merged[key] = fields[key]
            merged = _clean(merged)
            merged["id"] = repo_id
            self._repos[index] = merged
            self._sort()
            self.save()
            return dict(merged)
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
