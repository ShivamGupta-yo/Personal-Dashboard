"""Morning brief: a dashboard that runs only on this computer (127.0.0.1).

Start it:      python app.py
Preview UI:    python app.py --demo        (sample data, nothing is fetched)
"""
import json
import os
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
from google_data import fetch_messages, todays_events, add_task_to_calendar, delete_calendar_event


from flask import Flask, abort, jsonify, request, send_from_directory

import ranking
import store
from google_auth import SetupNeeded

BASE = Path(__file__).parent
DEMO = os.environ.get("DEMO") == "1" or "--demo" in sys.argv


def load_config():
    try:
        return json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit("config.json was not found next to app.py.")
    except json.JSONDecodeError as exc:
        sys.exit(f"config.json has a syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}")


CFG = load_config()
app = Flask(__name__, static_folder="static", static_url_path="")


# ---------------------------------------------------------------- safety

@app.before_request
def only_local():
    """Refuse requests whose Host header is not this machine (blocks DNS-rebinding tricks)."""
    if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
        abort(403, "This app only answers on localhost.")


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def http_error(exc):
    return jsonify(error=exc.description), exc.code


@app.errorhandler(405)
def method_not_allowed(exc):
    # static_url_path="" makes Flask's static route match EVERY url, so a request to a route that does
    # not exist is answered with 405 (not 404). Say what is really going on.
    return jsonify(
        error=f"The running server has no route that accepts {request.method} {request.path}. "
              "If you just added it, restart the server (app.run must be the last thing in app.py)."
    ), 405


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Expected a JSON object.")
    return data


def short(exc):
    text = str(exc).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:200]


# ---------------------------------------------------------------- caching

_cache = {}


def cached(key):
    """Runs fn at most once per cache window. If a refresh fails, serves the last good result."""
    minutes = CFG["cache_minutes"][key]

    def run(fn):
        refresh = request.args.get("refresh") == "1"
        now = time.time()
        hit = _cache.get(key)
        if hit and not refresh and now - hit["t"] < minutes * 60:
            return hit["v"], False
        try:
            value = fn()
        except SetupNeeded:
            raise
        except Exception:
            if hit:
                return hit["v"], True
            raise
        _cache[key] = {"t": now, "v": value}
        return value, False

    return run


def respond(name, key, live, demo_fn, post=None):
    try:
        if DEMO:
            data, stale = demo_fn(), False
        else:
            data, stale = cached(key)(live)
        payload = post(data) if post else dict(data)
    except SetupNeeded as exc:
        return jsonify(status="setup_needed", message=str(exc))
    except Exception as exc:
        return jsonify(error=f"{name} could not be loaded. {short(exc)}")
    payload["stale"] = stale
    return jsonify(payload)


# ---------------------------------------------------------------- pages and config

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def api_config():
    return jsonify(
        user_name=CFG["user_name"],
        greetings=CFG["greetings"],
        timer=CFG["timer"],
        demo=DEMO,
        weather_enabled=CFG["weather"].get("enabled", True),
    )


# ---------------------------------------------------------------- mail

def mail_payload(data):
    cfg = CFG["gmail"]
    states = store.mail_states()
    items, done = [], 0
    for msg in data["messages"]:
        state = states.get(msg["id"])
        if state == "done":
            done += 1
            continue
        score, reasons = ranking.score_message(msg, cfg)
        items.append(
            {
                **msg,
                "score": score,
                "reasons": reasons,
                "important": score >= cfg["min_score"],
                "level": ranking.level(score, cfg["min_score"]),
                "state": state,
            }
        )
    items.sort(key=lambda m: (m["state"] != "pinned", -m["score"], -m["ts"]))
    return {"items": items, "done_count": done}


@app.get("/api/mail")
def api_mail():
    if not CFG["gmail"].get("enabled", True):
        return jsonify(status="disabled")

    def live():
        from google_data import fetch_messages
        return {"messages": fetch_messages(CFG["gmail"])}

    import demo
    return respond("Gmail", "mail", live, demo.mail, mail_payload)


@app.post("/api/mail/<mail_id>/state")
def api_mail_state(mail_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", mail_id):
        abort(400, "Invalid message id.")
    state = body().get("state")
    if state not in ("done", "pinned", None):
        abort(400, "State must be done, pinned or null.")
        
    # Trigger Gmail API sync if the user marked it as "done"
    if state == "done":
        from google_data import mark_message_as_read
        mark_message_as_read(mail_id)
        
    store.set_mail_state(mail_id, state)
    return jsonify(ok=True)


@app.post("/api/mail/reset-done")
def api_mail_reset_done():
    store.reset_done_mail()
    return jsonify(ok=True)


# ---------------------------------------------------------------- calendar, news, papers, weather

@app.get("/api/calendar")
def api_calendar():
    if not CFG["calendar"].get("enabled", True):
        return jsonify(status="disabled")

    def live():
        from google_data import todays_events
        return {"events": todays_events()}

    import demo
    return respond("Calendar", "calendar", live, demo.events)


@app.post("/api/calendar/remove")
def api_calendar_remove():
    """Deletes one Google Calendar event. JSON body: {"event_id": "..."}"""
    if not CFG["calendar"].get("enabled", True):
        abort(400, "Calendar is turned off in config.json.")
    event_id = str(body().get("event_id", "")).strip()
    if not event_id:  # checked before the try block so abort() keeps its 400 instead of becoming a 500
        abort(400, "Missing event ID.")
    try:
        delete_calendar_event(event_id)
    except Exception as exc:
        return jsonify(error=f"Could not delete the event. {short(exc)}"), 500
    return jsonify(ok=True)


@app.get("/api/news")
def api_news():
    import news
    import demo
    return respond("News", "news", lambda: news.build(CFG["news"]), demo.news)


@app.get("/api/papers")
def api_papers():
    if not CFG["papers"].get("enabled", True):
        return jsonify(status="disabled")
    import papers
    import demo
    return respond("Papers", "papers", lambda: papers.build(CFG["papers"]), demo.papers)


@app.get("/api/weather")
def api_weather():
    if not CFG["weather"].get("enabled", True):
        return jsonify(status="disabled")
    import weather
    import demo
    return respond("Weather", "weather", lambda: weather.build(CFG["weather"]), demo.weather)


# ---------------------------------------------------------------- tasks

@app.get("/api/tasks")
def api_tasks():
    return jsonify(tasks=store.list_tasks())


@app.post("/api/tasks")
def api_tasks_add():
    data = body()
    title = str(data.get("title", "")).strip()[:200]
    if not title:
        abort(400, "Write a task title first.")
    due = str(data["due"]) if data.get("due") else None
    if due and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        abort(400, "Due date must look like 2026-09-25.")
    return jsonify(task=store.add_task(title, due)), 201


@app.post("/api/tasks/clear-done")
def api_tasks_clear_done():
    store.clear_done_tasks()
    return jsonify(ok=True)


@app.patch("/api/tasks/<int:task_id>")
def api_tasks_patch(task_id):
    if not store.set_task_done(task_id, bool(body().get("done"))):
        abort(404, "Task not found.")
    return jsonify(ok=True)


@app.delete("/api/tasks/<int:task_id>")
def api_tasks_delete(task_id):
    # Retrieve task to check for a linked Google Calendar event_id
    task = next((t for t in store.list_tasks() if t["id"] == task_id), None)
    
    if task and task.get("event_id"):
        try:
            delete_calendar_event(task["event_id"])
        except Exception:
            pass # Fails silently if it was already deleted on Google Calendar manually

    if not store.delete_task(task_id):
        abort(404, "Task not found.")
    return jsonify(ok=True)


@app.post("/api/tasks/<task_id>/calendar")
def task_to_calendar(task_id):
    req_data = body()
    start_time = req_data.get("start_time")
    end_time = req_data.get("end_time")
    recurrence = req_data.get("recurrence")

    tasks = store.list_tasks()
    task = next((t for t in tasks if str(t['id']) == str(task_id)), None)
    
    if not task:
        abort(404, "Task not found.")
        
    due_date = task.get("due")
    if not due_date:
        abort(400, "Task must have a due date to add to calendar.")
        
    try:
        event_id = add_task_to_calendar(task["title"], due_date, start_time, end_time, recurrence)
        store.set_task_event_id(task["id"], event_id)
        return jsonify(status="success")
    except Exception as e:
        return jsonify(error=str(e)), 500


# ---------------------------------------------------------------- read later

@app.get("/api/bookmarks")
def api_bookmarks():
    return jsonify(bookmarks=store.list_bookmarks())


@app.post("/api/bookmarks")
def api_bookmarks_add():
    data = body()
    url = str(data.get("url", ""))
    if urlparse(url).scheme not in ("http", "https"):
        abort(400, "Only http and https links can be saved.")
    kind = data.get("kind")
    if kind not in ("news", "paper"):
        abort(400, "Kind must be news or paper.")
    title = str(data.get("title", "")).strip()[:300] or url
    store.add_bookmark(kind, title, url, str(data.get("source", ""))[:80])
    return jsonify(ok=True), 201


@app.delete("/api/bookmarks/<int:bookmark_id>")
def api_bookmarks_delete(bookmark_id):
    if not store.delete_bookmark(bookmark_id):
        abort(404, "Bookmark not found.")
    return jsonify(ok=True)


# ---------------------------------------------------------------- spotify

@app.get("/api/spotify")
def api_spotify():
    if not CFG.get("spotify", {}).get("enabled", False):
        return jsonify(status="disabled")
    import spotify_data
    return jsonify(spotify_data.get_now_playing(CFG["spotify"]))

@app.post("/api/spotify/toggle")
def api_spotify_toggle():
    action = body().get("action")
    import spotify_data
    return jsonify(spotify_data.toggle_playback(CFG["spotify"], action))


# ---------------------------------------------------------------- focus timer

@app.get("/api/focus")
def api_focus():
    return jsonify(store.focus_today())


@app.post("/api/focus")
def api_focus_log():
    data = body()
    try:
        minutes = int(data.get("minutes", 0))
    except (TypeError, ValueError):
        minutes = 0
    if not 1 <= minutes <= 180:
        abort(400, "Minutes must be between 1 and 180.")
    store.log_focus(minutes, str(data.get("label", "")).strip()[:80])
    return jsonify(store.focus_today()), 201


# ---------------------------------------------------------------- start

store.init()

if __name__ == "__main__":
    port = int(CFG.get("port", 5057))
    url = f"http://127.0.0.1:{port}"
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Morning brief running at {url}" + ("  (demo mode: sample data)" if DEMO else ""))
    print("Press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)