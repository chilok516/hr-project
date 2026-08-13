"""UK racing scraper — RacingPost Playwright + text parser.

Format after 'Expand All':
  COURSE_NAME
  Going: GOOD TO FIRM (...)
  Race Title
  6f, Class 6, £4,187.20
  Going: Good To Firm
  3. Cape Toronada
  11/8F                      ← odds on next line (no brackets)
  5. Beach Partee
  13/2
  ...
  5 ran Distances: ... Time: ...
  Winning jockey: ... Winning trainer: ...
  2:30                       ← next race time
"""

import re
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass, asdict
from loguru import logger
import pandas as pd

from config import DATA_RAW


@dataclass
class EURaceResult:
    race_date: str
    country: str
    venue: str
    race_no: int
    race_name: str
    distance: str
    race_class: str
    going: str
    horse_name: str
    finish_pos: int
    win_odds: str
    win_odds_decimal: float
    jockey: str = ""
    trainer: str = ""
    weight: str = ""
    draw: int = 0
    margin: str = ""
    finish_time: str = ""
    horse_no: int = 0


COURSES = {
    'aintree', 'ascot', 'ayr', 'bangor', 'bath', 'beverley', 'brighton',
    'carlisle', 'cartmel', 'catterick', 'chelmsford', 'cheltenham',
    'chepstow', 'chester', 'doncaster', 'epsom', 'exeter', 'fakenham',
    'fontwell', 'goodwood', 'hamilton', 'haydock', 'hereford', 'hexham',
    'huntingdon', 'kelso', 'kempton', 'leicester', 'lingfield', 'ludlow',
    'market rasen', 'musselburgh', 'newbury', 'newcastle', 'newmarket',
    'nottingham', 'perth', 'plumpton', 'pontefract', 'redcar', 'ripon',
    'salisbury', 'sandown', 'sedgefield', 'southwell', 'stratford',
    'taunton', 'thirsk', 'uttoxeter', 'warwick', 'wetherby', 'wincanton',
    'windsor', 'wolverhampton', 'worcester', 'york', 'yarmouth',
    'curragh', 'leopardstown', 'naas', 'fairyhouse', 'punchestown',
    'galway', 'tipperary', 'roscommon', 'clonmel', 'tramore', 'sligo',
    'saratoga', 'delaware', 'woodbine', 'deauville', 'chantilly',
    'longchamp', 'saint-cloud', 'baden-baden', 'hamburg', 'cologne',
}


def parse_results_page(text: str, race_date: str) -> List[EURaceResult]:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    results = []

    current_venue = "Unknown"
    current_race_no = 0
    current_race_name = ""
    current_distance = ""
    current_class = ""
    current_going = ""
    pending_odds = ""

    i = 0
    while i < len(lines):
        line = lines[i]

        # --- VENUE DETECTION ---
        # UPPERCASE line that's a known course, followed by "Going:"
        if (line.isupper() and line.lower() in COURSES 
            and i + 1 < len(lines) and lines[i + 1].startswith("Going:")):
            current_venue = line.title()
            current_race_no = 0
            current_going = lines[i + 1].replace("Going:", "").strip()
            i += 2
            continue

        # --- RACE HEADER ---
        # Distance line: "6f, Class 6, £4,187.20" or "1m 2f, Class 4, £5,000"
        dist_match = re.match(
            r'^(\d+m\s*\d*f|\d+m|\d+f)\s*,\s*Class\s*(\d+)\s*,',
            line, re.IGNORECASE
        )
        if dist_match:
            prev_line = lines[i - 1] if i > 0 else ""
            # Previous non-Going line is likely the race name
            if prev_line and not prev_line.startswith("Going:") and not prev_line.isupper():
                current_race_name = prev_line
            current_distance = dist_match.group(1).strip()
            current_class = f"Class {dist_match.group(2)}"
            current_race_no += 1
            i += 1
            continue

        # --- GOING (in-race) ---
        if line.startswith("Going:") and current_venue != "Unknown":
            current_going = line.replace("Going:", "").strip()
            i += 1
            continue

        # --- HORSE POSITION ---
        pos_match = re.match(r'^(\d{1,2})\.\s+(.+)$', line)
        if pos_match:
            pos = int(pos_match.group(1))
            name = pos_match.group(2).strip()

            # Skip non-horse lines
            if name.lower().startswith(('ran ', 'distances', 'time:', 'winning', 'win:', 'place:', 'dividend')):
                i += 1
                continue

            # Check if odds are on next line
            pending_odds = ""
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if re.match(r'^\d{1,3}/\d{1,2}[FJC]?$', next_line):
                    pending_odds = next_line
                    i += 1  # consume odds line

            if current_venue != "Unknown" and current_race_no > 0:
                results.append(EURaceResult(
                    race_date=race_date, country="UK",
                    venue=current_venue, race_no=current_race_no,
                    race_name=current_race_name, distance=current_distance,
                    race_class=current_class, going=current_going,
                    horse_name=name, finish_pos=pos,
                    win_odds=pending_odds,
                    win_odds_decimal=_frac_to_dec(pending_odds),
                ))

            i += 1
            continue

        # --- RACE SUMMARY (extract jockey/trainer) ---
        jockey_match = re.match(r'^Winning jockey:\s+(.+)$', line)
        if jockey_match and results:
            results[-1].jockey = jockey_match.group(1).strip()
            if i + 1 < len(lines) and lines[i + 1].startswith("Winning trainer:"):
                results[-1].trainer = lines[i + 1].replace("Winning trainer:", "").strip()
                i += 1

        i += 1

    return results


def _frac_to_dec(odds_str: str) -> float:
    if not odds_str:
        return 0.0
    odds_str = re.sub(r'[FJC]$', '', odds_str.strip())
    m = re.match(r'^(\d+)/(\d+)$', odds_str)
    if m:
        return int(m.group(1)) / int(m.group(2)) + 1.0
    return 0.0


async def scrape_uk_date(race_date: str, headless: bool = True) -> List[EURaceResult]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        try:
            await page.goto(
                f"https://www.racingpost.com/results/{race_date}",
                timeout=20000, wait_until="domcontentloaded"
            )
            await page.wait_for_timeout(2000)

            # Quick early-exit: skip if no course names in text
            text_check = await page.inner_text('body')
            has_content = any(w in text_check.lower() for w in [
                'brighton', 'ascot', 'newmarket', 'kempton', 'york',
                'lingfield', 'chelmsford', 'southwell', 'wolverhampton',
                'doncaster', 'goodwood', ' Results - '
            ])
            if not has_content:
                await browser.close()
                return []

            for btn_text in ['Accept All', 'Accept', 'Allow All']:
                try:
                    btn = page.locator(f'button:has-text("{btn_text}")').first
                    if await btn.count() > 0:
                        await btn.click(timeout=2000)
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            try:
                expand = page.locator('text=Expand All').first
                if await expand.count() > 0:
                    await expand.click(timeout=3000)
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            text = await page.inner_text('body')
            results = parse_results_page(text, race_date)

        except Exception:
            results = []
        finally:
            await browser.close()

    return results


async def batch_scrape_uk(start: str, end: str) -> pd.DataFrame:
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")

    all_results = []
    current = start_dt
    while current <= end_dt:
        d = current.strftime("%Y-%m-%d")
        results = await scrape_uk_date(d)
        if results:
            all_results.extend(results)
            logger.info(f"UK {d}: {len(results)} horses")
        current += timedelta(days=1)
        await asyncio.sleep(0.5)

    df = pd.DataFrame([asdict(r) for r in all_results]) if all_results else pd.DataFrame()
    if not df.empty:
        path = DATA_RAW / "uk_race_results.csv"
        df.to_csv(path, index=False)
        logger.info(f"Saved {len(df)} UK results")
    return df


if __name__ == "__main__":
    async def main():
        r = await scrape_uk_date("2026-08-05")
        print(f"{len(r)} results")
        for x in r[:15]:
            print(f"  {x.venue} R{x.race_no} #{x.finish_pos} {x.horse_name:<22s} {x.win_odds} {x.distance} {x.race_class}")

    asyncio.run(main())
