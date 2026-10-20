"""给模型用的三个工具：查笔记、写笔记、抓网页。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent

from .fetch import fetch_url_text

TRUST_LABEL = {
    "high": "可信（wiki/官方资料）",
    "medium": "一般（攻略/社区）",
    "low": "存疑（来源不明）",
    "untrusted": "不可信（已确认有误）",
    "unknown": "未标注来源",
}
TRUST_LEVELS = ("high", "medium", "low", "untrusted", "unknown")


@dataclass
class NotesSearchTool(FunctionTool):
    store: Any = field(repr=False, default=None)
    name: str = "notes_search"
    description: str = (
        "在你自己积累的笔记本里检索。回答具体数据、攻略、人名、设定之前，"
        "先用它查一遍你以前记过什么；命中说明以前查过，优先用自己的笔记，"
        "比重新搜更快也更稳。没有命中再考虑联网搜索。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "要查的关键词或问题"},
                "limit": {
                    "type": "integer",
                    "description": "返回条数，1-5，默认 3",
                },
            },
            "required": ["query"],
        }
    )

    async def run(self, event: AstrMessageEvent, query: str, limit: int = 3) -> str:
        if not query.strip():
            return "错误：query 不能为空。"
        limit = max(1, min(int(limit or 3), 5))
        hits = self.store.search(query, limit=limit)
        if not hits:
            return "笔记本里没有相关记录。"
        lines = []
        for score, note in hits:
            trust = TRUST_LABEL.get(str(note.get("trust")), "未标注来源")
            source = note.get("source") or "无来源"
            body = str(note.get("body") or "").strip()
            if len(body) > 600:
                body = body[:600] + "…"
            lines.append(
                f"### {note.get('title') or '无标题'}（{trust}）\n"
                f"来源：{source}\n{body}"
            )
            self.store.touch(str(note.get("id")))
        return "\n\n".join(lines)


@dataclass
class NotesWriteTool(FunctionTool):
    store: Any = field(repr=False, default=None)
    trust_of: Callable[[str], str] = field(repr=False, default=lambda _s: "unknown")
    name: str = "notes_write"
    description: str = (
        "把这次查到的、以后还会用到的结论写进你自己的笔记本。"
        "只记稳定的结论和数值，不要抄整段网页；一条笔记一个主题。"
        "同一个来源再写会覆盖旧内容，所以可以放心更新。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "笔记标题，短，例如「雷横默 人格要点」"},
                "body": {"type": "string", "description": "结论正文，可以分行，只写要点"},
                "source": {"type": "string", "description": "来源 URL 或出处说明，没有就留空"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选标签，例如 limbus、EGO",
                },
            },
            "required": ["title", "body"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        title: str,
        body: str,
        source: str = "",
        tags: list[str] | None = None,
    ) -> str:
        title = (title or "").strip()
        body = (body or "").strip()
        if not title or not body:
            return "错误：title 和 body 都不能为空。"
        if len(body) > 4000:
            body = body[:4000]
        trust = self.trust_of(source)
        note = self.store.add(
            title=title,
            body=body,
            source=source,
            trust=trust,
            tags=[str(t).strip() for t in (tags or []) if str(t).strip()],
        )
        return f"已记下：{note.get('title')}（{TRUST_LABEL.get(trust, trust)}，id={note.get('id')}）"


@dataclass
class NotesFetchTool(FunctionTool):
    store: Any = field(repr=False, default=None)
    timeout: float = field(default=20.0)
    max_chars: int = field(default=6000)
    name: str = "notes_fetch"
    description: str = (
        "抓取一个网页的正文并返回纯文本，用来核对细节或补充资料。"
        "抓完请自己判断：只把可靠、稳定的结论用 notes_write 记下来，"
        "广告、标题党、和主题无关的内容不要记。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要抓取的公开 http(s) 地址"},
            },
            "required": ["url"],
        }
    )

    async def run(self, event: AstrMessageEvent, url: str) -> str:
        url = (url or "").strip()
        if not url:
            return "错误：url 不能为空。"
        try:
            text = await asyncio.to_thread(
                fetch_url_text, url, float(self.timeout), int(self.max_chars)
            )
        except Exception as exc:
            return f"抓取失败：{exc}"
        return f"来源：{url}\n\n{text}"


@dataclass
class NotesCorrectTool(FunctionTool):
    """被用户纠正时用：旧版本归档为「不可信」，本条目换成正确版本。"""

    store: Any = field(repr=False, default=None)
    name: str = "notes_correct"
    description: str = (
        "当用户指出你笔记里的某条是错的，用这个工具更正。"
        "它会把写错的旧内容归档成一条「不可信」的笔记（以后提醒你别再犯），"
        "原笔记则替换成你改正后的内容。只改确实错的地方，不要整条重写。"
    )
    parameters: dict = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "要更正的笔记 id，知道就直接填"},
                "title_or_keyword": {
                    "type": "string",
                    "description": "不知道 id 时填标题或关键词，用它来定位笔记",
                },
                "corrected_body": {
                    "type": "string",
                    "description": "改正后的完整正文（替换掉旧的正文）",
                },
                "reason": {
                    "type": "string",
                    "description": "错在哪，一句话，会写进旧版本的备注里",
                },
            },
            "required": ["corrected_body"],
        }
    )

    async def run(
        self,
        event: AstrMessageEvent,
        corrected_body: str,
        note_id: str = "",
        title_or_keyword: str = "",
        reason: str = "",
    ) -> str:
        corrected_body = (corrected_body or "").strip()
        if not corrected_body:
            return "错误：corrected_body 不能为空。"

        note = None
        if note_id:
            for item in self.store.all():
                if item.get("id") == note_id:
                    note = item
                    break
        if note is None and title_or_keyword.strip():
            hits = self.store.search(title_or_keyword.strip(), limit=1, min_score=0.8)
            if hits:
                note = hits[0][1]
        if note is None:
            return "没找到要更正的笔记，可以先用 notes_search 查一下。"

        old_body = str(note.get("body") or "").strip()
        if old_body == corrected_body:
            return "新旧内容一样，没有需要更正的地方。"

        archived = self.store.add(
            title=f"❌ 旧版本：{note.get('title') or '无标题'}",
            body=f"（{reason.strip() or '被用户指出有误'}）\n\n{old_body}",
            source=str(note.get("source") or ""),
            trust="untrusted",
            tags=list(dict.fromkeys([*(note.get("tags") or []), "错误版本"])),
            dedupe=False,
        )
        updated = self.store.update(note["id"], body=corrected_body)
        times = self.store.increment_corrections(note["id"])
        if not updated:
            return "更正失败：原笔记不存在了。"

        return (
            f"已更正：{updated.get('title')}（累计被更正 {times} 次）\n"
            f"旧版本已归档为「不可信」：{archived.get('title')}（id={archived.get('id')}）"
        )
