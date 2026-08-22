#!/usr/bin/env python3
# FanAttic League Recap Bot — v0 (Sleeper edition)
#
# Usage:
#   python3 recap_bot.py --league <LEAGUE_ID> [--week N]   live recap
#   python3 recap_bot.py --mock                             test harness
#
# Sleeper's API is public and keyless. HONESTY LABEL: the live path is
# untested from this sandbox (network allowlist); logic is mock-verified
# below. Same lineage as fetcher_espn.py, which passed its first live fire.
# Failure modes: bad league id -> HTTP 404; preseason weeks have empty
# matchups; players_points can be missing (bench calc then reads 0).

import json, sys, urllib.request

API = "https://api.sleeper.app/v1"

def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=15) as r:
        return json.load(r)

def team_names(users, rosters):
    uname = {u["user_id"]: ((u.get("metadata") or {}).get("team_name")
             or u.get("display_name") or "Team") for u in users}
    return {r["roster_id"]: uname.get(r.get("owner_id"), f"Roster {r['roster_id']}")
            for r in rosters}

def bench_points(m):
    starters = set(m.get("starters") or [])
    pp = m.get("players_points") or {}
    return round(sum(v for k, v in pp.items() if k not in starters), 2)

def build_recap(league_name, week, names, matchups, rosters):
    pairs = {}
    for m in matchups:
        pairs.setdefault(m.get("matchup_id"), []).append(m)
    games = []
    for pair in pairs.values():
        if len(pair) != 2:
            continue
        a, b = pair
        if b["points"] > a["points"]:
            a, b = b, a
        games.append({"w_name": names[a["roster_id"]], "l_name": names[b["roster_id"]],
                      "w": a["points"], "l": b["points"],
                      "margin": round(a["points"] - b["points"], 2)})
    closest = min(games, key=lambda g: g["margin"])
    blowout = max(games, key=lambda g: g["margin"])
    top     = max(matchups, key=lambda m: m["points"])
    tragic  = max(matchups, key=bench_points)

    L = [f"🏈 {league_name} — Week {week} Wire", "=" * 46]
    for g in games:
        L.append(f"{g['w_name']} {g['w']:.2f} def. {g['l_name']} {g['l']:.2f} (by {g['margin']:.2f})")
    L += ["",
      f"⚔️ Game of the Week: {closest['w_name']} escaped {closest['l_name']} "
      f"by {closest['margin']:.2f}. Margins like that end friendships, not seasons.",
      f"💥 The Blowout: {blowout['w_name']} dropped {blowout['l_name']} "
      f"by {blowout['margin']:.2f}. No notes. Several notes for {blowout['l_name']}.",
      f"🔥 Heavyweight: {names[top['roster_id']]} posted {top['points']:.2f}, the week's high.",
      f"🪑 Bench Tragedy: {names[tragic['roster_id']]} left {bench_points(tragic):.2f} "
      f"points in street clothes. Every benching is remembered.",
      "", "📊 Standings:"]
    st = sorted(rosters, key=lambda r: (-(r["settings"].get("wins", 0)),
                                        -(r["settings"].get("fpts", 0))))
    for i, r in enumerate(st, 1):
        s = r["settings"]
        L.append(f" {i}. {names[r['roster_id']]}  "
                 f"{s.get('wins',0)}-{s.get('losses',0)}  ({s.get('fpts',0)} pts)")
    L += ["", "— The FanAttic desk. Every number above is a stored number."]
    return "\n".join(L)

def run_live(league_id, week):
    league  = get(f"/league/{league_id}")
    users   = get(f"/league/{league_id}/users")
    rosters = get(f"/league/{league_id}/rosters")
    if not week:
        week = get("/state/nfl").get("week") or 1
    matchups = get(f"/league/{league_id}/matchups/{week}")
    print(build_recap(league.get("name", "League"), week,
                      team_names(users, rosters), matchups, rosters))

def run_mock():
    names = {1: "Grackle Squad", 2: "Casket Match", 3: "Seemsless FC", 4: "Bench Mob"}
    matchups = [
      {"matchup_id": 1, "roster_id": 1, "points": 121.44, "starters": ["a","b"],
       "players_points": {"a": 60.0, "b": 61.44, "c": 8.5}},
      {"matchup_id": 1, "roster_id": 2, "points": 118.90, "starters": ["d","e"],
       "players_points": {"d": 50.0, "e": 68.9, "f": 31.2}},
      {"matchup_id": 2, "roster_id": 3, "points": 145.20, "starters": ["g","h"],
       "players_points": {"g": 80.2, "h": 65.0, "i": 12.0}},
      {"matchup_id": 2, "roster_id": 4, "points": 98.00, "starters": ["j","k"],
       "players_points": {"j": 40.0, "k": 58.0, "l": 30.7, "m": 14.0}},
    ]
    rosters = [
      {"roster_id": 1, "settings": {"wins": 5, "losses": 2, "fpts": 812}},
      {"roster_id": 2, "settings": {"wins": 4, "losses": 3, "fpts": 799}},
      {"roster_id": 3, "settings": {"wins": 6, "losses": 1, "fpts": 901}},
      {"roster_id": 4, "settings": {"wins": 1, "losses": 6, "fpts": 640}},
    ]
    out = build_recap("Mock League of Record", 7, names, matchups, rosters)
    assert "escaped Casket Match by 2.54" in out
    assert "dropped Bench Mob by 47.20" in out
    assert "Seemsless FC posted 145.20" in out
    assert "Bench Mob left 44.70" in out
    print(out)
    print("\n✅ MOCK ASSERTIONS PASSED — logic verified.")

if __name__ == "__main__":
    a = sys.argv[1:]
    if "--mock" in a:
        run_mock()
    elif "--league" in a:
        lid = a[a.index("--league") + 1]
        wk  = int(a[a.index("--week") + 1]) if "--week" in a else None
        run_live(lid, wk)
    else:
        print(__doc__ or "See header for usage.")
