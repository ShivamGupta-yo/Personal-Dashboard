"""Newest arXiv papers for the topics listed in config.json (free API, no key)."""
import calendar
import re
import time
from datetime import datetime

import feedparser
import requests

ARXIV_API = "https://export.arxiv.org/api/query"
UA = "MorningBrief/1.0 (personal local use)"


def _squash(text):
    return re.sub(r"\s+", " ", text or "").strip()


def build(cfg):
    print("\n--- DEBUG: CURRENT QUERIES ---")
    print(cfg["queries"])
    print("------------------------------\n")
    
    found, warnings = {}, []
    for i, q in enumerate(cfg["queries"]):
        if i:
            time.sleep(3)  # arXiv asks for at most one request every three seconds
        try:
            resp = requests.get(
                ARXIV_API,
                params={
                    "search_query": q["query"],
                    "start": 0,
                    "max_results": cfg.get("per_query", 8),
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                headers={"User-Agent": UA},
                timeout=45,
            )
            resp.raise_for_status()
        except Exception as exc:
            warnings.append(f"{q['label']}: {str(exc).splitlines()[0][:120]}")
            continue

        for entry in feedparser.parse(resp.content).entries:
            pid = entry.get("id", "")
            if not pid:
                continue
            if pid in found:
                if q["label"] not in found[pid]["topics"]:
                    found[pid]["topics"].append(q["label"])
                continue
            stamp = entry.get("published_parsed")
            pdf = next((l["href"] for l in entry.get("links", []) if l.get("type") == "application/pdf"), "")
            found[pid] = {
                "id": pid,
                "title": _squash(entry.get("title")),
                "authors": [a.get("name", "") for a in entry.get("authors", [])],
                "abstract": _squash(entry.get("summary"))[:900],
                "published": entry.get("published", "")[:10],
                "ts": calendar.timegm(stamp) if stamp else 0,
                "url": entry.get("link", pid),
                "pdf": pdf,
                "topics": [q["label"]],
            }

    if not found and warnings:
        raise RuntimeError("arXiv could not be reached. " + "; ".join(warnings[:2]))

    papers = sorted(found.values(), key=lambda p: -p["ts"])[: cfg.get("max", 10)]
    return {"papers": papers, "warnings": warnings, "fetched_at": datetime.now().isoformat(timespec="seconds")}
