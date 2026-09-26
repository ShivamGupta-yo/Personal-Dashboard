"""Newest and Trending NLP papers for the topics listed in config.json using the arXiv API."""
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

ARXIV_API = "http://export.arxiv.org/api/query"

def _squash(text):
    return re.sub(r"\s+", " ", text or "").strip()

def build(cfg):
    latest_found, warnings = {}, []
    topic_buckets = {}
    
    # Create an unverified SSL context to bypass local machine certificate errors
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    for q in cfg.get("queries", []):
        label = q["label"]
        topic_buckets[label] = []
        
        try:
            query_str = q["query"]
            params = {
                "search_query": query_str,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": cfg.get("per_query", 10)
            }
            url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
            
            req = urllib.request.Request(url, headers={"User-Agent": "ResearchDashboard/1.0"})
            with urllib.request.urlopen(req, context=ssl_context, timeout=15) as resp:
                xml_data = resp.read()
                
            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            
            for entry in root.findall("atom:entry", ns):
                title = _squash(entry.find("atom:title", ns).text)
                summary = _squash(entry.find("atom:summary", ns).text)
                id_url = entry.find("atom:id", ns).text
                
                paper_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else id_url
                pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
                
                published_str = entry.find("atom:published", ns).text
                pub_date = published_str.split("T")[0] if published_str else ""
                
                ts = 0
                if pub_date:
                    try:
                        ts = int(datetime.strptime(pub_date, "%Y-%m-%d").timestamp())
                    except ValueError:
                        pass
                        
                authors = [_squash(author.find("atom:name", ns).text) for author in entry.findall("atom:author", ns)]
                
                paper_data = {
                    "id": paper_id,
                    "title": title,
                    "authors": authors,
                    "abstract": summary[:900],
                    "published": pub_date,
                    "ts": ts,
                    "url": id_url,
                    "pdf": pdf_url,
                    "topics": [label, "Article"],
                    "cited_by_count": 0
                }
                
                if paper_id in latest_found:
                    if label not in latest_found[paper_id]["topics"]:
                        latest_found[paper_id]["topics"].append(label)
                    topic_buckets[label].append(latest_found[paper_id])
                else:
                    latest_found[paper_id] = paper_data
                    topic_buckets[label].append(paper_data)
                    
        except Exception as exc:
            warnings.append(f"{label}: {str(exc)}")
            continue

    diverse_papers = []
    added_ids = set()
    for label in topic_buckets:
        topic_buckets[label].sort(key=lambda p: -p["ts"])
        
    global_max = cfg.get("max", 25)
    while len(diverse_papers) < global_max:
        added_in_round = False
        for label in topic_buckets:
            while topic_buckets[label]:
                p = topic_buckets[label].pop(0)
                if p["id"] not in added_ids:
                    diverse_papers.append(p)
                    added_ids.add(p["id"])
                    added_in_round = True
                    break
            if len(diverse_papers) >= global_max:
                break
        if not added_in_round:
            break
            
    papers = sorted(diverse_papers, key=lambda p: -p["ts"])
    
    # Populate trending with top recent papers so the section is active
    trending_papers = []
    for p in papers[:5]:
        t_copy = p.copy()
        if "🔥 Trending" not in t_copy["topics"]:
            t_copy["topics"] = ["🔥 Trending"] + t_copy["topics"]
        trending_papers.append(t_copy)
    
    return {
        "papers": papers, 
        "trending": trending_papers, 
        "warnings": warnings, 
        "fetched_at": datetime.now().isoformat(timespec="seconds")
    }