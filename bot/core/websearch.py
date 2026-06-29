"""
Lightweight web search + page reader for the autopost/structuring research loop.

Backend: DuckDuckGo's no-API HTML endpoint (html.duckduckgo.com/html/), scraped
with regex — no API key, no extra dependency (httpx only). An optional API key
field is accepted for a future paid backend but DDG is the default and works
without one.

Two primitives the research loop uses:
  • search(query, n)        → top-n results (title, url, snippet);
  • fetch_page(url, limit)  → readable text (truncated) + best-guess publish date,
                              so the model can judge how current a source is.

Everything is best-effort: network/parse failures return empty results rather
than raising, so one bad page never breaks a post.
"""
from __future__ import annotations

import asyncio
import html as ihtml
import logging
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_DDG_URL = "https://html.duckduckgo.com/html/"
_TIMEOUT = 20.0

_RESULT_A = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I
)
_SNIPPET = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S | re.I
)
_TAG = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
_WS = re.compile(r"[ \t\r\f\v]+")
_MULTINL = re.compile(r"\n\s*\n\s*\n+")

_META_DATE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:article:published_time|article:modified_time|'
    r'og:updated_time|date|pubdate|datepublished|dc\.date|dc\.date\.issued)["\'][^>]+'
    r'content=["\']([^"\']+)["\']',
    re.I,
)
_JSONLD_DATE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.I)
_TIME_TAG = re.compile(r'<time[^>]+datetime=["\']([^"\']+)["\']', re.I)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _strip(text: str) -> str:
    return ihtml.unescape(_TAG.sub("", text or "")).strip()


def _real_url(href: str) -> str:
    """DDG wraps targets as //duckduckgo.com/l/?uddg=<encoded>; unwrap to the real URL."""
    if "uddg=" in href:
        q = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
        if q.get("uddg"):
            return unquote(q["uddg"][0])
    if href.startswith("//"):
        return "https:" + href
    return href


async def search(query: str, n: int = 5, api_key: str | None = None) -> list[SearchResult]:
    """Top-n DuckDuckGo results for a query. Returns [] on any failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as client:
            r = await client.post(_DDG_URL, data={"q": query, "kl": "ru-ru"})
            r.raise_for_status()
            body = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("web search failed for %r: %s", query, e)
        return []

    out: list[SearchResult] = []
    snippets = _SNIPPET.findall(body)
    for i, (href, title) in enumerate(_RESULT_A.findall(body)):
        url = _real_url(href)
        if not url.startswith("http"):
            continue
        snip = _strip(snippets[i]) if i < len(snippets) else ""
        out.append(SearchResult(title=_strip(title), url=url, snippet=snip))
        if len(out) >= n:
            break
    return out


def _extract_date(html_text: str) -> str | None:
    for rx in (_META_DATE, _JSONLD_DATE, _TIME_TAG):
        m = rx.search(html_text)
        if m:
            return m.group(1).strip()[:40]
    return None


def _readable(html_text: str, limit: int) -> str:
    text = _SCRIPT_STYLE.sub(" ", html_text)
    text = _TAG.sub(" ", text)
    text = ihtml.unescape(text)
    text = _WS.sub(" ", text)
    text = _MULTINL.sub("\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = text.strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + " …[обрезано]"
    return text


async def fetch_page(url: str, limit: int = 1500) -> dict:
    """Fetch a page → {url, title, date, text}. Best-effort; text='' on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as client:
            r = await client.get(url)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return {"url": url, "title": "", "date": None, "text": ""}
            body = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_page failed for %s: %s", url, e)
        return {"url": url, "title": "", "date": None, "text": ""}

    tmatch = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    title = _strip(tmatch.group(1)) if tmatch else ""
    return {"url": url, "title": title, "date": _extract_date(body), "text": _readable(body, limit)}


async def search_and_read(query: str, n: int, snippet_chars: int,
                          api_key: str | None = None) -> list[dict]:
    """Search, then fetch each result's page content in parallel."""
    results = await search(query, n, api_key)
    pages = await asyncio.gather(*[fetch_page(r.url, snippet_chars) for r in results])
    merged = []
    for res, page in zip(results, pages):
        merged.append({
            "title": page.get("title") or res.title,
            "url": res.url,
            "date": page.get("date"),
            "snippet": res.snippet,
            "text": page.get("text", ""),
        })
    return merged
