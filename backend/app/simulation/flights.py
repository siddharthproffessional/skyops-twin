"""Deterministic synthetic flight bank (seeded). All data is synthetic."""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict

from .config import AIRCRAFT_TYPES, AIRLINES, TIMING

ORIGINS = [
    "London", "Mumbai", "Paris", "Singapore", "Frankfurt", "Delhi", "Cairo",
    "Istanbul", "Karachi", "Riyadh", "Manila", "Nairobi", "Colombo", "Muscat",
    "Kuwait", "Bahrain", "Doha", "Amman", "Kochi", "Lahore", "Dhaka", "Milan",
    "Zurich", "Madrid", "Tokyo", "Sydney", "Johannesburg", "Moscow", "Baku", "Tbilisi",
]
DESTS = [
    "Manchester", "Bengaluru", "Rome", "Bangkok", "Munich", "Hyderabad", "Athens",
    "Vienna", "Chennai", "Jeddah", "Jakarta", "Dar es Salaam", "Male", "Salalah",
    "Dammam", "Tehran", "Beirut", "Larnaca", "Kozhikode", "Islamabad", "Kathmandu",
    "Barcelona", "Geneva", "Lisbon", "Seoul", "Melbourne", "Cape Town", "Warsaw",
    "Almaty", "Yerevan",
]


@dataclass
class Flight:
    id: str
    airline: str
    airline_name: str
    aircraft: str
    size: str
    origin: str
    destination: str
    sta: float            # scheduled landing (sim minutes)
    std: float            # scheduled off-block for the outbound leg
    pax: int
    connecting: int
    planned_gate: str = ""
    priority: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


MIX = ["A388"] * 3 + ["B77W"] * 8 + ["A359"] * 7 + ["A321"] * 9 + ["B38M"] * 9


def build_flights(seed: int = 36) -> list[Flight]:
    rng = random.Random(seed)
    types = MIX[:]
    rng.shuffle(types)
    # make sure the A380s are spread across the bank
    n = len(types)
    arrivals = sorted(rng.uniform(4, 165) for _ in range(n))
    airlines = list(AIRLINES)
    flights: list[Flight] = []
    used_numbers: set[str] = set()
    for i, (ac, sta) in enumerate(zip(types, arrivals)):
        spec = AIRCRAFT_TYPES[ac]
        al = airlines[i % len(airlines)]
        while True:
            num = f"{al}{rng.randint(100, 989)}"
            if num not in used_numbers:
                used_numbers.add(num)
                break
        load = rng.uniform(0.78, 0.96)
        pax = int(spec["seats"] * load)
        wide = spec["size"] in ("E", "F")
        conn_share = rng.uniform(0.35, 0.6) if wide else rng.uniform(0.08, 0.3)
        connecting = int(pax * conn_share)
        slack = rng.uniform(10, 22)
        std = sta + TIMING["taxi_in_min"] + spec["turnaround_min"] + slack
        f = Flight(
            id=num,
            airline=al,
            airline_name=AIRLINES[al],
            aircraft=ac,
            size=spec["size"],
            origin=ORIGINS[i % len(ORIGINS)],
            destination=DESTS[(i * 7) % len(DESTS)],
            sta=round(sta, 1),
            std=round(std, 1),
            pax=pax,
            connecting=connecting,
        )
        f.priority = round((pax + 2 * connecting) / 100.0, 2)
        flights.append(f)
    return flights
