"""Integration adapters: where real airport feeds would plug in (Round 3 story).

Only the METAR adapter is functional (it parses a raw METAR string). The AODB and
A-CDM adapters define the mapping contract a real integration would implement.
"""
from __future__ import annotations

import re
from typing import Optional

from .simulation.engine import Disruption
from .simulation.scenarios import SANDSTORM_END, SANDSTORM_START


def parse_metar(raw: str) -> dict:
    """Minimal METAR decoding: wind, visibility, weather codes (SA/DU/BLSA/SS/DS/FG)."""
    out: dict = {"raw": raw.strip(), "wind_kt": None, "gust_kt": None, "visibility_m": None, "weather": []}
    w = re.search(r"\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b", raw)
    if w:
        out["wind_kt"] = int(w.group(2))
        out["gust_kt"] = int(w.group(3)) if w.group(3) else None
    v = re.search(r"KT\s+(?:\d{3}V\d{3}\s+)?(\d{4})\b", raw)
    if v:
        out["visibility_m"] = int(v.group(1))
    out["weather"] = re.findall(r"(?<!\S)([+-]?(?:BL|DR)?(?:SA|DU|SS|DS|FG|BR|HZ|TS|RA))(?!\S)", raw)
    return out


def metar_to_disruption(raw: str, start: float = SANDSTORM_START, end: float = SANDSTORM_END) -> Optional[Disruption]:
    """Map decoded METAR to synthetic operating restrictions (thresholds are assumptions)."""
    m = parse_metar(raw)
    vis, wind = m["visibility_m"], max(filter(None, [m["wind_kt"], m["gust_kt"]]), default=0)
    dusty = any(x.replace("+", "").replace("-", "").endswith(("SA", "DU", "SS", "DS")) for x in m["weather"])
    if vis is None or (vis >= 1500 and wind < 30):
        return None
    cap = 12 if vis < 800 else 18 if vis < 1500 else 24
    d = Disruption(label=f"METAR-driven restrictions (vis {vis} m, wind {wind} kt)",
                   kind="sandstorm" if dusty else "low_visibility", start=start, end=end,
                   capacity_overrides=[{"runway": "30R", "capacity_per_hour": cap, "start": start, "end": end}],
                   turnaround_factor=1.3 if dusty else 1.1, visibility_m=vis, wind_kt=wind)
    if vis < 800 or wind >= 35:
        d.runway_closures.append({"runway": "30L", "start": start, "end": end})
    return d


ADAPTERS = [
    {"id": "metar", "name": "METAR weather feed", "status": "functional",
     "maps": "wind, visibility, dust/sand codes -> runway closure, capacity limit, turnaround factor"},
    {"id": "aodb", "name": "Airport Operational Database (AODB)", "status": "contract",
     "maps": "flight schedule, aircraft type, planned stand -> Flight records"},
    {"id": "acdm", "name": "A-CDM milestones (TOBT/TSAT/TTOT)", "status": "contract",
     "maps": "plan off-block and take-off times -> TSAT/TTOT messages for the airport CDM platform"},
    {"id": "rms", "name": "Resource management (stands, crews)", "status": "contract",
     "maps": "stand closures, crew rosters -> gate closures, crew availability"},
]
