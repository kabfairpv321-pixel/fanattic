#!/usr/bin/env python3
"""fetcher_espn.py v2 — universal multi-league score poller, now with hands.

v1 printed; v2 writes. Feed it these environment variables and it
mirrors live fixtures into your Supabase, which the World Cup Wire
page then displays:

  SUPABASE_URL          e.g. https://abcd1234.supabase.co
  SUPABASE_SERVICE_KEY  service_role key — SERVER-SIDE ONLY (GitHub
                        Actions secret; never in any page)
  NTFY_TOPIC            optional — goal pushes to ntfy.sh/<topic>

Modes:
  python3 fetcher_espn.py         single pass (right for cron / Actions)
  python3 fetcher_espn.py loop    poll every 60s locally during a match

Change detection uses the DATABASE as memory, so single-pass cron runs
remember what they saw last time. Without env vars it degrades to the
old read-only demo and just prints.

HONESTY LABEL: ESPN's endpoints are unofficial and unreachable from
the build sandbox, so the first live run is the live test. And after
the World Cup final, disable the Actions workflow (repo -> Actions ->
fetch-scores -> "..." -> Disable) or it will politely burn your free
minutes polling an empty calendar until autumn.

Stdlib only.
"""

import json
import os
import sys
import time
import urllib.request

# league_id (matches schema_sports.sql) -> ESPN path
LEAGUES = {
    "world_cup":        "soccer/fifa.world",
    "epl":              "soccer/eng.1",
    "la_liga":          "soccer/esp.1",
    "champions_league": "soccer/uefa.champions",
    "mls":              "soccer/usa.1",
    "nfl":              "football/nfl",
}
ACTIVE = ["world_cup", "mls"]   # mirror tracked_leagues.is_active_now

BASE = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY", "")
NTFY_TOPIC   = os.environ.get("NTFY_TOPIC", "")
DB_ON = bool(SUPABASE_URL and SERVICE_KEY)

_mem = {}   # fallback memory when running without a database


def _req(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def fetch_scoreboard(path):
    return json.loads(_req(BASE.format(path=path),
                           headers={"User-Agent": "fanattic/1.0"}))


def parse_events(league_id, data):
    """Normalize ESPN's shape into rows matching sports_fixtures_log."""
    rows = []
    for ev in data.get("events", []):
        comp = ev["competitions"][0]
        sides = {c["homeAway"]: c for c in comp["competitors"]}
        home, away = sides["home"], sides["away"]
        st = comp.get("status", ev.get("status", {}))
        state = st.get("type", {}).get("state", "pre")   # pre / in / post
        status = {"pre": "UPCOMING", "in": "LIVE", "post": "FT"}.get(state, "LIVE")
        score = f"{home.get('score', '0')} - {away.get('score', '0')}"
        rows.append({
            "league_id":       league_id,
            "match_id":        f"{league_id}_{ev['id']}",
            "home_team":       home["team"]["displayName"],
            "away_team":       away["team"]["displayName"],
            "score_snapshot":  score,
            "game_status":     status,
            "game_clock":      st.get("displayClock", ""),
            "last_event_text": f"{home['team']['displayName']} {score} "
                               f"{away['team']['displayName']} ({status})",
        })
    return rows


# ---------------- database hands ----------------
def _db_headers():
    return {"apikey": SERVICE_KEY,
            "Authorization": "Bearer " + SERVICE_KEY,
            "Content-Type": "application/json"}


def db_get_state(match_id):
    url = (f"{SUPABASE_URL}/rest/v1/sports_fixtures_log"
           f"?match_id=eq.{match_id}&select=score_snapshot,game_status")
    rows = json.loads(_req(url, headers=_db_headers()))
    if rows:
        return rows[0]["score_snapshot"] + "|" + rows[0]["game_status"]
    return None


def db_upsert(row):
    url = f"{SUPABASE_URL}/rest/v1/sports_fixtures_log?on_conflict=match_id"
    h = _db_headers()
    h["Prefer"] = "resolution=merge-duplicates"
    _req(url, data=json.dumps(row).encode(), headers=h, method="POST")


def notify(row):
    text = row["last_event_text"]
    print("-> ALERT:", text)
    if NTFY_TOPIC:
        try:
            _req(f"https://ntfy.sh/{NTFY_TOPIC}", data=text.encode())
        except Exception as e:
            print("   ntfy failed:", e)


# ---------------- the loop ----------------
def poll_once():
    print("mode:", "database" if DB_ON else "read-only demo (no env vars)")
    for league_id in ACTIVE:
        try:
            data = fetch_scoreboard(LEAGUES[league_id])
        except Exception as e:
            print(f"[{league_id}] fetch failed: {e}")
            continue
        for row in parse_events(league_id, data):
            state = row["score_snapshot"] + "|" + row["game_status"]
            if DB_ON:
                try:
                    prev = db_get_state(row["match_id"])
                    db_upsert(row)
                except Exception as e:
                    print("   db error:", e)
                    continue
            else:
                prev = _mem.get(row["match_id"])
                _mem[row["match_id"]] = state
            if prev is not None and prev != state:
                notify(row)
            else:
                print(f"   seen: {row['last_event_text']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        print("Polling every 60s. Ctrl-C to stop.")
        while True:
            poll_once()
            time.sleep(60)
    else:
        poll_once()
  
