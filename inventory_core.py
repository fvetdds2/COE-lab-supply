"""Lab inventory tracker backed by a Google Sheet.

Core logic shared by the Streamlit app (app.py) and the command line.

The spreadsheet gets two tabs:
  * "Inventory"  - one row per item (see HEADERS)
  * "Change log" - every add/update, with who, when, old and new value

Usage columns drive the restock meter:
  * "Per sample" - units used per extracted sample (e.g. 1 2D tube)
  * "Per run"    - units used per 96-sample KingFisher run (e.g. 4 deep-well plates)
Items with neither are tracked against their fixed "Target" only.

Command line (needs GOOGLE_SERVICE_ACCOUNT_FILE and INVENTORY_SHEET_URL):
    python inventory_core.py init --seed
    python inventory_core.py list
    python inventory_core.py add --item "Filter tips, 10 uL" --unit tip --target 500 --on-hand 200
    python inventory_core.py update INV-0003 --set "On hand=120" --set "Notes=1 case opened" --user DS
    python inventory_core.py coverage --goal 4000
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

# Bumped whenever app.py starts relying on something new in this module.
CORE_VERSION = 5

INVENTORY_TAB = "Inventory"
LOG_TAB = "Change log"
LOCATIONS_TAB = "Locations"
SAMPLES_PER_RUN = 96
TIMEZONE = ZoneInfo("America/Chicago")

HEADERS = [
    "Item ID", "Item", "Category", "Cat. No.", "Unit",
    "Per sample", "Per run", "Target", "On hand", "Reorder at",
    "Status", "Location", "Last checked", "Checked by", "Notes",
]
LOG_HEADERS = ["Timestamp", "User", "Item ID", "Item", "Field", "Old value", "New value"]
LOCATION_HEADERS = ["Location", "Added by", "Added on", "Map X", "Map Y", "Note"]
# Storage places from the lab floor plan: (name, % across the map, % down the map).
# None means the place is not drawn on the map yet. Staff can move pins, add notes and add
# places in the app; those changes are saved in the Locations tab and override these defaults.
PRESET_PLACES = [
    # cold storage room (recalibrated 2026-10-26 to the redrawn floor plan)
    ("Liquid nitrogen tank", 21.0, 9.0),
    ("-80 °C freezer #3", 34.0, 9.0),
    ("4 °C fridge", 45.0, 10.0),
    ("-80 °C freezer #4 (DNA)", 56.0, 9.0),
    ("-80 °C freezer #5", 68.0, 9.0),
    ("-20 °C freezer #1", 79.0, 9.0),
    ("Cold storage supply cabinet", 91.0, 10.0),
    ("storage supply shelf", 98.0, 10.0),
    ("Cart #1", 74.5, 16.0),
    ("Cart #2", 84.5, 16.0),
    ("-80 °C freezer #1", 21.0, 43.0),
    ("-80 °C freezer #2", 34.0, 43.0),
    ("Freezer supplies table", 51.0, 43.0),
    ("Ice machine", 68.0, 44.0),
    ("Freezer box cabinet 1", 66.0, 43.0),
    ("Freezer box cabinet 2", 75.0, 43.0),
    # main lab
    ("Delivery desk", 23.0, 55.0),
    ("PPE station", 53.0, 57.0),
    ("Lab bench #1", 69.0, 52.0),
    ("Supply cabinet 1, upper", None, None),  # superseded by "Lab bench #1, supply cabinet 1"
    ("Supply cabinet 1, lower", None, None),
    ("Supply cabinet 2, upper", None, None),
    ("Supply cabinet 2, lower", None, None),
    ("Lab bench #7, specimen prep", 53.0, 69.0),
    ("Lab bench #6, extraction", 53.0, 77.0),
    ("Sink #2", 29.0, 74.0),
    ("Sink #3", 80.0, 74.0),
    ("Lab desk #1", 90.0, 69.0),
    ("Lab desk #2", 90.0, 73.0),
    ("Lab bench #2, centrifuge", 16.0, 80.0),
    ("Lab bench #3", 29.0, 93.0),
    ("Supply cabinet 3, upper", None, None),  # superseded by "Lab bench #3, Kingfisher supply cabinet …"
    ("Supply cabinet 3, lower", None, None),
    ("Lab bench #4", 50.0, 93.0),
    ("Supply cabinet 4, upper", None, None),  # superseded by "Lab bench #4, supply cabinet …"
    ("Supply cabinet 4, lower", None, None),
    ("BSC #1", 67.0, 93.0),
    ("Chemical hood", 77.0, 93.0),
    ("Flammables cabinet", None, None),  # not drawn on the redrawn floor plan
    ("Lab bench #5, QC", 92.0, 91.0),
    # sub-storage spots, clustered around their parent cabinet/bench pin above
    ("Freezer box cabinet 1, top", 64.0, 41.5),
    ("Freezer box cabinet 1, lower", 68.0, 41.5),
    ("Freezer box cabinet 1, drawer 1", 64.0, 44.5),
    ("Freezer box cabinet 1, drawer 2", 68.0, 44.5),
    ("Freezer box cabinet 1, empty space", 66.0, 46.5),
    ("Freezer box cabinet 2, top", 73.0, 41.5),
    ("Freezer box cabinet 2, lower", 77.0, 41.5),
    ("Freezer box cabinet 2, drawer 1", 73.0, 44.5),
    ("Freezer box cabinet 2, drawer 2", 77.0, 44.5),
    ("Freezer box cabinet 2, empty space", 75.0, 46.5),
    ("Delivery desk, top shelf", 19.0, 53.0),
    ("Delivery desk, drawer 1", 27.0, 53.0),
    ("Delivery desk, drawer 2", 23.0, 58.0),
    ("Lab bench #7, specimen prep, top shelf 1", 44.0, 68.0),
    ("Lab bench #7, specimen prep, top shelf 2", 62.0, 68.0),
    ("Lab bench #7, specimen prep, lower storage", 53.0, 70.5),
    ("Lab bench #6, extraction, top shelf 1", 44.0, 76.0),
    ("Lab bench #6, extraction, top shelf 2", 62.0, 76.0),
    ("Lab bench #6, extraction, lower storage", 53.0, 78.5),
    ("Lab bench #2, centrifuge, drawer 1", 13.0, 70.0),
    ("Lab bench #2, centrifuge, drawer 2", 19.0, 70.0),
    ("Lab bench #2, centrifuge, lower storage", 16.0, 73.0),
    # bench 1-5 storage: supply cabinets and drawers, clustered around each bench's pin above
    ("Lab bench #1, supply cabinet 1", 63.0, 48.5),
    ("Lab bench #1, supply cabinet 2", 74.0, 48.5),
    ("Lab bench #1, supply cabinet 3", 63.0, 55.0),
    ("Lab bench #1, supply cabinet 4", 74.0, 55.0),
    ("Lab bench #1, drawer 1", 60.0, 57.5),
    ("Lab bench #1, drawer 2", 67.0, 57.5),
    ("Lab bench #1, drawer 3", 74.0, 57.5),
    ("Lab bench #1, drawer 4", 81.0, 57.5),
    ("Lab bench #2, centrifuge, drawer 5", 13.0, 76.0),
    ("Lab bench #2, centrifuge, drawer 6", 19.0, 76.0),
    ("Lab bench #2, centrifuge, drawer 7", 16.0, 85.0),
    ("Lab bench #2, centrifuge, supply cabinet 9", 19.0, 82.0),
    ("Lab bench #2, centrifuge, lower storage part", 13.0, 88.0),
    ("Lab bench #3, Kingfisher supply cabinet 1", 24.0, 91.5),
    ("Lab bench #3, Kingfisher supply cabinet 2", 34.0, 91.5),
    ("Lab bench #3, Kingfisher drawer 1", 24.0, 95.0),
    ("Lab bench #3, Kingfisher drawer 2", 34.0, 95.0),
    ("Lab bench #4, supply cabinet 5", 45.0, 97.0),
    ("Lab bench #4, supply cabinet 6", 56.0, 97.0),
    ("Lab bench #4, supply cabinet 7", 45.0, 91.7),
    ("Lab bench #4, supply cabinet 8", 56.0, 91.7),
    ("Lab bench #4, drawer 5", 40.0, 91.7),
    ("Lab bench #4, drawer 6", 40.0, 97.0),
    ("Lab bench #4, drawer 7", 61.0, 91.7),
    ("Lab bench #4, drawer 8", 61.0, 97.0),
    ("Lab bench #5, QC, supply cabinet 10", 91.0, 92.0),
    ("Lab bench #5, QC, supply cabinet 11", 91.0, 97.0),
]
# Starting notes for places whose position on the plan is a guess, or that aren't on the current floor plan.
PRESET_NOTES = {
    "Flammables cabinet": "Not on the redrawn floor plan. Set its position under Edit a location if you want it "
                          "on the map again.",
    "Supply cabinet 1, upper": "Replaced on the redrawn floor plan by \"Lab bench #1, supply cabinet 1\".",
    "Supply cabinet 1, lower": "Replaced on the redrawn floor plan by \"Lab bench #1, supply cabinet 3\".",
    "Supply cabinet 2, upper": "Replaced on the redrawn floor plan by \"Lab bench #1, supply cabinet 2\".",
    "Supply cabinet 2, lower": "Replaced on the redrawn floor plan by \"Lab bench #1, supply cabinet 4\".",
    "Supply cabinet 3, upper": "Replaced on the redrawn floor plan by \"Lab bench #3, Kingfisher supply cabinet 1\".",
    "Supply cabinet 3, lower": "Replaced on the redrawn floor plan by \"Lab bench #3, Kingfisher supply cabinet 2\".",
    "Supply cabinet 4, upper": "Replaced on the redrawn floor plan by \"Lab bench #4, supply "
                              "cabinet 7\".",
    "Supply cabinet 4, lower": "Replaced on the redrawn floor plan by \"Lab bench #4, supply "
                              "cabinet 8\".",
    "Freezer box cabinet 1, empty space": "Open space in the cabinet, not yet assigned to an item.",
    "Freezer box cabinet 2, empty space": "Open space in the cabinet, not yet assigned to an item.",
}
PRESET_LOCATIONS = [name for name, _, _ in PRESET_PLACES]
NUMERIC_FIELDS = {"Per sample", "Per run", "Target", "On hand", "Reorder at"}
EDITABLE_FIELDS = [h for h in HEADERS if h not in ("Item ID", "Last checked", "Checked by")]
STATUS_OPTIONS = ["In stock", "Low", "Ordered", "Out of stock"]

# Starter list for MagMAX DNA Multi-Sample Ultra 2.0 on the KingFisher Apex,
# 200 uL whole blood per sample. Usage per sample/run follows the COE lab supply list.
STARTER_ITEMS = [
    # item, category, cat no, unit, per sample, per run, target
    ("MagMAX DNA Multi-Sample Ultra 2.0 Kit", "Extraction kit", "A36570", "kit", 1 / 200, None, None),
    ("KingFisher Apex 96 deep-well plates, barcoded", "KingFisher consumables", "95040450B", "plate", None, 4, None),
    ("KingFisher Apex 96 KF microplates, barcoded", "KingFisher consumables", "97002540B", "plate", None, 2, None),
    ("KingFisher 96 deep-well tip combs, barcoded", "KingFisher consumables", "97002534B", "tip comb", None, 1, None),
    ("Ethanol, 96-100%, molecular biology grade", "Reagents", "", "L", 0.00088, None, None),
    ("Nuclease-free water", "Reagents", "AM9932", "L", 0.00022, None, None),
    ("MicroAmp Clear Adhesive Film", "KingFisher consumables", "4306311", "film", None, None, None),
    ("Filter tips, 20 uL", "Pipetting", "", "tip", 1, 8, None),
    ("Filter tips, 200 uL", "Pipetting", "", "tip", 2, 8, None),
    ("Filter tips, 300 uL", "Pipetting", "", "tip", 1, None, None),
    ("Filter tips, 1,000 or 1,250 uL", "Pipetting", "", "tip", None, 24, None),
    ("Serological pipettes, 10 and 25 mL", "Pipetting", "", "pipette", None, 3.5, None),
    ("Reagent reservoirs, 25-100 mL", "Pipetting", "", "reservoir", None, 6, None),
    ("Conical tubes, 50 mL", "Tubes and storage", "", "tube", None, 1, None),
    ("2D-barcoded tubes", "Tubes and storage", "", "tube", 1, None, None),
    ("2D tube racks, 96-position", "Tubes and storage", "", "rack", None, 1, None),
    ("Microcentrifuge tubes, 1.5 mL", "Tubes and storage", "", "bag", None, None, 1),
    ("Paraffin film", "Tubes and storage", "", "roll", None, None, 1),
    ("Nitrile gloves", "Safety and waste", "", "box", None, None, None),
    ("Biohazard bags and tip waste bins", "Safety and waste", "", "pack", None, None, None),
    ("Foam coolers with outer cartons", "Dry ice shipping", "", "set", None, None, None),
    ("Leakproof secondary bags and absorbent", "Dry ice shipping", "", "set", None, None, None),
    ("Class 9 labels and UN1845 dry ice markings", "Dry ice shipping", "", "label", None, None, None),
    ("Cryogenic gloves and face shield", "Dry ice shipping", "", "set", None, None, 1),
]


class InventoryError(ValueError):
    """Bad input or an item that cannot be found."""


try:  # a missing tab raises WorksheetNotFound in gspread, KeyError in the in-memory stand-in
    from gspread.exceptions import WorksheetNotFound as _GspreadNotFound
    _NOT_FOUND: tuple = (_GspreadNotFound, KeyError)
except ImportError:  # pragma: no cover - gspread not installed (demo/tests only)
    _NOT_FOUND = (KeyError,)


# --------------------------------------------------------------------------- helpers

def now_text() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")


def to_number(value) -> float | None:
    """Parse a sheet cell into a number; blank -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise InventoryError(f"{value!r} is not a number.") from exc


def clean_number(value) -> str | float:
    """Validate a numeric field for writing; blank stays blank."""
    number = to_number(value)
    if number is None:
        return ""
    if number < 0:
        raise InventoryError("Quantities cannot be negative.")
    return int(number) if number.is_integer() else number


def column_letter(index: int) -> str:
    """1 -> A, 27 -> AA."""
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def auto_status(on_hand: float | None, reorder_at: float | None, current: str = "",
                target: float | None = None) -> str:
    """Status from the count; a manual 'Ordered' sticks until stock is back above the reorder point.

    Low means at or below the reorder level (as in Quartzy's min stock), unless the count
    already meets the item's target.
    """
    if on_hand is None:
        return current or ""
    if on_hand <= 0:
        return "Ordered" if current == "Ordered" else "Out of stock"
    if reorder_at is not None and on_hand <= reorder_at and not (target and on_hand >= target):
        return "Ordered" if current == "Ordered" else "Low"
    return "In stock"


# --------------------------------------------------------------------------- restock math

def runs_needed(goal_samples: int) -> int:
    return math.ceil(goal_samples / SAMPLES_PER_RUN) if goal_samples > 0 else 0


def needed_for_goal(item: dict, goal_samples: int) -> float | None:
    """Units needed for the goal: per-sample and per-run use, else the fixed Target."""
    per_sample = to_number(item.get("Per sample"))
    per_run = to_number(item.get("Per run"))
    if per_sample is None and per_run is None:
        return to_number(item.get("Target"))
    need = (per_sample or 0) * goal_samples + (per_run or 0) * runs_needed(goal_samples)
    return math.ceil(need - 1e-9) if need else 0


def samples_covered(item: dict) -> int | None:
    """How many samples the current stock of this item supports (None if not usage-based)."""
    per_sample = to_number(item.get("Per sample")) or 0
    per_run = to_number(item.get("Per run")) or 0
    if not per_sample and not per_run:
        return None
    on_hand = to_number(item.get("On hand")) or 0
    rate = per_sample + per_run / SAMPLES_PER_RUN
    n = int(on_hand / rate) + SAMPLES_PER_RUN
    while n > 0 and per_sample * n + per_run * math.ceil(n / SAMPLES_PER_RUN) > on_hand + 1e-9:
        n -= 1
    return max(n, 0)


@dataclass
class MeterRow:
    item_id: str
    item: str
    category: str
    unit: str
    on_hand: float
    needed: float
    shortfall: float
    fraction: float
    covered: int | None


def restock_report(items: list[dict], goal_samples: int) -> tuple[list[MeterRow], dict]:
    """Per-item meter rows (most urgent first) and the overall coverage summary."""
    rows: list[MeterRow] = []
    for item in items:
        needed = needed_for_goal(item, goal_samples)
        if not needed:
            continue
        on_hand = to_number(item.get("On hand")) or 0
        rows.append(MeterRow(
            item_id=item.get("Item ID", ""), item=item.get("Item", ""),
            category=item.get("Category", ""), unit=item.get("Unit", ""),
            on_hand=on_hand, needed=needed,
            shortfall=max(needed - on_hand, 0),
            fraction=min(on_hand / needed, 1.0),
            covered=samples_covered(item),
        ))
    rows.sort(key=lambda r: (r.fraction, r.item))
    usage_rows = [r for r in rows if r.covered is not None]
    if usage_rows:
        limiting = min(usage_rows, key=lambda r: r.covered)
        covered = min(limiting.covered, goal_samples)
    else:
        limiting, covered = None, 0
    summary = {
        "goal": goal_samples,
        "runs": runs_needed(goal_samples),
        "covered": covered,
        "limiting_item": limiting.item if limiting else None,
        "items_short": sum(1 for r in rows if r.shortfall > 0),
        "items_tracked": len(rows),
    }
    return rows, summary


# --------------------------------------------------------------------------- sheet access

class InventorySheet:
    """Reads and writes the Inventory, Change log and Locations tabs of one spreadsheet."""

    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet
        self.inventory = self._tab(INVENTORY_TAB, HEADERS)
        self.log = self._tab(LOG_TAB, LOG_HEADERS)
        self.places = self._tab(LOCATIONS_TAB, LOCATION_HEADERS)

    def _tab(self, title: str, headers: list[str]):
        try:
            ws = self.spreadsheet.worksheet(title)
        except _NOT_FOUND:
            ws = self.spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
        if hasattr(ws, "col_count") and ws.col_count < len(headers):
            ws.add_cols(len(headers) - ws.col_count)  # older tab with fewer columns
        first_row = ws.get_all_values()[:1]
        if not first_row or first_row[0][: len(headers)] != headers:
            if first_row and any(cell.strip() for cell in first_row[0]):
                existing = [c for c in first_row[0] if c.strip()]
                if existing != headers[: len(existing)]:
                    raise InventoryError(
                        f"The '{title}' tab already has different column headers. "
                        "Use an empty tab or rename the existing one."
                    )
            ws.update(values=[headers], range_name=f"A1:{column_letter(len(headers))}1")
        return ws

    # ---- reading
    def items(self) -> list[dict]:
        values = self.inventory.get_all_values()
        return [
            {h: (row[i] if i < len(row) else "") for i, h in enumerate(HEADERS)}
            for row in values[1:]
            if any(cell.strip() for cell in row)
        ]

    def get(self, item_id: str) -> tuple[int, dict]:
        """Return (sheet row number, item) for an Item ID."""
        values = self.inventory.get_all_values()
        for row_number, row in enumerate(values[1:], start=2):
            if row and row[0].strip().upper() == item_id.strip().upper():
                return row_number, {h: (row[i] if i < len(row) else "") for i, h in enumerate(HEADERS)}
        raise InventoryError(f"No item with ID {item_id}.")

    # ---- storage locations
    def _saved_places(self) -> list[list[str]]:
        rows = self.places.get_all_values()[1:]
        return [(r + [""] * len(LOCATION_HEADERS))[: len(LOCATION_HEADERS)] for r in rows if r and r[0].strip()]

    @staticmethod
    def _coord(value) -> float | None:
        try:
            number = to_number(value)
        except InventoryError:
            return None
        return None if number is None else max(0.0, min(100.0, number))

    def location_details(self) -> list[dict]:
        """Every location with its map position and note: presets first, then ones staff added."""
        saved = {}
        for name, by, on, x, y, note in self._saved_places():
            saved.setdefault(name.strip().lower(), {
                "name": name.strip(), "added_by": by, "x": self._coord(x), "y": self._coord(y),
                "note": note, "saved": True,
            })
        result, seen = [], set()
        for name, x, y in PRESET_PLACES:
            row = saved.get(name.lower())
            if row:
                result.append({**row, "name": name, "preset": True})
            else:
                result.append({"name": name, "added_by": "", "x": x, "y": y, "note": PRESET_NOTES.get(name, ""),
                               "saved": False, "preset": True})
            seen.add(name.lower())
        for key, row in saved.items():
            if key not in seen:
                result.append({**row, "preset": False})
                seen.add(key)
        return result

    def locations(self) -> list[str]:
        """Location names: presets first, then the ones staff added."""
        return [d["name"] for d in self.location_details()]

    def add_location(self, name: str, user: str, x: float | None = None, y: float | None = None,
                     note: str = "") -> str:
        """Save a new location to the Locations tab and the change log; returns the cleaned name."""
        name = " ".join(str(name).split())
        if not name:
            raise InventoryError("Enter a location name.")
        if not user.strip():
            raise InventoryError("Enter your initials first.")
        known = {n.lower(): n for n in self.locations()}
        if name.lower() in known:
            return known[name.lower()]
        self.places.append_row([name, user.strip().upper(), now_text(), clean_number(x) if x is not None else "",
                                clean_number(y) if y is not None else "", note.strip()],
                               value_input_option="USER_ENTERED")
        self._log(user.strip().upper(), "-", "(location list)", "New location", "", name)
        return name

    def update_location(self, name: str, user: str, x: float | None, y: float | None, note: str) -> None:
        """Save a location's map position (None, None = not on the map) and note."""
        if not user.strip():
            raise InventoryError("Enter your initials first.")
        who = user.strip().upper()
        current = next((d for d in self.location_details() if d["name"].lower() == name.lower()), None)
        if current is None:
            raise InventoryError(f"No location called {name}.")
        x = None if x is None else round(max(0.0, min(100.0, float(x))), 1)
        y = None if y is None else round(max(0.0, min(100.0, float(y))), 1)
        note = str(note or "").strip()
        values = ["" if x is None else x, "" if y is None else y, note]
        row_number = next((i for i, r in enumerate(self.places.get_all_values()[1:], start=2)
                           if r and r[0].strip().lower() == name.lower()), None)
        if row_number:
            self.places.update(values=[values], range_name=f"D{row_number}:F{row_number}",
                               value_input_option="USER_ENTERED")
        else:
            self.places.append_row([current["name"], who, now_text(), *values], value_input_option="USER_ENTERED")
        where = lambda a, b: "not on map" if a is None else f"{a}, {b}"  # noqa: E731
        if (current["x"], current["y"]) != (x, y):
            self._log(who, "-", current["name"], "Map position", where(current["x"], current["y"]), where(x, y))
        if (current["note"] or "").strip() != note:
            self._log(who, "-", current["name"], "Location note", current["note"], note)

    def changes(self, limit: int = 200) -> list[dict]:
        values = self.log.get_all_values()
        rows = [dict(zip(LOG_HEADERS, r)) for r in values[1:] if any(c.strip() for c in r)]
        return rows[-limit:][::-1]

    # ---- writing
    def _next_id(self) -> str:
        numbers = []
        for item in self.items():
            tail = item["Item ID"].rsplit("-", 1)[-1]
            if tail.isdigit():
                numbers.append(int(tail))
        return f"INV-{(max(numbers) + 1) if numbers else 1:04d}"

    def _log(self, user: str, item_id: str, item: str, field: str, old, new) -> None:
        self.log.append_row(
            [now_text(), user, item_id, item, field, str(old), str(new)],
            value_input_option="USER_ENTERED",
        )

    def add_item(self, data: dict, user: str) -> str:
        name = str(data.get("Item", "")).strip()
        if not name:
            raise InventoryError("Item name is required.")
        if not user.strip():
            raise InventoryError("Enter your initials so the change is logged.")
        if any(i["Item"].strip().lower() == name.lower() for i in self.items()):
            raise InventoryError(f"'{name}' is already in the inventory. Update it instead.")
        record = {h: "" for h in HEADERS}
        for field, value in data.items():
            if field not in HEADERS or field == "Item ID":
                continue
            record[field] = clean_number(value) if field in NUMERIC_FIELDS else str(value).strip()
        record["Item"] = name
        if record["Status"] and record["Status"] not in STATUS_OPTIONS:
            raise InventoryError(f"Status must be one of: {', '.join(STATUS_OPTIONS)}.")
        record["Status"] = auto_status(to_number(record["On hand"]), to_number(record["Reorder at"]),
                                       record["Status"], to_number(record["Target"]))
        record["Item ID"] = self._next_id()
        record["Last checked"] = now_text()
        record["Checked by"] = user.strip()
        self.inventory.append_row([record[h] for h in HEADERS], value_input_option="USER_ENTERED")
        self._log(user, record["Item ID"], name, "(new item)", "", f"On hand {record['On hand'] or 0}")
        return record["Item ID"]

    def update_item(self, item_id: str, changes: dict, user: str, reason: str = "") -> dict:
        """Write changed fields; `reason` (e.g. "received +10") is added to the On hand log entry."""
        if not user.strip():
            raise InventoryError("Enter your initials so the change is logged.")
        row_number, item = self.get(item_id)
        updated = dict(item)
        changed_fields = []
        for field, value in changes.items():
            if field not in EDITABLE_FIELDS:
                raise InventoryError(f"'{field}' cannot be edited.")
            new = clean_number(value) if field in NUMERIC_FIELDS else str(value).strip()
            if field == "Item" and not new:
                raise InventoryError("Item name cannot be blank.")
            if field == "Status" and new and new not in STATUS_OPTIONS:
                raise InventoryError(f"Status must be one of: {', '.join(STATUS_OPTIONS)}.")
            if str(new) != str(item[field]):
                updated[field] = new
                changed_fields.append(field)
        if "Status" not in changes or "On hand" in changes:
            status = auto_status(to_number(updated["On hand"]), to_number(updated["Reorder at"]),
                                 str(updated["Status"]), to_number(updated["Target"]))
            if status != updated["Status"]:
                updated["Status"] = status
                changed_fields.append("Status")
        updated["Last checked"] = now_text()
        updated["Checked by"] = user.strip()
        last_col = column_letter(len(HEADERS))
        self.inventory.update(
            values=[[updated[h] for h in HEADERS]],
            range_name=f"A{row_number}:{last_col}{row_number}",
            value_input_option="USER_ENTERED",
        )
        for field in dict.fromkeys(changed_fields):
            label = f"{field} ({reason})" if reason and field == "On hand" else field
            self._log(user, item["Item ID"], updated["Item"], label, item[field], updated[field])
        if not changed_fields:
            self._log(user, item["Item ID"], updated["Item"], "(checked)", "", "no change")
        return updated

    def adjust_on_hand(self, item_id: str, received: float, used: float, user: str) -> dict:
        """Add what arrived and subtract what was used, reading the latest count from the sheet first."""
        received, used = to_number(received) or 0, to_number(used) or 0
        if received < 0 or used < 0:
            raise InventoryError("Received and used must be zero or more.")
        if not received and not used:
            raise InventoryError("Enter an amount received or used.")
        _, item = self.get(item_id)
        current = to_number(item["On hand"]) or 0
        new_total = current + received - used
        if new_total < 0:
            raise InventoryError(f"Only {current:g} {item['Unit'] or 'units'} on hand; cannot use {used:g}.")
        parts = ([f"received +{received:g}"] if received else []) + ([f"used -{used:g}"] if used else [])
        return self.update_item(item_id, {"On hand": new_total}, user, reason=", ".join(parts))

    def seed_starter_items(self, user: str, goal_samples: int = 4000) -> int:
        """Add the COE lab starter list (skips names already present)."""
        existing = {i["Item"].strip().lower() for i in self.items()}
        added = 0
        for name, category, cat_no, unit, per_sample, per_run, target in STARTER_ITEMS:
            if name.lower() in existing:
                continue
            probe = {"Per sample": per_sample, "Per run": per_run, "Target": target}
            needed = needed_for_goal(probe, goal_samples)
            self.add_item({
                "Item": name, "Category": category, "Cat. No.": cat_no, "Unit": unit,
                "Per sample": "" if per_sample is None else round(per_sample, 6),
                "Per run": "" if per_run is None else per_run,
                "Target": "" if needed is None else needed,
                "On hand": "",  # blank = not counted yet
                "Reorder at": "" if needed is None else math.ceil(needed * 0.25),
            }, user)
            added += 1
        return added


# --------------------------------------------------------------------------- connections

def connect_service_account(sheet_url_or_key: str, *, info: dict | None = None,
                            filename: str | None = None) -> InventorySheet:
    """Open the spreadsheet with a Google service account (dict from secrets, or a JSON key file)."""
    import gspread

    client = gspread.service_account_from_dict(info) if info else gspread.service_account(filename=filename)
    if sheet_url_or_key.startswith("http"):
        spreadsheet = client.open_by_url(sheet_url_or_key)
    else:
        spreadsheet = client.open_by_key(sheet_url_or_key)
    return InventorySheet(spreadsheet)


class MemoryWorksheet:
    """Minimal in-memory stand-in for a gspread Worksheet (demo mode and tests)."""

    def __init__(self, title: str):
        self.title = title
        self.rows: list[list[str]] = []

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self.rows]

    def append_row(self, values, value_input_option=None):
        self.rows.append(["" if v is None else str(v) for v in values])

    def update(self, values, range_name, value_input_option=None):
        start = range_name.split(":")[0]
        row_number = int("".join(ch for ch in start if ch.isdigit()))
        col = 0
        for ch in "".join(ch for ch in start if ch.isalpha()).upper():
            col = col * 26 + (ord(ch) - 64)
        while len(self.rows) < row_number:
            self.rows.append([])
        row = self.rows[row_number - 1]
        new = ["" if v is None else str(v) for v in values[0]]
        row.extend([""] * max(0, col - 1 + len(new) - len(row)))
        row[col - 1: col - 1 + len(new)] = new


class MemorySpreadsheet:
    def __init__(self):
        self.tabs: dict[str, MemoryWorksheet] = {}

    def worksheet(self, title: str) -> MemoryWorksheet:
        if title not in self.tabs:
            raise KeyError(title)
        return self.tabs[title]

    def add_worksheet(self, title: str, rows: int, cols: int) -> MemoryWorksheet:
        self.tabs[title] = MemoryWorksheet(title)
        return self.tabs[title]


# --------------------------------------------------------------------------- command line

def _cli_sheet() -> InventorySheet:
    key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    sheet = os.environ.get("INVENTORY_SHEET_URL")
    if not key_file or not sheet:
        sys.exit("Set GOOGLE_SERVICE_ACCOUNT_FILE and INVENTORY_SHEET_URL first (see README.md).")
    return connect_service_account(sheet, filename=key_file)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Lab inventory tracker (Google Sheets).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create the tabs and headers.")
    p_init.add_argument("--seed", action="store_true", help="Add the COE lab starter item list.")
    p_init.add_argument("--user", default="setup")

    sub.add_parser("list", help="Show all items.")

    p_add = sub.add_parser("add", help="Add a new item.")
    p_add.add_argument("--item", required=True)
    for flag in ("category", "cat-no", "unit", "location", "notes", "status"):
        p_add.add_argument(f"--{flag}", default="")
    for flag in ("per-sample", "per-run", "target", "on-hand", "reorder-at"):
        p_add.add_argument(f"--{flag}", default="")
    p_add.add_argument("--user", required=True)

    p_upd = sub.add_parser("update", help="Update fields of an item.")
    p_upd.add_argument("item_id")
    p_upd.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    p_upd.add_argument("--user", required=True)

    p_cov = sub.add_parser("coverage", help="Restock report for a sample goal.")
    p_cov.add_argument("--goal", type=int, default=4000)

    args = parser.parse_args(argv)
    sheet = _cli_sheet()

    if args.command == "init":
        if args.seed:
            print(f"Added {sheet.seed_starter_items(args.user)} starter items.")
        print("Inventory and Change log tabs are ready.")
    elif args.command == "list":
        for item in sheet.items():
            print(f"{item['Item ID']:9} {item['On hand']:>8} {item['Unit']:10} {item['Status']:12} {item['Item']}")
    elif args.command == "add":
        data = {
            "Item": args.item, "Category": args.category, "Cat. No.": args.cat_no,
            "Unit": args.unit, "Location": args.location, "Notes": args.notes, "Status": args.status,
            "Per sample": args.per_sample, "Per run": args.per_run, "Target": args.target,
            "On hand": args.on_hand, "Reorder at": args.reorder_at,
        }
        print(f"Added {sheet.add_item(data, args.user)}.")
    elif args.command == "update":
        changes = {}
        for pair in args.set:
            if "=" not in pair:
                sys.exit(f"Use FIELD=VALUE, got {pair!r}.")
            field, value = pair.split("=", 1)
            changes[field.strip()] = value
        updated = sheet.update_item(args.item_id, changes, args.user)
        print(f"Updated {updated['Item ID']}: on hand {updated['On hand']}, status {updated['Status']}.")
    elif args.command == "coverage":
        rows, summary = restock_report(sheet.items(), args.goal)
        print(f"Stock covers {summary['covered']:,} of {summary['goal']:,} samples "
              f"({summary['runs']} runs). Limiting item: {summary['limiting_item']}.")
        for r in rows:
            print(f"{r.fraction:6.0%}  {r.on_hand:>8g} / {r.needed:<8g} {r.unit:10} short {r.shortfall:<8g} {r.item}")


if __name__ == "__main__":
    try:
        main()
    except InventoryError as exc:
        sys.exit(f"Error: {exc}")
