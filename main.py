"""她自己的笔记本（astrbot_plugin_notes）

完全独立的成长型知识插件：不依赖、不修改任何其它插件。

* 三个工具：notes_search / notes_write / notes_fetch
* 对话时自动把相关笔记带进上下文
* 自带面板页（数据管理 → 插件 → 她自己的笔记本）可以查看、编辑、删除、导入导出

数据只落在 data/plugin_data/astrbot_plugin_notes/notes.jsonl。
"""

from __future__ import annotations

import json
import os
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.agent.message import TextPart
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .store import NoteStore
from .tools import (
    TRUST_LABEL,
    TRUST_LEVELS,
    NotesCorrectTool,
    NotesFetchTool,
    NotesSearchTool,
    NotesWriteTool,
)

PLUGIN_NAME = "astrbot_plugin_notes"
# 面板桥接会把相对 endpoint 拼成 /api/plug/<插件名>/<endpoint>，
# 所以这里注册的前缀是 /<插件名>，最终路由形如 /astrbot_plugin_notes/list
API_PREFIX = f"/{PLUGIN_NAME}"

try:  # Quart 是 AstrBot 自带的，拿不到也不该让整个插件起不来
    from quart import request
except Exception:  # pragma: no cover
    request = None


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p.strip().lower() for p in value.replace("，", ",").split(",") if p.strip()]
    return []


@register(
    PLUGIN_NAME,
    "若剑清",
    "她自己的笔记本：把查到的、值得留的结论存下来，下次自动带上，并标注来源与可信度。",
    "0.5.0",
    "",
)
class NotesPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | dict | None = None) -> None:
        super().__init__(context)
        self.config = config or {}

        data_dir = os.path.join(get_astrbot_plugin_data_path(), PLUGIN_NAME)
        self.store = NoteStore(os.path.join(data_dir, "notes.jsonl"))

        self.enabled = self._bool("enabled", True)
        self.inject_enabled = self._bool("inject_enabled", True)
        self.inject_limit = max(1, min(self._int("inject_limit", 2), 5))
        self.min_score = self._float("min_score", 1.0)
        self.fetch_enabled = self._bool("fetch_enabled", True)
        self.fetch_timeout = self._float("fetch_timeout", 20.0)
        self.fetch_max_chars = self._int("fetch_max_chars", 6000)

        self.wiki_domains = _as_list(self.config.get("wiki_domains"))
        self.guide_domains = _as_list(self.config.get("guide_domains"))

        self.tools: list[Any] = [
            NotesSearchTool(store=self.store),
            NotesWriteTool(store=self.store, trust_of=self.trust_of),
            NotesCorrectTool(store=self.store),
        ]
        if self.fetch_enabled:
            self.tools.append(
                NotesFetchTool(
                    store=self.store,
                    timeout=self.fetch_timeout,
                    max_chars=self.fetch_max_chars,
                )
            )
        self.context.add_llm_tools(*self.tools)
        self._register_web_apis()
        logger.info(
            "[Notes] 笔记本加载完成：%s 条，数据路径 %s",
            self.store.stats().get("total"),
            self.store.path,
        )

    # ---------------- 配置工具 ----------------

    def _bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except Exception:
            return default

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self.config.get(key, default))
        except Exception:
            return default

    def trust_of(self, source: str) -> str:
        url = (source or "").lower()
        if not url:
            return "unknown"
        for domain in self.wiki_domains:
            if domain and domain in url:
                return "high"
        for domain in self.guide_domains:
            if domain and domain in url:
                return "medium"
        return "low"

    # ---------------- 面板 API ----------------

    def _register_web_apis(self) -> None:
        register = getattr(self.context, "register_web_api", None)
        if not callable(register):
            logger.info("[Notes] 当前 AstrBot 版本不支持插件 Web API，跳过面板注册")
            return
        routes = [
            ("/list", self.api_list, ["GET"], "列出笔记"),
            ("/save", self.api_save, ["POST"], "新增或更新一条笔记"),
            ("/delete", self.api_delete, ["POST"], "删除一条笔记"),
            ("/import", self.api_import, ["POST"], "批量导入笔记"),
            ("/stats", self.api_stats, ["GET"], "笔记本统计"),
        ]
        for path, handler, methods, desc in routes:
            try:
                register(f"{API_PREFIX}{path}", handler, methods, desc)
            except Exception as exc:
                logger.warning("[Notes] 注册面板 API 失败 %s: %s", path, exc)

    async def api_list(self):
        items = self.store.all()
        items.sort(key=lambda n: -float(n.get("updated_at") or 0))
        for note in items:
            note["trust_label"] = TRUST_LABEL.get(str(note.get("trust")), "未标注")
        return {"ok": True, "items": items, "stats": self.store.stats()}

    async def api_stats(self):
        return {"ok": True, "stats": self.store.stats()}

    async def api_save(self):
        payload = await self._json_body()
        title = str(payload.get("title") or "").strip()
        body = str(payload.get("body") or "").strip()
        if not title or not body:
            return {"ok": False, "error": "标题和正文都不能为空"}
        note_id = str(payload.get("id") or "").strip()
        source = str(payload.get("source") or "").strip()
        tags = payload.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        # 面板里手动选的可信度优先；没选才按来源域名自动分级
        trust = str(payload.get("trust") or "").strip().lower()
        if trust not in TRUST_LEVELS:
            trust = self.trust_of(source) if source else "unknown"
        if note_id:
            updated = self.store.update(
                note_id,
                title=title,
                body=body,
                source=source,
                trust=trust,
                tags=[str(t).strip() for t in tags if str(t).strip()],
            )
            if not updated:
                return {"ok": False, "error": "没找到这条笔记"}
            return {"ok": True, "note": updated}
        note = self.store.add(
            title=title,
            body=body,
            source=source,
            trust=trust,
            tags=[str(t).strip() for t in tags if str(t).strip()],
        )
        return {"ok": True, "note": note}

    async def api_delete(self):
        payload = await self._json_body()
        note_id = str(payload.get("id") or "").strip()
        if not note_id:
            return {"ok": False, "error": "缺少 id"}
        return {"ok": self.store.delete(note_id)}

    async def api_import(self):
        payload = await self._json_body()
        content = payload.get("content")
        name = str(payload.get("name") or "").strip()
        if isinstance(content, list):
            rows = content
        elif isinstance(content, str) and content.strip():
            rows = self._parse_text(content, name)
        else:
            return {"ok": False, "error": "没有可导入的内容"}
        added = 0
        updated = 0
        before_ids = {n.get("id") for n in self.store.all()}
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            body = str(row.get("body") or "").strip()
            if not title or not body:
                continue
            source = str(row.get("source") or "").strip()
            note = self.store.add(
                title=title,
                body=body,
                source=source,
                trust=str(row.get("trust") or (self.trust_of(source) if source else "unknown")),
                tags=row.get("tags") if isinstance(row.get("tags"), list) else [],
            )
            if note.get("id") in before_ids:
                updated += 1
            else:
                added += 1
        return {"ok": True, "added": added, "updated": updated, "total": len(rows)}

    @staticmethod
    def _parse_text(text: str, name: str) -> list[dict]:
        raw = text.strip()
        if not raw:
            return []
        # 1) JSON 数组 / 单个对象
        if raw[0] in "[{":
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return [parsed]
                if isinstance(parsed, list):
                    return [p for p in parsed if isinstance(p, dict)]
            except Exception:
                pass
        # 2) Markdown：按 # / ## 标题切块
        rows: list[dict] = []
        title = ""
        buf: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                if title and buf:
                    rows.append({"title": title, "body": "\n".join(buf).strip()})
                title = stripped.lstrip("#").strip() or "无标题"
                buf = []
            else:
                buf.append(line)
        if title and buf:
            rows.append({"title": title, "body": "\n".join(buf).strip()})
        if rows:
            return rows
        # 3) 纯文本：整篇一条
        fallback_title = os.path.splitext(name or "导入的笔记")[0] or "导入的笔记"
        return [{"title": fallback_title, "body": raw}]

    async def _json_body(self) -> dict:
        if request is None:
            return {}
        try:
            payload = await request.get_json(silent=True)
        except Exception:
            payload = None
        return payload if isinstance(payload, dict) else {}

    # ---------------- 自动注入 ----------------

    @filter.on_llm_request()
    async def inject_notes(self, event: AstrMessageEvent, req: Any) -> None:
        if not self.enabled or not self.inject_enabled:
            return
        text = (getattr(event, "message_str", "") or "").strip()
        if not text or text.startswith(("/笔记", "笔记 ")):
            return
        hits = self.store.search(text, limit=self.inject_limit, min_score=self.min_score)
        if not hits:
            return
        lines = ["【你笔记本里查到的东西（你自己以前记的）】"]
        for _score, note in hits:
            trust = {
                "high": "可信",
                "medium": "一般",
                "low": "存疑",
                "untrusted": "不可信（这条你以前记错过）",
            }.get(str(note.get("trust")), "未标注")
            body = str(note.get("body") or "").strip()
            if len(body) > 500:
                body = body[:500] + "…"
            lines.append(
                f"- {note.get('title') or '无标题'}（{trust}｜{note.get('source') or '无来源'}）：{body}"
            )
        lines.append("标「存疑」的别当定论；标「不可信」的是错误版本，只能用来避开旧错误，不能当事实说。")
        block = "\n".join(lines)
        try:
            parts = getattr(req, "extra_user_content_parts", None)
            if not isinstance(parts, list):
                parts = []
                req.extra_user_content_parts = parts
            # 只对本次请求可见：mark_as_temp() 标记后不落历史，
            # 也不碰 req.system_prompt —— 避免每轮改写系统提示词击穿前缀缓存。
            parts.append(TextPart(text=block).mark_as_temp())
        except Exception as exc:
            logger.debug("[Notes] 记忆块注入失败: %s", exc)
            return
        for _score, note in hits:
            self.store.touch(str(note.get("id")))

    # ---------------- 管理命令 ----------------

    @filter.command("笔记")
    async def notes_command(self, event: AstrMessageEvent):
        """管理笔记本：笔记 / 笔记 搜索 xx / 笔记 删除 id / 笔记 导出"""
        args = (getattr(event, "message_str", "") or "").strip()
        for prefix in ("/笔记", "笔记"):
            if args.startswith(prefix):
                args = args[len(prefix) :].strip()
                break
        action, _, rest = args.partition(" ")
        rest = rest.strip()

        if action in ("", "统计", "状态"):
            stats = self.store.stats()
            yield event.plain_result(
                f"笔记本共 {stats['total']} 条｜"
                + "、".join(f"{k} {v}" for k, v in stats["by_trust"].items())
                + "\n用法：笔记 搜索 关键词 / 笔记 删除 id / 笔记 导出"
            )
            return

        if action in ("搜索", "查"):
            if not rest:
                yield event.plain_result("要查什么？例：笔记 搜索 雷横默")
                return
            hits = self.store.search(rest, limit=5)
            if not hits:
                yield event.plain_result("没找到相关笔记。")
                return
            lines = []
            for score, note in hits:
                lines.append(
                    f"[{note.get('id')}] {note.get('title')}（{note.get('trust')}，{score:.1f}）\n"
                    f"  {str(note.get('body'))[:180]}"
                )
            yield event.plain_result("\n".join(lines))
            return

        if action in ("删除", "删"):
            if not rest:
                yield event.plain_result("要删哪条？例：笔记 删除 3f2a1b9c")
                return
            ok = self.store.delete(rest)
            yield event.plain_result("已删除。" if ok else "没找到这个 id。")
            return

        if action in ("导出", "备份"):
            dump = json.dumps(self.store.all(), ensure_ascii=False, indent=2)
            path = os.path.join(os.path.dirname(self.store.path), "notes_export.json")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(dump)
                yield event.plain_result(f"已导出到 {path}")
            except Exception as exc:
                yield event.plain_result(f"导出失败：{exc}")
            return

        yield event.plain_result(
            "用法：\n笔记 搜索 关键词\n笔记 删除 id\n笔记 导出\n笔记 统计"
        )

    async def terminate(self) -> None:
        for tool in getattr(self, "tools", []):
            try:
                self.context.provider_manager.llm_tools.remove_func(tool.name)
            except Exception:
                pass
        logger.info("[Notes] 笔记本插件已停止。")
