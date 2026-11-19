# Waitlist Watcher

A small agent that checks affordable housing web pages every morning, notices when one changes, asks a local AI model whether the change is real news, and alerts me if a waiting list opened, closed, or changed dates.

I work as a housing case manager. People miss waiting list openings all the time because each housing authority posts news on its own page and nobody can check them all every day. This does the checking.

## What it does

- Reads a list of pages from `sites.txt`
- Downloads each page and keeps only the readable text
- Compares today's text with the copy saved from the last run
- Sends any change to a local model, which answers **IMPORTANT** or **noise** with a one-sentence summary
- Pops up a Mac notification for real news and writes it to `alerts.log`
- Runs by itself every morning at 8:00

Everything runs on a laptop. No cloud service or API key is needed.

## How it works

1. **Fetch.** Download the page.
2. **Clean.** Remove menus, scripts, and footers.
3. **Compare.** Line-by-line check against the saved snapshot.
4. **Judge.** If something changed, the model decides whether it matters.
5. **Alert.** Notification and log entry for important changes.
6. **Save.** Today's text becomes the snapshot for next time.

Step 4 is why a model belongs here. Pages change for boring reasons, such as a "last updated" date. A plain change alarm would go off constantly. The model filters that out.

## Tech

| Part | Tool |
|---|---|
| Fetching pages | `requests` |
| Cleaning HTML | `beautifulsoup4` |
| Finding changes | Python's built-in `difflib` |
| Local model | [Ollama](https://ollama.com) with `qwen3:4b` |
| Notifications | macOS `osascript` |
| Schedule | macOS `launchd` |

## Setup

Install [Ollama](https://ollama.com) and open it, then:

```
ollama pull qwen3:4b

git clone https://github.com/DavidRamirez231/waitlist-watcher.git
cd waitlist-watcher
python3 -m venv .venv
source .venv/bin/activate
pip install requests beautifulsoup4 ollama
```

## Use

| Command | What it does |
|---|---|
| `python watcher.py` | Check every site in `sites.txt` |
| `python watcher.py demo` | Practice run with a made-up change. Visits no websites. |
| `python watcher.py test-alert` | Send one test notification |
| `bash schedule.sh` | Run automatically every day at 8:00 AM |
| `bash schedule.sh off` | Turn the schedule off |

To watch a different page, add a line to `sites.txt`:

```
Name of the page | https://example.gov/waiting-list
```

## How I tested the model

I edited a saved snapshot by hand to fake two kinds of change, then ran the watcher.

| Fake change | Expected | Result |
|---|---|---|
| Waiting list status flipped between "open" and "closed" | IMPORTANT | IMPORTANT, with a correct one-sentence summary |
| A "Website last updated" line added | noise | noise |

If the model is unavailable or gives an unclear answer, the watcher treats the change as important. A false alarm costs a minute. A missed opening can cost someone a place on a list.

## What I learned

**Not every page can be read by a simple script.** Of the first five official pages I tried, two worked. One needs a real browser because it builds itself with scripts. Two sit behind a "prove you are human" check.

**Respect the sites.** When a site turns automated visitors away, this project leaves it alone. Those pages are listed in `sites.txt` as parked, with the reason. The watcher identifies itself honestly, visits each page once a day, and pauses between sites.

**Guard against bad data.** During testing, one site briefly returned an almost empty page. The watcher is built to notice that and skip it, so a bad response is never mistaken for a change and never overwrites a good snapshot.

**Build in small stages.** This was built in five steps, each tested before the next: fetch one page, detect a change, handle a list, add the model, add alerts and a schedule.

## Limits

- Runs only when the laptop is awake
- Works only on pages that load without a browser
- Notifications and scheduling are macOS-only
- A small local model can misjudge a change, so the raw added and removed lines are always printed too

## Next steps

- Read script-built pages with a real browser engine
- Email or text alerts
- Run in the cloud so the laptop does not need to be on
- Track individual buildings, not just housing authorities

## About

Built by David Ramirez, a housing case manager learning to build AI tools for affordable housing and nonprofit work. I used an AI assistant as a pair programmer while building this.
