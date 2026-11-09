"""Synthetic airport configuration.

EVERY value in this file is a synthetic assumption for a competition prototype.
None of it describes a real airport, airline or certified operating procedure.
"""
from __future__ import annotations

BASE_CLOCK = "14:00"  # t = 0 minutes in the simulation is shown as 14:00 local
SIM_WINDOW_MIN = 300  # metrics window: 14:00 -> 19:00

AIRPORT = {
    "code": "SKY",
    "name": "SkyOps International (synthetic hub)",
    "note": "Synthetic airport. All parameters are illustrative assumptions.",
}

# Parallel runways. capacity = movements per hour (arrivals + departures).
RUNWAYS = [
    {"id": "30L", "capacity_per_hour": 32},
    {"id": "30R", "capacity_per_hour": 32},
]

# ICAO aerodrome reference code letter: C (narrow-body) < E (wide-body) < F (A380)
SIZE_RANK = {"C": 1, "E": 2, "F": 3}

GATES = [
    {"id": "A1", "size": "F", "zone": "A", "kind": "contact"},
    {"id": "A2", "size": "F", "zone": "A", "kind": "contact"},
    {"id": "A3", "size": "F", "zone": "A", "kind": "contact"},
    {"id": "A4", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A5", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A6", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A7", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A8", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A9", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A10", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A11", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "A12", "size": "E", "zone": "A", "kind": "contact"},
    {"id": "B1", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B2", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B3", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B4", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B5", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B6", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B7", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B8", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B9", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "B10", "size": "C", "zone": "B", "kind": "contact"},
    {"id": "R1", "size": "E", "zone": "R", "kind": "remote"},
    {"id": "R2", "size": "E", "zone": "R", "kind": "remote"},
    {"id": "R3", "size": "C", "zone": "R", "kind": "remote"},
    {"id": "R4", "size": "C", "zone": "R", "kind": "remote"},
]

AIRCRAFT_TYPES = {
    "A388": {"size": "F", "seats": 489, "turnaround_min": 105, "label": "Airbus A380-800"},
    "B77W": {"size": "E", "seats": 354, "turnaround_min": 85, "label": "Boeing 777-300ER"},
    "A359": {"size": "E", "seats": 300, "turnaround_min": 75, "label": "Airbus A350-900"},
    "A321": {"size": "C", "seats": 190, "turnaround_min": 45, "label": "Airbus A321neo"},
    "B38M": {"size": "C", "seats": 172, "turnaround_min": 40, "label": "Boeing 737 MAX 8"},
}

# Ground handling crews (one crew services one turnaround at a time).
CREWS = [
    {"id": "GH-A1", "zone": "A"},
    {"id": "GH-A2", "zone": "A"},
    {"id": "GH-A3", "zone": "A"},
    {"id": "GH-A4", "zone": "A"},
    {"id": "GH-A5", "zone": "A"},
    {"id": "GH-A6", "zone": "A"},
    {"id": "GH-A7", "zone": "A"},
    {"id": "GH-A8", "zone": "A"},
    {"id": "GH-A9", "zone": "A"},
    {"id": "GH-B1", "zone": "B"},
    {"id": "GH-B2", "zone": "B"},
    {"id": "GH-B3", "zone": "B"},
    {"id": "GH-B4", "zone": "B"},
    {"id": "GH-B5", "zone": "B"},
    {"id": "GH-B6", "zone": "B"},
    {"id": "GH-R1", "zone": "R"},
    {"id": "GH-R2", "zone": "R"},
]

TIMING = {
    "taxi_in_min": 8,
    "taxi_out_min": 10,
    "gate_buffer_min": 5,         # minimum gap between two aircraft on one gate
    "remote_stand_penalty_min": 12,  # bussing + stairs at remote stands
    "crew_transfer_min": 6,       # pooled crew moving between zones
    "max_airborne_hold_min": 45,  # beyond this an arrival diverts (fuel assumption)
    "delay_threshold_min": 15,    # a flight counts as "delayed" above this
    "missed_connection_arrival_delay_min": 40,
    "diversion_passenger_delay_min": 240,  # assumed delay per passenger on a diverted flight
}

AIRLINES = {
    "FA": "Falcon Air",
    "DN": "Dune Airways",
    "PG": "Pearl Gulf",
    "OJ": "Oasis Jet",
    "MR": "Meridian Air",
}
