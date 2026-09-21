"""Sample data used by demo mode (python app.py --demo). Not real news, mail or papers."""
import time
from datetime import datetime, timedelta

import news as news_module


def _ago(minutes):
    return time.time() - minutes * 60


def mail():
    return {
        "messages": [
            dict(id="demo001", from_name="Prof. Mehta", from_email="mehta@example.edu",
                 subject="Comments on the evaluation section",
                 snippet="I went through the draft. The metric comparison needs a clearer baseline, and please send the revision before Friday's group meeting so we can review it together.",
                 ts=_ago(35), labels=["INBOX", "UNREAD", "IMPORTANT", "CATEGORY_PERSONAL"], unread=True,
                 url="https://mail.google.com/"),
            dict(id="demo002", from_name="Journal Editorial Office", from_email="editor@journal.example.org",
                 subject="Decision on your submission: minor revision",
                 snippet="The reviewers have completed their assessment. A revised manuscript is due within 21 days of this notice.",
                 ts=_ago(140), labels=["INBOX", "UNREAD", "IMPORTANT", "CATEGORY_UPDATES"], unread=True,
                 url="https://mail.google.com/"),
            dict(id="demo003", from_name="Lab Coordinator", from_email="lab@example.edu",
                 subject="Seminar room changed to Block C",
                 snippet="Today's reading group meeting is moving to Block C, room 204. Same time as usual.",
                 ts=_ago(200), labels=["INBOX", "UNREAD", "CATEGORY_PERSONAL"], unread=True,
                 url="https://mail.google.com/"),
            dict(id="demo004", from_name="Conference Chairs", from_email="chairs@conf.example.org",
                 subject="Registration closes this week",
                 snippet="Early registration for the workshop closes on Thursday. Accepted authors must register to be included in the programme.",
                 ts=_ago(520), labels=["INBOX", "IMPORTANT", "CATEGORY_UPDATES"], unread=False,
                 url="https://mail.google.com/"),
            dict(id="demo005", from_name="Hostel Office", from_email="office@example.edu",
                 subject="Reminder: room inspection on Monday",
                 snippet="This is a reminder that room inspections will take place on Monday morning.",
                 ts=_ago(700), labels=["INBOX", "UNREAD", "CATEGORY_PERSONAL"], unread=True,
                 url="https://mail.google.com/"),
            dict(id="demo006", from_name="Research Weekly", from_email="newsletter@researchweekly.example",
                 subject="This week in NLP: five papers worth reading",
                 snippet="Our weekly digest of new papers and tools for language technology researchers.",
                 ts=_ago(900), labels=["INBOX", "UNREAD", "CATEGORY_UPDATES"], unread=True,
                 url="https://mail.google.com/"),
            dict(id="demo007", from_name="Book Store", from_email="deals@bookstore.example",
                 subject="Weekend sale: 40% off all textbooks",
                 snippet="Limited time offer on selected titles. Shop now.",
                 ts=_ago(1100), labels=["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"], unread=True,
                 url="https://mail.google.com/"),
        ]
    }


def events():
    today = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)

    def at(hour):
        return today.replace(hour=hour).isoformat()

    return {
        "events": [
            dict(id="e1", title="Reading group", start=at(10), end=at(11), all_day=False,
                 location="Block C, room 204", url="", join_url=""),
            dict(id="e2", title="Supervisor meeting", start=at(15), end=at(16), all_day=False,
                 location="", url="", join_url="https://meet.google.com/"),
            dict(id="e3", title="Draft due for review", start=today.date().isoformat(),
                 end=(today + timedelta(days=1)).date().isoformat(), all_day=True,
                 location="", url="", join_url=""),
        ]
    }


def weather():
    return dict(label="Sample city", temp=31, feels=34, wind=9, description="Mostly clear", high=35, low=25, rain_chance=10)


def news():
    def item(title, source, category, mins, rank):
        return dict(title=title, url="https://example.com/", source=source, category=category,
                    ts=_ago(mins), summary="Sample summary text. This is demo data, not a real story.",
                    score=0.9 - rank * 0.05)

    pool = [
        item("Sample headline: city council approves metro line extension", "Sample Daily", "India", 40, 0),
        item("Sample headline: city council clears metro line extension", "Sample Post", "India", 60, 1),
        item("Sample headline: heavy rain expected across the northern plains", "Sample Post", "India", 90, 1),
        item("Sample headline: exam results announced ahead of schedule", "Sample Times", "India", 150, 2),
        item("Sample headline: talks resume between trade delegations", "World Sample", "World", 55, 0),
        item("Sample headline: trade delegations resume talks", "Global Sample", "World", 80, 1),
        item("Sample headline: flood relief operations expand in coastal region", "Global Sample", "World", 120, 1),
        item("Sample headline: central bank holds rates steady", "World Sample", "World", 200, 3),
        item("Sample headline: researchers report faster way to train small language models", "Tech Sample", "Tech", 75, 0),
        item("Sample headline: open dataset released for low-resource speech recognition", "Tech Sample", "Tech", 260, 1),
        item("Sample headline: chipmaker unveils new accelerator for on-device AI", "Gadget Sample", "Tech", 310, 2),
        item("Sample headline: national science fellowship applications open", "Sample Daily", "India", 400, 4),
        item("Sample headline: airline schedules disrupted by storm system", "Global Sample", "World", 500, 4),
        item("Sample headline: browser update tightens tracking protection", "Gadget Sample", "Tech", 600, 5),
    ]
    categories = sorted({i["category"] for i in pool})
    items = {"All": news_module.select_top(pool, 10, 3)}
    for cat in categories:
        items[cat] = news_module.select_top([i for i in pool if i["category"] == cat], 10, 3)
    return {"categories": ["All"] + categories, "items": items, "warnings": [],
            "fetched_at": datetime.now().isoformat(timespec="seconds")}


def papers():
    def paper(i, title, topic, days):
        published = (datetime.now() - timedelta(days=days)).date().isoformat()
        return dict(id=f"demo-paper-{i}", title=title, authors=["A. Author", "B. Author", "C. Author", "D. Author"],
                    abstract="Sample abstract. This is demo data showing how an abstract expands when you press the Abstract button.",
                    published=published, ts=time.time() - days * 86400, url="https://arxiv.org/",
                    pdf="https://arxiv.org/", topics=[topic])

    return {
        "papers": [
            paper(1, "Sample paper: robust language identification for short, noisy text", "Language identification", 1),
            paper(2, "Sample paper: adapter-based translation for extremely low-resource pairs", "Low-resource MT", 2),
            paper(3, "Sample paper: benchmarking language identification across 200 languages", "Language identification", 4),
        ],
        "warnings": [],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
