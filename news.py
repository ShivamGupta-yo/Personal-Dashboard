"""Builds the daily top-10 from RSS feeds.

Ranking idea (simple and explainable):
  - prominence: stories a feed puts near its top score higher
  - freshness: newer stories score higher
  - coverage: the same story appearing in several outlets gets a bonus
  - variety: no single outlet can take more than `per_source_cap` slots
"""
import calendar
import difflib
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import feedparser
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
TAGS = re.compile(r"<[^>]+>")
STOPWORDS = set(
    "the a an of to in on for and or at is are was were be by with from as it its that this "
    "after over says say new".split()
)


def _clean(text):
    return re.sub(r"\s+", " ", html.unescape(TAGS.sub(" ", text or ""))).strip()


def _tokens(title):
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOPWORDS and len(w) > 2}


def _similar(a, b):
    ta, tb = a["_tok"], b["_tok"]
    if ta and tb and len(ta & tb) / len(ta | tb) >= 0.5:
        return True
    return difflib.SequenceMatcher(None, a["title"].lower(), b["title"].lower()).ratio() >= 0.8


def _fetch_feed(feed, per_feed, max_age_hours):
    resp = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if not parsed.entries:
        raise ValueError("feed returned no entries")

    now = time.time()
    items = []
    for rank, entry in enumerate(parsed.entries[:per_feed]):
        title = _clean(entry.get("title"))
        link = entry.get("link", "")
        if not title or not link.startswith(("http://", "https://")):
            continue
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        ts = calendar.timegm(stamp) if stamp else now
        age_hours = max(0.0, (now - ts) / 3600)
        if age_hours > max_age_hours:
            continue
        prominence = 1 - rank / per_feed
        freshness = max(0.0, 1 - age_hours / max_age_hours)
        items.append(
            {
                "title": title,
                "url": link,
                "source": feed["name"],
                "category": feed.get("category", "General"),
                "ts": ts,
                "summary": _clean(entry.get("summary"))[:220],
                "score": 0.6 * prominence + 0.4 * freshness,
            }
        )
    return items


def select_top(pool, count, cap):
    """Cluster near-duplicate stories, boost multi-outlet stories, cap per source."""
    pool = [dict(item, _tok=_tokens(item["title"])) for item in pool]
    clusters = []
    for item in sorted(pool, key=lambda x: -x["score"]):
        for cluster in clusters:
            if _similar(cluster, item):
                if item["source"] != cluster["source"] and item["source"] not in cluster["also_in"]:
                    cluster["also_in"].append(item["source"])
                break
        else:
            item["also_in"] = []
            clusters.append(item)

    for c in clusters:
        c["rank_score"] = c["score"] + 0.15 * min(3, len(c["also_in"]))
    clusters.sort(key=lambda c: -c["rank_score"])

    picked, per_source = [], {}
    for c in clusters:
        if len(picked) >= count:
            break
        if per_source.get(c["source"], 0) >= cap:
            continue
        picked.append(c)
        per_source[c["source"]] = per_source.get(c["source"], 0) + 1
    for c in clusters:  # not enough variety available: fill the remaining slots
        if len(picked) >= count:
            break
        if c not in picked:
            picked.append(c)

    return [{k: v for k, v in c.items() if not k.startswith("_") and k != "rank_score"} for c in picked]


def build(cfg):
    pool, warnings = [], []

    def work(feed):
        try:
            return feed, _fetch_feed(feed, cfg["per_feed"], cfg["max_age_hours"]), None
        except Exception as exc:  # one broken feed must not break the page
            return feed, [], str(exc).splitlines()[0][:120] if str(exc) else exc.__class__.__name__

    with ThreadPoolExecutor(max_workers=8) as pool_executor:
        for feed, items, error in pool_executor.map(work, cfg["feeds"]):
            pool.extend(items)
            if error:
                warnings.append(f"{feed['name']}: {error}")

    if not pool:
        raise RuntimeError("No stories could be fetched. " + "; ".join(warnings[:3]))

    count, cap = cfg["count"], cfg["per_source_cap"]
    categories = sorted({item["category"] for item in pool})
    result = {"All": select_top(pool, count, cap)}
    for cat in categories:
        result[cat] = select_top([i for i in pool if i["category"] == cat], count, cap)

    return {
        "categories": ["All"] + categories,
        "items": result,
        "warnings": warnings,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
