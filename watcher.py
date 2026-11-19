"""
Waitlist watcher, stage 4: alerts and a daily schedule.

When the model finds real news, the watcher pops up a Mac notification
and writes a line to alerts.log. To test that:  python watcher.py test-alert
To run it every morning, see schedule.sh.

Setup (one time):
    pip install requests beautifulsoup4 ollama
    ollama pull qwen3:4b        (skip if you already have it)

Run:
    python watcher.py

The pages to watch live in sites.txt, one per line, like this:
    LACDA How to Apply | https://lacda.org/section-8/shared-info/how-to-apply

The first run saves a copy of each page. Every run after that compares
each page to its saved copy. When a page changed, the model reads what
was removed and added, and says whether it is real news or just noise.
"""

import difflib
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import ollama
import requests
from bs4 import BeautifulSoup

SITES_FILE = Path("sites.txt")
SNAPSHOT_DIR = Path("snapshots")
ALERT_LOG = Path("alerts.log")   # every piece of news is also written here
CHAT_MODEL = "qwen3:4b"
PAUSE_SECONDS = 2      # wait between sites so we are gentle on them
TOO_SHORT = 300        # fewer characters than this usually means the page did not load properly
MAX_FOR_MODEL = 3000   # most characters of changed text to show the model

# Tell the site who is visiting. Polite scripts identify themselves.
HEADERS = {"User-Agent": "waitlist-watcher (personal project, checks once a day)"}


def load_sites():
    """Read sites.txt and return a list of (name, url) pairs."""
    if not SITES_FILE.exists():
        raise SystemExit("sites.txt is missing. Put it in the same folder as watcher.py.")
    sites = []
    for line in SITES_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, url = [part.strip() for part in line.split("|", 1)]
        else:
            name, url = line, line
        sites.append((name, url))
    return sites


def get_text(url):
    """Download a page and return only the words a person would read."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def snapshot_path(url):
    """Turn a web address into a safe file name, like lacda.org_section-8_....txt"""
    name = re.sub(r"^https?://", "", url)
    name = re.sub(r"[^A-Za-z0-9.-]+", "_", name).strip("_")
    return SNAPSHOT_DIR / f"{name}.txt"


def find_changes(old_text, new_text):
    """Return the lines that were added and the lines that were removed."""
    added, removed = [], []
    for line in difflib.ndiff(old_text.splitlines(), new_text.splitlines()):
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
    return added, removed


def check(url):
    """Compare the page to the saved copy. Returns (status, added, removed)."""
    new_text = get_text(url)
    if len(new_text) < TOO_SHORT:
        return "empty", [], []

    path = snapshot_path(url)
    SNAPSHOT_DIR.mkdir(exist_ok=True)

    if not path.exists():
        path.write_text(new_text)
        return "first", [], []

    old_text = path.read_text()
    if old_text == new_text:
        return "same", [], []

    added, removed = find_changes(old_text, new_text)
    path.write_text(new_text)  # today's page becomes the copy for next time
    return "changed", added, removed


def remove_thinking(text):
    """Some models write private reasoning first. Keep only the answer."""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.replace("<think>", "").strip()


def judge(name, added, removed):
    """Ask the model if a change matters. Returns (important, summary)."""
    old = "\n".join(removed)[:MAX_FOR_MODEL] or "(nothing)"
    new = "\n".join(added)[:MAX_FOR_MODEL] or "(nothing)"
    prompt = (
        "You help a housing case manager watch housing authority web pages "
        "for waiting list news. A page changed. Decide if the change matters.\n\n"
        "IMPORTANT means: a waiting list or lottery opened, closed, or was scheduled; "
        "application dates or deadlines changed; who can apply or how to apply changed.\n"
        "NOISE means: typos, formatting, menus, footers, 'last updated' dates, "
        "or anything not about applying for housing.\n\n"
        "Reply with exactly two lines and nothing else:\n"
        "VERDICT: IMPORTANT or NOISE\n"
        "SUMMARY: one plain sentence saying what changed, from the old text to the new text.\n\n"
        f"PAGE: {name}\n\n"
        f"OLD TEXT (removed from the page):\n{old}\n\n"
        f"NEW TEXT (added to the page):\n{new}"
    )
    if "qwen" in CHAT_MODEL.lower():
        prompt += "\n\n/no_think"  # asks Qwen to skip its long thinking step

    messages = [{"role": "user", "content": prompt}]
    try:
        try:
            reply = ollama.chat(model=CHAT_MODEL, messages=messages, think=False)
        except (ollama.ResponseError, TypeError):
            reply = ollama.chat(model=CHAT_MODEL, messages=messages)
        text = remove_thinking(reply["message"]["content"] or "")
    except Exception as problem:
        # If the model is not available, do not hide the change. Flag it.
        return True, f"The model could not judge this ({problem}). Check the page yourself."

    verdict = re.search(r"VERDICT:\s*(\w+)", text, re.IGNORECASE)
    summary = re.search(r"SUMMARY:\s*(.+)", text, re.IGNORECASE)
    if not verdict:
        return True, "The model gave an unclear answer. Check the page yourself."
    important = verdict.group(1).upper() != "NOISE"
    return important, (summary.group(1).strip() if summary else "No summary given.")


def notify(title, message):
    """Pop up a Mac notification. Does nothing on other computers."""
    if sys.platform != "darwin":
        return
    script = [
        "osascript",
        "-e", "on run argv",
        "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
        "-e", "end run",
        title, message,
    ]
    try:
        subprocess.run(script, check=False, timeout=10)
    except Exception:
        pass  # a failed pop-up should never stop the watcher


def record(name, url, summary):
    """Add one line of news to alerts.log so nothing is lost."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with ALERT_LOG.open("a") as log:
        log.write(f"{stamp} | {name} | {summary} | {url}\n")


def shorten(line, limit=200):
    return line if len(line) <= limit else line[:limit] + "..."


def run():
    sites = load_sites()
    counts = {"first": 0, "same": 0, "changed": 0, "empty": 0, "error": 0}
    news = []

    for number, (name, url) in enumerate(sites):
        if number:
            time.sleep(PAUSE_SECONDS)
        print(f"\n{name}\n  {url}")
        try:
            status, added, removed = check(url)
        except requests.RequestException as problem:
            counts["error"] += 1
            print(f"  COULD NOT LOAD: {problem}")
            continue

        counts[status] += 1
        if status == "first":
            print("  First visit. Saved a copy.")
        elif status == "same":
            print("  No change.")
        elif status == "empty":
            print("  Almost no text came back. This page probably needs a real browser to load.")
        else:
            print("  Changed. Asking the model if it matters...")
            important, summary = judge(name, added, removed)
            label = "IMPORTANT" if important else "noise"
            print(f"  {label}: {summary}")
            if important:
                news.append((name, url, summary))
            for line in removed:
                print(f"    removed: {shorten(line)}")
            for line in added:
                print(f"    added:   {shorten(line)}")

    print(
        f"\nDone. {len(sites)} sites: {counts['changed']} changed, {counts['same']} same, "
        f"{counts['first']} new, {counts['empty']} empty, {counts['error']} could not load."
    )
    if news:
        print("\nNEWS TODAY")
        for name, url, summary in news:
            print(f"  {name}: {summary}\n    {url}")
            record(name, url, summary)
            notify(f"Housing news: {name}", summary)

    # Always say when a run is finished, even if nothing changed.
    problems = counts["empty"] + counts["error"]
    finished = f"{len(sites)} sites checked. {len(news)} with news."
    if problems:
        finished += f" {problems} did not load."
    notify("Waitlist watcher finished", finished)
    return news


if __name__ == "__main__":
    # Run from the folder this file lives in, so the schedule finds sites.txt.
    import os
    os.chdir(Path(__file__).resolve().parent)

    if len(sys.argv) > 1 and sys.argv[1] == "test-alert":
        record("Test", "https://example.com", "This is a test alert.")
        notify("Housing news: Test", "This is a test alert.")
        print("Sent a test notification and wrote a line to alerts.log.")
    elif len(sys.argv) > 1 and sys.argv[1] == "demo":
        # A full practice run that does not visit any website:
        # a made-up change goes to the real model, then to the real alert.
        removed = ["At this time, the waiting list is closed for public registration."]
        added = ["The waiting list will be open for public registration "
                 "from December 1 through December 15."]
        print("Demo: pretending a housing page changed. Asking the model...")
        important, summary = judge("Demo Housing Authority", added, removed)
        print(f"  {'IMPORTANT' if important else 'noise'}: {summary}")
        if important:
            record("Demo Housing Authority", "https://example.com", summary)
            notify("Housing news: Demo Housing Authority", summary)
            print("  Sent a notification and wrote a line to alerts.log.")
    else:
        print(datetime.now().strftime("Run started %Y-%m-%d %H:%M"))
        run()
