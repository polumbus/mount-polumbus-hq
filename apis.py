"""
Sports API integrations for Mount Polumbus HQ.
ESPN (free) + Sleeper (free) + Perplexity (key required).
"""

import requests
import json
import re
import os
import time
from datetime import datetime, timedelta
from typing import Optional

_HEADERS = {"User-Agent": "Mozilla/5.0"}
_TIMEOUT = 12

# ═══════════════════════════════════════════════════════════════════════
# ESPN API — Free, no auth
# ═══════════════════════════════════════════════════════════════════════

_ESPN = "https://site.api.espn.com/apis/site/v2/sports"
_ESPN_SPORTS = {
    "nfl": ("football", "nfl"),
    "nba": ("basketball", "nba"),
    "ncaam": ("basketball", "mens-college-basketball"),
    "nhl": ("hockey", "nhl"),
}


def espn_scores(sport: str, limit: int = 20) -> list:
    """Get today's scores for a sport."""
    s, l = _ESPN_SPORTS.get(sport.lower(), ("football", "nfl"))
    try:
        data = requests.get(f"{_ESPN}/{s}/{l}/scoreboard", params={"limit": limit},
                            headers=_HEADERS, timeout=_TIMEOUT).json()
    except Exception:
        return []
    games = []
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        home = away = {}
        for c in competitors:
            td = {
                "name": c.get("team", {}).get("displayName", ""),
                "abbr": c.get("team", {}).get("abbreviation", ""),
                "score": c.get("score", "0"),
            }
            if c.get("homeAway") == "home":
                home = td
            else:
                away = td
        status = event.get("status", {})
        games.append({
            "name": event.get("name", ""),
            "date": event.get("date", ""),
            "status": status.get("type", {}).get("description", ""),
            "completed": status.get("type", {}).get("completed", False),
            "home": home, "away": away,
            "broadcast": comp.get("broadcasts", [{}])[0].get("names", [""])[0] if comp.get("broadcasts") else "",
        })
    return games


def espn_news(sport: str, limit: int = 10) -> list:
    """Get latest headlines."""
    s, l = _ESPN_SPORTS.get(sport.lower(), ("football", "nfl"))
    try:
        data = requests.get(f"{_ESPN}/{s}/{l}/news", params={"limit": limit},
                            headers=_HEADERS, timeout=_TIMEOUT).json()
    except Exception:
        return []
    return [{"headline": a.get("headline", ""), "description": a.get("description", "")}
            for a in data.get("articles", [])]


def espn_standings(sport: str) -> list:
    """Get current standings (simplified)."""
    s, l = _ESPN_SPORTS.get(sport.lower(), ("football", "nfl"))
    try:
        data = requests.get(f"{_ESPN}/{s}/{l}/standings",
                            headers=_HEADERS, timeout=_TIMEOUT).json()
    except Exception:
        return []
    standings = []
    for group in data.get("children", []):
        div = group.get("name", "")
        entries = group.get("standings", {}).get("entries", [])
        # Some sports nest conferences > divisions
        if not entries and group.get("children"):
            for sub in group["children"]:
                subdiv = sub.get("name", "")
                for entry in sub.get("standings", {}).get("entries", []):
                    team = entry.get("team", {})
                    stats = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}
                    standings.append({
                        "team": team.get("displayName", ""),
                        "abbr": team.get("abbreviation", ""),
                        "division": f"{div} - {subdiv}",
                        "wins": stats.get("wins", "0"),
                        "losses": stats.get("losses", "0"),
                    })
        else:
            for entry in entries:
                team = entry.get("team", {})
                stats = {s["name"]: s["displayValue"] for s in entry.get("stats", [])}
                standings.append({
                    "team": team.get("displayName", ""),
                    "abbr": team.get("abbreviation", ""),
                    "division": div,
                    "wins": stats.get("wins", "0"),
                    "losses": stats.get("losses", "0"),
                })
    return standings


def espn_team(sport: str, team_abbr: str) -> dict:
    """Get team info (record, next game)."""
    s, l = _ESPN_SPORTS.get(sport.lower(), ("football", "nfl"))
    team_abbr = team_abbr.upper()
    try:
        data = requests.get(f"{_ESPN}/{s}/{l}/teams",
                            headers=_HEADERS, timeout=_TIMEOUT).json()
    except Exception:
        return {}
    for group in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
        t = group.get("team", {})
        if t.get("abbreviation", "").upper() == team_abbr:
            return {
                "name": t.get("displayName", ""),
                "record": t.get("record", {}).get("items", [{}])[0].get("summary", "") if t.get("record") else "",
                "next_event": t.get("nextEvent", [{}])[0].get("name", "") if t.get("nextEvent") else "",
            }
    return {}


# ═══════════════════════════════════════════════════════════════════════
# SLEEPER API — Free, no auth
# ═══════════════════════════════════════════════════════════════════════

_SLEEPER = "https://api.sleeper.app/v1"
_sleeper_players_cache = {"data": None, "ts": 0}


def sleeper_nfl_state() -> dict:
    """Current NFL season/week/phase."""
    try:
        data = requests.get(f"{_SLEEPER}/state/nfl", headers=_HEADERS, timeout=_TIMEOUT).json()
        return {"season": data.get("season"), "week": data.get("week"), "phase": data.get("season_type", "off")}
    except Exception:
        return {}


def _sleeper_players() -> dict:
    """Get all NFL players (cached 6h in memory)."""
    if _sleeper_players_cache["data"] and (time.time() - _sleeper_players_cache["ts"]) < 21600:
        return _sleeper_players_cache["data"]
    try:
        data = requests.get(f"{_SLEEPER}/players/nfl", headers=_HEADERS, timeout=30).json()
        _sleeper_players_cache["data"] = data
        _sleeper_players_cache["ts"] = time.time()
        return data
    except Exception:
        return _sleeper_players_cache.get("data") or {}


def sleeper_trending(direction: str = "add", limit: int = 15) -> list:
    """Trending players (most added/dropped in fantasy last 24h)."""
    try:
        data = requests.get(f"{_SLEEPER}/players/nfl/trending/{direction}",
                            params={"limit": limit}, headers=_HEADERS, timeout=_TIMEOUT).json()
    except Exception:
        return []
    players = _sleeper_players()
    results = []
    for item in data:
        pid = str(item.get("player_id", ""))
        p = players.get(pid, {})
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if name:
            results.append({
                "name": name, "team": p.get("team", ""), "position": p.get("position", ""),
                "count": item.get("count", 0),
                "injury": p.get("injury_status", ""),
            })
    return results


def sleeper_player(name: str) -> dict:
    """Look up a player by name."""
    name_lower = name.lower().strip()
    players = _sleeper_players()
    for pid, p in players.items():
        full = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if name_lower == full.lower():
            return {
                "name": full, "team": p.get("team", ""), "position": p.get("position", ""),
                "number": p.get("number", ""), "age": p.get("age", ""),
                "years_exp": p.get("years_exp", 0), "college": p.get("college", ""),
                "status": p.get("status", ""), "injury": p.get("injury_status", ""),
                "injury_notes": p.get("injury_notes", ""),
                "depth_chart_position": p.get("depth_chart_position", ""),
                "depth_chart_order": p.get("depth_chart_order"),
            }
    # Fuzzy match
    for pid, p in players.items():
        full = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if name_lower in full.lower() and p.get("team"):
            return {
                "name": full, "team": p.get("team", ""), "position": p.get("position", ""),
                "number": p.get("number", ""), "age": p.get("age", ""),
                "years_exp": p.get("years_exp", 0), "college": p.get("college", ""),
                "status": p.get("status", ""), "injury": p.get("injury_status", ""),
            }
    return {}


def sleeper_roster(team_abbr: str) -> list:
    """Get a team's active roster."""
    team_abbr = team_abbr.upper()
    players = _sleeper_players()
    roster = []
    for pid, p in players.items():
        if (p.get("team") or "").upper() == team_abbr and p.get("status") == "Active":
            roster.append({
                "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                "position": p.get("position", ""),
                "number": p.get("number", ""),
                "injury": p.get("injury_status", ""),
            })
    return roster


def sleeper_injuries(team_abbr: str) -> list:
    """Get injured players for a team."""
    roster = sleeper_roster(team_abbr)
    return [p for p in roster if p.get("injury")]


# ═══════════════════════════════════════════════════════════════════════
# PERPLEXITY SONAR API — Requires key
# ═══════════════════════════════════════════════════════════════════════

def _pplx_key() -> str:
    """Get Perplexity API key from Streamlit secrets or env."""
    try:
        import streamlit as st
        key = st.secrets.get("PERPLEXITY_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("PERPLEXITY_API_KEY", "")


def _pplx_call(prompt: str, system: str = "", max_tokens: int = 500) -> dict:
    """Call Perplexity Sonar API."""
    key = _pplx_key()
    if not key:
        return {"answer": "", "citations": [], "error": "No Perplexity API key configured"}
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "sonar", "messages": messages, "return_citations": True, "max_tokens": max_tokens},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])
        return {"answer": content, "citations": citations}
    except Exception as e:
        return {"answer": "", "citations": [], "error": str(e)}


def pplx_fact_check(claim: str) -> dict:
    """Fact-check a claim. Returns answer + sources."""
    return _pplx_call(
        f'Fact check this claim for accuracy. If wrong, provide the correct information:\n\n"{claim}"',
        system="You are a fact-checker for a sports media professional. Be precise and concise. Confirm with source if accurate. Correct with specific numbers/dates if wrong.",
    )


def pplx_research(topic: str) -> dict:
    """Research a topic for content creation."""
    return _pplx_call(
        f"Research this topic for a sports media professional creating Twitter content:\n\n{topic}\n\n"
        "Include: key stats, recent developments, notable quotes, controversy/debate angles. Be specific.",
        system="You are a sports researcher. Provide accurate, detailed information with specific stats and dates.",
        max_tokens=800,
    )


def pplx_trending(city: str = "Denver") -> dict:
    """What's trending in sports right now."""
    return _pplx_call(
        f"What are the top 5 sports stories trending in {city} right now? NFL, NBA, college sports. Key details for each.",
        system="List the most talked-about stories ordered by relevance. Include team names, player names, specific details. Be current.",
    )


def pplx_quick(question: str) -> str:
    """Quick factual answer, no sources."""
    result = _pplx_call(question, system="Answer concisely in 1-2 sentences with specific facts.", max_tokens=200)
    return result.get("answer", "")


def pplx_available() -> bool:
    """Check if Perplexity API key is configured."""
    return bool(_pplx_key())


# ═══════════════════════════════════════════════════════════════════════
# THE ODDS API — Betting lines, spreads, totals
# ═══════════════════════════════════════════════════════════════════════

_ODDS_BASE = "https://api.the-odds-api.com/v4"
_ODDS_SPORT_MAP = {
    "nfl": "americanfootball_nfl", "nba": "basketball_nba",
    "ncaam": "basketball_ncaab", "ncaaf": "americanfootball_ncaaf",
    "nhl": "icehockey_nhl", "mlb": "baseball_mlb",
}
_ODDS_TEAM_ALIASES = {
    "broncos": "Denver Broncos", "nuggets": "Denver Nuggets",
    "avalanche": "Colorado Avalanche", "avs": "Colorado Avalanche",
    "rockies": "Colorado Rockies", "buffs": "Colorado Buffaloes",
    "denver": "Denver", "colorado": "Colorado",
}


def _odds_key() -> str:
    """Get Odds API key from Streamlit secrets or env."""
    try:
        import streamlit as st
        key = st.secrets.get("ODDS_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("ODDS_API_KEY", "")


def odds_available() -> bool:
    """Check if Odds API key is configured."""
    return bool(_odds_key())


def odds_game(sport: str, team: str) -> Optional[dict]:
    """Get betting lines for a team's next/current game. Returns None if no game found."""
    key = _odds_key()
    if not key:
        return None
    sport_key = _ODDS_SPORT_MAP.get(sport.lower(), sport)
    try:
        resp = requests.get(
            f"{_ODDS_BASE}/sports/{sport_key}/odds",
            params={"apiKey": key, "regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "american"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        events = resp.json()
    except Exception:
        return None

    # Find the team's game
    team_lower = _ODDS_TEAM_ALIASES.get(team.lower().strip(), team).lower()
    event = None
    for e in events:
        if team_lower in e.get("home_team", "").lower() or team_lower in e.get("away_team", "").lower():
            event = e
            break
    if not event:
        return None

    home = event["home_team"]
    away = event["away_team"]
    start = event.get("commence_time", "")

    # Extract consensus from first bookmaker
    result = {"home": home, "away": away, "start": start}
    bms = event.get("bookmakers", [])
    if bms:
        bm = bms[0]
        result["source"] = bm.get("title", "")
        for market in bm.get("markets", []):
            mkey = market.get("key", "")
            outcomes = {o.get("name", ""): o for o in market.get("outcomes", [])}
            if mkey == "h2h":
                h_odds = outcomes.get(home, {}).get("price", 0)
                a_odds = outcomes.get(away, {}).get("price", 0)
                result["moneyline_home"] = f"+{h_odds}" if h_odds > 0 else str(h_odds)
                result["moneyline_away"] = f"+{a_odds}" if a_odds > 0 else str(a_odds)
            elif mkey == "spreads":
                h_spread = outcomes.get(home, {})
                result["spread"] = h_spread.get("point", "")
                result["spread_odds"] = h_spread.get("price", "")
            elif mkey == "totals":
                over = outcomes.get("Over", {})
                result["over_under"] = over.get("point", "")
                result["over_odds"] = over.get("price", "")
    return result


def odds_format_block(team: str, sport: str) -> str:
    """Get formatted odds block for prompt injection. Returns empty string if unavailable."""
    data = odds_game(sport, team)
    if not data:
        return ""
    parts = [f"BETTING LINES ({data.get('source', 'consensus')}):"]
    parts.append(f"  {data['away']} @ {data['home']}")
    if data.get("spread"):
        parts.append(f"  Spread: {data['home']} {data['spread']}")
    if data.get("moneyline_home"):
        parts.append(f"  Moneyline: {data['home']} {data['moneyline_home']} / {data['away']} {data['moneyline_away']}")
    if data.get("over_under"):
        parts.append(f"  Over/Under: {data['over_under']}")
    return "\n".join(parts)


def odds_denver_lines() -> str:
    """Get all Denver team lines as a text block."""
    lines = []
    for team, sport in [("Denver Broncos", "nfl"), ("Denver Nuggets", "nba"),
                        ("Colorado Avalanche", "nhl")]:
        block = odds_format_block(team, sport)
        if block:
            lines.append(block)
    return "\n".join(lines) if lines else ""


# ═══════════════════════════════════════════════════════════════════════
# COMBINED: Sports Context Builder
# ═══════════════════════════════════════════════════════════════════════

_sports_context_cache = {"text": "", "ts": 0}


def get_sports_context(force: bool = False) -> str:
    """
    Build a real-time sports context block from ESPN + Sleeper.
    Cached 10 minutes. Used to inject into AI prompts across HQ.
    Returns a text block like:
        TODAY (Tue Mar 25, 2026):
        NBA: DAL @ DEN (7pm), LAL @ IND, OKC @ BOS ...
        NCAA: TEX @ PUR, IOWA @ NEB ...
        NFL NEWS: Flacco to Bengals, Wilson to Saints ...
        BRONCOS: Bo Nix (QB1), Jaylen Waddle trade, no injuries ...
        TRENDING: Kenny McIntosh +9738 leagues, OBJ +7735 ...
    """
    if not force and _sports_context_cache["text"] and (time.time() - _sports_context_cache["ts"]) < 600:
        return _sports_context_cache["text"]

    lines = [f"TODAY ({datetime.now().strftime('%a %b %d, %Y')}):"]

    # NBA scores
    try:
        nba = espn_scores("nba", limit=15)
        if nba:
            game_strs = []
            for g in nba[:12]:
                h, a = g["home"], g["away"]
                if g["completed"]:
                    game_strs.append(f"{a['abbr']} {a['score']}-{h['score']} {h['abbr']} (F)")
                else:
                    game_strs.append(f"{a['abbr']} @ {h['abbr']}")
            lines.append(f"NBA: {', '.join(game_strs)}")
    except Exception:
        pass

    # NCAA
    try:
        ncaa = espn_scores("ncaam", limit=10)
        if ncaa:
            game_strs = [f"{g['away']['abbr']} @ {g['home']['abbr']}" for g in ncaa[:6]]
            lines.append(f"NCAA: {', '.join(game_strs)}")
    except Exception:
        pass

    # NFL news
    try:
        nfl_news = espn_news("nfl", limit=6)
        if nfl_news:
            headlines = [n["headline"][:80] for n in nfl_news[:5]]
            lines.append(f"NFL NEWS: {' | '.join(headlines)}")
    except Exception:
        pass

    # NBA news
    try:
        nba_news = espn_news("nba", limit=4)
        if nba_news:
            headlines = [n["headline"][:80] for n in nba_news[:3]]
            lines.append(f"NBA NEWS: {' | '.join(headlines)}")
    except Exception:
        pass

    # Broncos info
    try:
        broncos = espn_team("nfl", "DEN")
        nuggets = espn_team("nba", "DEN")
        team_info = []
        if broncos.get("name"):
            team_info.append(f"Broncos ({broncos.get('record', 'N/A')})")
            if broncos.get("next_event"):
                team_info.append(f"Next: {broncos['next_event']}")
        if nuggets.get("name"):
            team_info.append(f"Nuggets ({nuggets.get('record', 'N/A')})")
        if team_info:
            lines.append(f"DENVER: {' | '.join(team_info)}")
    except Exception:
        pass

    # Broncos injuries from Sleeper
    try:
        injuries = sleeper_injuries("DEN")
        if injuries:
            inj_strs = [f"{p['name']} ({p['injury']})" for p in injuries[:5]]
            lines.append(f"BRONCOS INJURIES: {', '.join(inj_strs)}")
    except Exception:
        pass

    # Trending NFL players
    try:
        trending = sleeper_trending("add", limit=8)
        if trending:
            trend_strs = [f"{p['name']} ({p['team']} {p['position']}) +{p['count']}" for p in trending[:5]]
            lines.append(f"TRENDING PLAYERS: {', '.join(trend_strs)}")
    except Exception:
        pass

    # NFL state
    try:
        state = sleeper_nfl_state()
        if state.get("season"):
            lines.append(f"NFL: {state['season']} season, {state['phase']} phase, week {state.get('week', 'N/A')}")
    except Exception:
        pass

    # Betting lines for Denver teams
    try:
        if odds_available():
            denver_odds = odds_denver_lines()
            if denver_odds:
                lines.append(denver_odds)
    except Exception:
        pass

    text = "\n".join(lines)
    _sports_context_cache["text"] = text
    _sports_context_cache["ts"] = time.time()
    return text


def get_espn_headlines_for_inspo() -> list:
    """Get ESPN headlines formatted for the What's Hot inspiration feed."""
    headlines = []
    for sport in ["nfl", "nba"]:
        try:
            news = espn_news(sport, limit=8)
            for n in news:
                h = n.get("headline", "")
                d = n.get("description", "")
                if h:
                    headlines.append(f"{h}" + (f" — {d[:100]}" if d and d != h else ""))
        except Exception:
            pass
    return headlines


def get_sleeper_trending_for_inspo() -> list:
    """Get Sleeper trending players formatted for inspiration feed."""
    lines = []
    try:
        trending = sleeper_trending("add", limit=10)
        for p in trending:
            if p["count"] > 100:
                lines.append(f"TRENDING: {p['name']} ({p['team']} {p['position']}) added in {p['count']} fantasy leagues in 24h" +
                             (f" — {p['injury']}" if p.get("injury") else ""))
    except Exception:
        pass
    return lines


# ═══════════════════════════════════════════════════════════════════════
# Universal APIs — Work for any content niche
# ═══════════════════════════════════════════════════════════════════════

def get_google_trends(geo: str = "US") -> list:
    """Get Google Trends daily trending searches. Free, no auth."""
    try:
        import xml.etree.ElementTree as ET
        resp = requests.get(
            f"https://trends.google.com/trending/rss?geo={geo}",
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        results = []
        for item in items[:15]:
            title = item.find("title")
            traffic = item.find("{https://trends.google.com/trending/rss}approx_traffic")
            if title is not None and title.text:
                line = f"TRENDING: {title.text}"
                if traffic is not None and traffic.text:
                    line += f" ({traffic.text} searches)"
                results.append(line)
        return results
    except Exception:
        return []


# Niche → subreddit mapping for Reddit integration
_NICHE_SUBREDDITS = {
    "sports": ["nfl", "nba", "hockey", "CFB", "sports"],
    "tech": ["technology", "programming", "artificial", "startups", "gadgets"],
    "finance": ["wallstreetbets", "stocks", "CryptoCurrency", "investing", "finance"],
    "fitness": ["fitness", "bodybuilding", "running", "nutrition", "loseit"],
    "entertainment": ["entertainment", "movies", "television", "Music", "popculture"],
    "politics": ["politics", "worldnews", "news", "geopolitics"],
    "business": ["Entrepreneur", "smallbusiness", "marketing", "startups", "SaaS"],
    "gaming": ["gaming", "pcgaming", "Games", "esports", "Steam"],
    "music": ["Music", "hiphopheads", "indieheads", "WeAreTheMusicMakers"],
    "food": ["food", "Cooking", "MealPrepSunday", "EatCheapAndHealthy"],
    "general": ["popular", "todayilearned", "Futurology"],
}


def get_reddit_trending(niche: str = "general", topics: list = None) -> list:
    """Get trending Reddit posts for a niche. Free, no auth needed."""
    niche_key = niche.lower().split("/")[0].strip()
    subreddits = _NICHE_SUBREDDITS.get(niche_key, _NICHE_SUBREDDITS["general"])[:3]
    results = []
    for sub in subreddits:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=5",
                headers={"User-Agent": "MountPolumbusHQ/1.0"},
                timeout=_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            posts = resp.json().get("data", {}).get("children", [])
            for p in posts:
                d = p.get("data", {})
                title = d.get("title", "")
                ups = d.get("ups", 0)
                comments = d.get("num_comments", 0)
                if title and ups > 50 and not d.get("stickied"):
                    results.append(f"r/{sub}: {title} ({ups:,} upvotes, {comments:,} comments)")
        except Exception:
            continue
    return results[:12]


def get_newsapi_headlines(topics: list = None, niche: str = "general") -> list:
    """Get headlines from NewsAPI.org. Requires NEWSAPI_KEY in secrets."""
    try:
        import streamlit as st
        api_key = st.secrets.get("NEWSAPI_KEY", "")
        if not api_key:
            return []
        # Build query from topics or niche
        if topics:
            q = " OR ".join(topics[:3])
        else:
            q = niche.split("/")[0].strip()
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": q,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 10,
            },
            headers={"X-Api-Key": api_key},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        articles = resp.json().get("articles", [])
        results = []
        for a in articles:
            title = a.get("title", "")
            source = a.get("source", {}).get("name", "")
            if title and "[Removed]" not in title:
                results.append(f"{title}" + (f" — {source}" if source else ""))
        return results
    except Exception:
        return []


def get_coingecko_trending() -> list:
    """Get trending crypto coins from CoinGecko. Free, no auth."""
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        # Trending coins
        for c in data.get("coins", [])[:7]:
            item = c.get("item", {})
            name = item.get("name", "")
            symbol = item.get("symbol", "")
            rank = item.get("market_cap_rank", "?")
            price_change = item.get("data", {}).get("price_change_percentage_24h", {}).get("usd")
            line = f"TRENDING CRYPTO: {name} (${symbol})"
            if rank and rank != "?":
                line += f" — rank #{rank}"
            if price_change is not None:
                direction = "up" if price_change > 0 else "down"
                line += f", {direction} {abs(price_change):.1f}% in 24h"
            results.append(line)
        return results
    except Exception:
        return []
