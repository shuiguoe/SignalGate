from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    published: str  # raw
    source: str     # hostname


def _strip_html(s: str) -> str:
    s = s or ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _guess_iso_ts(raw: str) -> str:
    """
    v0.1：尽力解析常见 RSS/Atom 时间；失败则用当前 UTC
    """
    raw = (raw or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()

    # Atom: 2026-02-07T00:00:00Z
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    # RSS pubDate 常见格式太多，v0.1 不做重度解析
    return datetime.now(timezone.utc).isoformat()


def _fetch_bytes(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SignalGate/0.1 (+https://github.com/shuiguoe/SignalGate)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _first_text(el: ET.Element | None, paths: list[str]) -> str:
    if el is None:
        return ""
    for p in paths:
        node = el.find(p)
        if node is not None and (node.text or "").strip():
            return (node.text or "").strip()
    return ""


def _parse_rss_or_atom(xml_bytes: bytes, base_url: str) -> list[FeedItem]:
    root = ET.fromstring(xml_bytes)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    host = urllib.parse.urlparse(base_url).hostname or "unknown"

    items: list[FeedItem] = []

    # RSS 2.0: <rss><channel><item>...
    channel = root.find("channel")
    if channel is not None:
        for it in channel.findall("item"):
            title = _first_text(it, ["title"])
            link = _first_text(it, ["link"])
            desc = _first_text(it, ["description"])
            pub = _first_text(it, ["pubDate"])

            items.append(
                FeedItem(
                    title=_strip_html(title),
                    link=(link or "").strip(),
                    summary=_strip_html(desc),
                    published=pub,
                    source=host,
                )
            )
        return items

    # Atom: <feed><entry>...
    if root.tag.endswith("feed"):
        for e in root.findall("atom:entry", ns) + root.findall("entry"):
            title = _first_text(e, ["atom:title", "title"])
            summary = _first_text(e, ["atom:summary", "summary", "atom:content", "content"])
            updated = _first_text(e, ["atom:updated", "updated", "atom:published", "published"])

            link = ""
            # atom link: <link href="..."/>
            ln = e.find("atom:link", ns) or e.find("link")
            if ln is not None:
                href = ln.attrib.get("href", "").strip()
                if href:
                    link = href

            items.append(
                FeedItem(
                    title=_strip_html(title),
                    link=link,
                    summary=_strip_html(summary),
                    published=updated,
                    source=host,
                )
            )
        return items

    return items


def _event_id(item: FeedItem) -> str:
    key = f"{item.source}|{item.link}|{item.title}".encode("utf-8", errors="ignore")
    h = hashlib.sha1(key).hexdigest()[:16]
    return f"evt_rss_{h}"


def _write_event(inbox_dir: Path, item: FeedItem) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)

    eid = _event_id(item)
    ts = _guess_iso_ts(item.published)
    url = (item.link or "").strip()

    obj = {
        "event_id": eid,
        "ts": ts,
        "title": item.title or "",
        "body": item.summary or "",
        "url": url,
        "source": item.source,
        # v0.1：RSS 默认给 B（可在后续按宪法做 source-tier 映射/加权）
        "source_tier": "B",
        "tags": [],
    }

    path = inbox_dir / f"{eid}.json"
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fetch_rss_to_inbox(url: str, inbox_dir: Path, limit: int = 20) -> int:
    xml_bytes = _fetch_bytes(url)
    items = _parse_rss_or_atom(xml_bytes, url)

    n = 0
    for it in items[: max(0, int(limit))]:
        # 必须有 link 或 title，否则跳过
        if not (it.link or it.title):
            continue
        _write_event(inbox_dir, it)
        n += 1
    return n
