"""ADR-001: Incident report parsing from HKJC LocalResults.aspx."""

import re
from typing import Dict


INCIDENT_PATTERNS = {
    "hampered": r"(?i)hamper|checked|crowded|tighten|shifted|bumped|taken\s?in",
    "wide": r"(?i)wide|without\s?cover|three.?wide|four.?wide|hung\s?out",
    "slow_start": r"(?i)slow(?:ly)?\s+(?:into\s+stride|to\s+begin|away|beginning)|began\s+slow|missed\s+the\s+start|reared",
    "bled": r"(?i)bled|blood|epistaxis|blood\s+in\s+trachea",
    "irregular_heart": r"(?i)irregular\s+heart|cardiac|arrhythmia|atrial|fibrillation",
    "lame": r"(?i)lame|lameness|stiffness|pulled\s?up",
    "roarer": r"(?i)roar|displaced\s+palate|respiratory|throat|wind\s+sucker",
    "unbalanced": r"(?i)unbalanced|hung\s+(?:in|out)|lay\s+(?:in|out)|inclined",
    "no_incident": r"(?i)^(?:no\s+report|no\s+findings|nothing\s+to\s+report|no\s+apparent|ridden\s+out)$",
    "stumbled": r"(?i)stumbl|blundered|jumped\s+shadow",
    "knuckled": r"(?i)knuckl|bucked|refused",
}


def parse_incidents(remark_text: str) -> Dict[str, bool]:
    if not remark_text or not isinstance(remark_text, str):
        return _empty_flags()

    flags = {}
    for name, pattern in INCIDENT_PATTERNS.items():
        flags[name] = bool(re.search(pattern, remark_text))

    flags["had_interference"] = flags.get("hampered", False) or flags.get("wide", False)
    flags["medical_issue"] = (
        flags.get("bled", False) or
        flags.get("irregular_heart", False) or
        flags.get("lame", False) or
        flags.get("roarer", False)
    )
    flags["had_excuse"] = (
        flags["had_interference"] or
        flags["medical_issue"] or
        flags.get("slow_start", False) or
        flags.get("stumbled", False) or
        flags.get("knuckled", False)
    )
    flags["clean_run"] = flags.get("no_incident", False) and not flags["had_excuse"]

    return flags


def _empty_flags() -> Dict[str, bool]:
    return {
        "hampered": False, "wide": False, "slow_start": False,
        "bled": False, "irregular_heart": False, "lame": False,
        "roarer": False, "unbalanced": False, "no_incident": False,
        "stumbled": False, "knuckled": False,
        "had_interference": False, "medical_issue": False,
        "had_excuse": False, "clean_run": False,
    }


def get_excuse_features(flags: Dict[str, bool]) -> Dict[str, float]:
    return {
        "excuse_interference": float(flags.get("had_interference", False)),
        "excuse_medical": float(flags.get("medical_issue", False)),
        "excuse_slow_start": float(flags.get("slow_start", False)),
        "excuse_any": float(flags.get("had_excuse", False)),
        "excuse_clean": float(flags.get("clean_run", False)),
    }
