"""HKJC simulcast race card scraper (Sitecore + racing-data GraphQL, no browser).

Two public APIs:
  1. Sitecore GraphQL (consvc.hkjc.com) — race info (name, distance, group) + Entries
     (declared runners: Horse<TAB>Trainer).
  2. info.cld.hkjc.com GraphQL — meeting/race list + odds pools.
"""

import re
import requests
from typing import List, Dict, Optional
from loguru import logger

SITECORE_URL = "https://consvc.hkjc.com/content-api/JCRW/api/graph"
SITECORE_KEY = "{CF83F525-0B06-44FE-B643-3258BCDA089A}"
CLD_URL = "https://info.cld.hkjc.com/graphql/base/"

MEETING_ROOT = "/sitecore/content/Sites/JCRW/Meetings/Simulcast"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://racing.hkjc.com",
    "Referer": "https://racing.hkjc.com/",
}


def _gql(url: str, query: str, variables: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    r = requests.post(url, params=params, json={"query": query, "variables": variables or {}},
                      headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def _sitecore(query: str, variables: dict) -> dict:
    return _gql(SITECORE_URL, query, variables, params={"sc_apikey": SITECORE_KEY})


def list_meetings(date: str) -> List[dict]:
    """Return today's simulcast meetings (venueCode S3/S4/S5 + country + races)."""
    # EXACT query (info.cld GraphQL has a whitelist — must match the SPA's query).
    q = """
query SIM_getUpcomingRace($localSim: LocalSim, $oddsTypes: [OddsType]) {
  commonMeetings(localSim: $localSim) {
    id
    venueCode
    date
    status
    season
    totalNumberOfRace
    currentNumberOfRace
    country {
      code
      namech
      nameen
      seq
    }
    races {
      id
      no
      postTime
      status
      raceResults {
        status
      }
      raceName_en
      raceName_ch
      raceTrack {
        code
        description_ch
        description_en
      }
      countryCodeNm {
        code
        english
        chinese
      }
    }
    pmPools(oddsTypes: $oddsTypes) {
      oddsType
      status
      leg {
        races
      }
    }
  }
}
"""
    r = _gql(CLD_URL, q, {"localSim": "SIM", "oddsTypes": ["WIN"]})
    out = []
    for m in (r.get("data", {}).get("commonMeetings") or []):
        if m.get("date") == date:
            country = (m.get("country") or [{}])[0]
            m["country_name"] = country.get("nameen", "") if isinstance(country, dict) else ""
            out.append(m)
    return out


def get_race_cards(meeting_code: str) -> List[dict]:
    """Return all race cards for a meeting (e.g. '20260821_S3'):
    race info + declared runners (horse + trainer)."""
    # find the meeting path (season/meeting folder)
    meeting = _find_meeting_path(meeting_code)
    if not meeting:
        logger.warning(f"Meeting {meeting_code} not found")
        return []

    q = """
    query SelectedMeetingRacingInfo($path: String, $language: String) {
      item(path: $path, language: $language) {
        races: children {
          displayName
          ... on Race {
            raceName { value }
            venueCode { value }
            raceDatetime { value: formattedDateValue(format: "yyyy-MM-ddTHH:mm:sszzz", offset: -480) }
            raceDistance { value }
            group { value }
          }
          entries: children(includeTemplateIDs: ["D28C1A7DE27245A3BD0FEC767C970347"]) {
            ... on Entries {
              entries { value }
            }
          }
        }
      }
    }
    """
    races_path = f"{MEETING_ROOT}/{meeting['season']}/{meeting_code}/Races"
    r = _sitecore(q, {"path": races_path, "language": "en-us"})
    item = (r.get("data") or {}).get("item") or {}
    cards = []
    for race in item.get("races") or []:
        race_name = (race.get("raceName") or {}).get("value", "")
        dist_raw = (race.get("raceDistance") or {}).get("value", "")
        group = (race.get("group") or {}).get("value", "")
        venue_code = (race.get("venueCode") or {}).get("value", "")
        race_time = (race.get("raceDatetime") or {}).get("value", "")
        # entries: children has one item (Entries folder) with the entries field
        entries_text = ""
        for e in race.get("entries") or []:
            entries_text = (e.get("entries") or {}).get("value", "") or entries_text
        runners = _parse_entries(entries_text)
        cards.append({
            "meeting": meeting_code,
            "venue_code": venue_code,
            "race_name": race_name,
            "distance": _parse_distance(dist_raw),
            "surface": _parse_surface(dist_raw),
            "group": group,
            "race_time": race_time,
            "runners": runners,
        })
    return cards


def _find_meeting_path(meeting_code: str) -> Optional[dict]:
    """Find the season folder for a meeting code via extendedSearch."""
    q = """
    query FindMeeting($path: String, $language: String, $fieldsEqual: [ItemSearchFieldQuery]) {
      extendedSearch(fieldsEqual: $fieldsEqual, rootItem: $path, language: $language,
                     fieldName: "MeetingDate", sortBy: "MeetingDate", sortDesc: false) {
        results { items { meeting: item { ... on MeetingDate { name path season: parent { name } } } } }
      }
    }
    """
    r = _sitecore(q, {
        "path": MEETING_ROOT, "language": "en-us",
        "fieldsEqual": [{"name": "_templateName", "value": "MeetingDate"}],
    })
    items = ((r.get("data") or {}).get("extendedSearch") or {}).get("results", {}).get("items", [])
    for it in items:
        m = it.get("meeting") or {}
        if m.get("name") == meeting_code:
            return {"season": (m.get("season") or {}).get("name", ""), "path": m.get("path", "")}
    return None


def _parse_entries(text: str) -> List[dict]:
    """Parse 'Horse<TAB>Trainer\nNAME (CC)<TAB>TRAINER\n...' -> [{horse, trainer, country}]."""
    runners = []
    lines = [l for l in (text or "").splitlines() if l.strip()]
    for line in lines[1:]:  # skip header
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        horse_raw = parts[0].strip()
        trainer = parts[1].strip()
        m = re.match(r"^(.*?)\s*\(([A-Z]{2,3})\)$", horse_raw)
        if m:
            horse = m.group(1).strip()
            country = m.group(2)
        else:
            horse = horse_raw
            country = ""
        runners.append({"horse": horse, "trainer": trainer, "country": country})
    return runners


def _parse_distance(raw: str) -> int:
    """'1590m Turf' -> 1590."""
    m = re.search(r"(\d+)\s*m", raw or "")
    return int(m.group(1)) if m else 0


def _parse_surface(raw: str) -> str:
    if "turf" in (raw or "").lower():
        return "TURF"
    if "dirt" in (raw or "").lower() or "awt" in (raw or "").lower() or "all weather" in (raw or "").lower():
        return "AWT"
    return ""


FORM_GUIDE_BASE = "https://consvc.hkjc.com/-/media/Sites/JCRW/FormGuide/Simulcast"


def get_starter_runners(meeting_code: str, race_no: int) -> List[dict]:
    """Fetch + parse the official 'Starters List' PDF for accurate runners
    (saddlecloth Card, draw, horse CN/EN, age/sex, weight, rating, trainer, jockey, ref odds)."""
    import io
    import pdfplumber

    meeting = _find_meeting_path(meeting_code)
    if not meeting:
        return []
    season = meeting["season"]
    date = f"{meeting_code[:4]}{meeting_code[4:6]}{meeting_code[6:8]}"
    s_code = meeting_code.split("_")[-1]  # e.g. "S3"
    url = f"{FORM_GUIDE_BASE}/{season}/{date}/OSE{date}_starter_{s_code}_r{race_no}.pdf"

    r = requests.get(url, headers=HEADERS, timeout=60)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        logger.warning(f"Starter PDF not available: {url}")
        return []

    runners = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if "Card" not in txt and "馬號" not in txt:
                continue
            words = page.extract_words()
            header_top = min(w["top"] for w in words if w["text"] in ("Card", "馬號"))
            words = [w for w in words if w["top"] > header_top + 3]
            words.sort(key=lambda w: (round(w["top"]), w["x0"]))

            rows = []
            cur_top = None
            cur = []
            for w in words:
                t2 = round(w["top"])
                if cur_top is None or abs(t2 - cur_top) <= 6:
                    if cur_top is None:
                        cur_top = t2
                    cur.append(w)
                else:
                    rows.append(cur)
                    cur = [w]
                    cur_top = t2
            if cur:
                rows.append(cur)

            def get(ws, lo, hi):
                return " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]) if lo <= w["x0"] <= hi)

            def split_tj(ws):
                ws = sorted(ws, key=lambda w: w["x0"])
                if len(ws) <= 1:
                    return (" ".join(w["text"] for w in ws), "")
                best, best_gap = 0, -1
                for i in range(len(ws) - 1):
                    gap = ws[i + 1]["x0"] - ws[i]["x1"]
                    if gap > best_gap:
                        best_gap, best = gap, i
                return (" ".join(w["text"] for w in ws[:best + 1]),
                        " ".join(w["text"] for w in ws[best + 1:]))

            for i, row in enumerate(rows):
                card_w = [w for w in row if 24 <= w["x0"] <= 46 and w["text"].isdigit()]
                if not card_w:
                    continue
                card = int(card_w[0]["text"])
                en_row = rows[i + 1] if i + 1 < len(rows) else []
                tj_cn = split_tj([w for w in row if 356 <= w["x0"] <= 554])
                tj_en = split_tj([w for w in en_row if 356 <= w["x0"] <= 554])
                runners.append({
                    "horse_no": card,
                    "draw": int(get(row, 130, 152)) if get(row, 130, 152).isdigit() else 0,
                    "horse_cn": get(row, 153, 265),
                    "horse": re.sub(r"\s*\([^)]*\)\s*$", "", get(en_row, 153, 265)).strip(),
                    "age_sex": get(row, 266, 289),
                    "weight": int(get(row, 289, 315)) if get(row, 289, 315).isdigit() else 0,
                    "rating": get(row, 316, 356).strip("[]"),
                    "trainer_cn": tj_cn[0],
                    "jockey_cn": tj_cn[1],
                    "trainer": tj_en[0],
                    "jockey": tj_en[1],
                    "odds": get(row, 555, 590),
                })
    return runners


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-21"
    print("=== meetings ===")
    for m in list_meetings(date):
        print(f"  {m['venueCode']} {m.get('country_name','')} races={len(m.get('races',[]))}")
        for r in m.get("races", [])[:8]:
            print(f"    R{r['no']} {r.get('raceName_en','')} @ {r.get('postTime','')}")

    code = sys.argv[2] if len(sys.argv) > 2 else "20260821_S3"
    print(f"\n=== race cards for {code} ===")
    for c in get_race_cards(code):
        print(f"  {c['venue_code']} {c['race_name']} {c['distance']}m {c['surface']} group={c['group']!r}")
        print(f"    runners={len(c['runners'])}: {', '.join(r['horse'] for r in c['runners'][:5])}...")
