"""Rule-based email importance. Every point added or removed comes with a reason
so the dashboard can show the user why a message is on the list."""
import re


def score_message(msg, cfg):
    score = 0
    reasons = []
    labels = set(msg.get("labels", []))

    if "IMPORTANT" in labels:
        score += 3
        reasons.append("Gmail marked it important")
    if "STARRED" in labels:
        score += 3
        reasons.append("you starred it")
    if "UNREAD" in labels:
        score += 2
        reasons.append("unread")
    if "CATEGORY_PERSONAL" in labels:
        score += 1
    if "CATEGORY_PROMOTIONS" in labels:
        score -= 4
        reasons.append("looks promotional")
    elif "CATEGORY_SOCIAL" in labels:
        score -= 3
        reasons.append("social notification")
    elif "CATEGORY_UPDATES" in labels or "CATEGORY_FORUMS" in labels:
        score -= 1

    sender = f"{msg.get('from_name', '')} {msg.get('from_email', '')}".lower()
    if any(v.lower() in sender for v in cfg.get("vip_senders", [])):
        score += 5
        reasons.append("from a sender you listed as VIP")
    if any(p.lower() in sender for p in cfg.get("demote_senders", [])):
        score -= 2

    text = f"{msg.get('subject', '')} {msg.get('snippet', '')}".lower()
    hits = [
        k for k in cfg.get("keywords", [])
        if re.search(r"(?<!\w)" + re.escape(k.lower()) + r"(?!\w)", text)
    ]
    if hits:
        score += 2 * min(len(hits), 2)
        reasons.append("mentions " + ", ".join(hits[:2]))

    return score, reasons


def level(score, min_score):
    if score >= min_score + 4:
        return "high"
    if score >= min_score:
        return "medium"
    return "low"
