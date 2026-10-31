from __future__ import annotations

import base64
import hmac
import html
import io
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import inventory_core as ic

CENTER_NAME = "Center of Excellence for Clinical and Translational Research"
APP_TITLE = "Laboratory Supply Inventory"
APP_NAME = f"{CENTER_NAME} {APP_TITLE}"

# Meharry Medical College logo (dark version for the white header), embedded so app.py works on its own.
MEHARRY_LOGO = "data:image/png;base64,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"
st.set_page_config(page_title=APP_NAME, page_icon="🧪", layout="wide",
                   initial_sidebar_state="collapsed")

METER = "#b8237a"  # magenta: meter fill and covered runs (5.9:1 on white)
# Stock states, most urgent first: (label, icon, text color, tint). Each state always shows an
# icon and a word, never color alone. Text colors pass 4.5:1 on their tint.
STATES = {
    "out": ("Out of stock", "✕", "#b42318", "#fde8e8"),
    "low": ("Low stock", "▲", "#8a5300", "#fff3d1"),
    "none": ("Not counted", "ring", "#4b5563", "#eef1f5"),
    "nomin": ("No minimum set", "dash", "#4b5563", "#eef1f5"),
    "ok": ("In stock", "✓", "#17692a", "#e3f4e6"),
}
STATE_ORDER = list(STATES)
FILTERS = {  # status filter above the item list -> states it shows
    "All": set(STATES),
    "Needs action": {"out", "low"},
    "Not counted": {"none"},
    "No minimum": {"nomin"},
    "In stock": {"ok"},
}
REFRESH_SECONDS = 30  # how often the meter and inventory re-read the sheet

# Where each starter item goes on the lab floor plan (liquids in lower cabinets, light
# everyday consumables in upper ones). Used by "Fill in suggested locations" on the Map page.
SUGGESTED_PLACES = {
    "MagMAX DNA Multi-Sample Ultra 2.0 Kit": "Lab bench #1, supply cabinet 3",
    "Nuclease-free water": "Lab bench #1, supply cabinet 3",
    "Reagent reservoirs, 25-100 mL": "Lab bench #1, supply cabinet 1",
    "Conical tubes, 50 mL": "Lab bench #1, supply cabinet 1",
    "KingFisher Apex 96 deep-well plates, barcoded": "Lab bench #1, supply cabinet 4",
    "KingFisher Apex 96 KF microplates, barcoded": "Lab bench #1, supply cabinet 2",
    "KingFisher 96 deep-well tip combs, barcoded": "Lab bench #1, supply cabinet 2",
    "MicroAmp Clear Adhesive Film": "Lab bench #1, supply cabinet 2",
    "Filter tips, 20 uL": "Lab bench #3, KingFisher, supply cabinet 7",
    "Filter tips, 200 uL": "Lab bench #3, KingFisher, supply cabinet 7",
    "Filter tips, 300 uL": "Lab bench #3, KingFisher, supply cabinet 7",
    "Microcentrifuge tubes, 1.5 mL": "Lab bench #3, KingFisher, supply cabinet 7",
    "Paraffin film": "Lab bench #3, KingFisher, supply cabinet 7",
    "Filter tips, 1,000 or 1,250 uL": "Lab bench #3, KingFisher, supply cabinet 8",
    "Serological pipettes, 10 and 25 mL": "Lab bench #3, KingFisher, supply cabinet 8",
    "Biohazard bags and tip waste bins": "Bench #4, supply cabinet 9",
    "Nitrile gloves": "PPE station",
    "Ethanol, 96-100%, molecular biology grade": "Flammables cabinet",
    "2D-barcoded tubes": "Freezer supplies table",
    "2D tube racks, 96-position": "Freezer supplies table",
    "Cryogenic gloves and face shield": "Freezer supplies table",
    "Foam coolers with outer cartons": "storage supply shelf",
    "Leakproof secondary bags and absorbent": "storage supply shelf",
    "Class 9 labels and UN1845 dry ice markings": "storage supply shelf",
}
DEMO_LOCATIONS = {k: v for k, v in SUGGESTED_PLACES.items() if k != "Nitrile gloves"}  # demo only
MAP_FILE = Path(__file__).with_name("lab_map.png")  # the lab floor plan shown on the Map page
DEMO_COUNTS = {  # example counts for demo mode only
    "MagMAX DNA Multi-Sample Ultra 2.0 Kit": 8,
    "KingFisher Apex 96 deep-well plates, barcoded": 200,
    "KingFisher Apex 96 KF microplates, barcoded": 60,
    "KingFisher 96 deep-well tip combs, barcoded": 100,
    "Ethanol, 96-100%, molecular biology grade": 2.5,
    "Nuclease-free water": 1,
    "Filter tips, 20 uL": 4800,
    "Filter tips, 200 uL": 1800,
    "Filter tips, 300 uL": 4000,
    "Filter tips, 1,000 or 1,250 uL": 960,
    "Serological pipettes, 10 and 25 mL": 200,
    "Reagent reservoirs, 25-100 mL": 120,
    "Conical tubes, 50 mL": 100,
    "2D-barcoded tubes": 1920,
    "2D tube racks, 96-position": 25,
    "Microcentrifuge tubes, 1.5 mL": 1,
    "Paraffin film": 0,
    "Nitrile gloves": 12,
    "Cryogenic gloves and face shield": 1,
}


# --------------------------------------------------------------------------- connection

REQUIRED_CORE = 7  # the inventory_core.py version this app.py needs


def check_core_version() -> None:
    """Stop with a plain message when inventory_core.py on the server is older than app.py."""
    if getattr(ic, "CORE_VERSION", 0) < REQUIRED_CORE:
        st.error("**inventory_core.py on the server is older than app.py.** Upload the new "
                 "inventory_core.py next to app.py, commit and sync it, then open Manage app, "
                 "the three-dot menu, and choose Reboot app.")
        st.stop()


@st.cache_resource(show_spinner="Connecting to Google Sheets...")
def live_sheet(sheet_url: str, account: tuple, core_version: int) -> ic.InventorySheet:
    # core_version is part of the cache key, so a new inventory_core.py gets a fresh connection
    return ic.connect_service_account(sheet_url, info=dict(account))


def demo_sheet() -> ic.InventorySheet:
    if "demo_sheet" not in st.session_state or not hasattr(st.session_state.demo_sheet, "location_details"):
        sheet = ic.InventorySheet(ic.MemorySpreadsheet())
        sheet.seed_starter_items("demo")
        for item in sheet.items():
            changes = {}
            if item["Item"] in DEMO_COUNTS:
                changes["On hand"] = DEMO_COUNTS[item["Item"]]
            if item["Item"] in DEMO_LOCATIONS:
                changes["Location"] = DEMO_LOCATIONS[item["Item"]]
            if changes:
                sheet.update_item(item["Item ID"], changes, "demo")
        st.session_state.demo_sheet = sheet
    return st.session_state.demo_sheet


def secrets_problem() -> str:
    """Why the app cannot use the Google Sheet, or "" when the secrets look complete."""
    try:
        names = list(st.secrets.keys())
    except Exception as exc:  # no secrets.toml, or one that is not valid TOML
        text = str(exc)
        if "No secrets found" in text:
            return ("No secrets were found. On your computer or in Codespaces, put `secrets.toml` "
                    "in the `.streamlit` folder next to app.py and restart the app. On Streamlit "
                    "Cloud, paste it into the app's Settings → Secrets.")
        return f"`secrets.toml` was found but could not be read: {text}"
    if "gcp_service_account" not in names:
        return "`secrets.toml` has no `[gcp_service_account]` section. Run make_secrets.py again."
    if "sheet_url" not in names:
        hint = ""
        if "sheet_url" in st.secrets["gcp_service_account"]:
            hint = " It is inside `[gcp_service_account]`; move it to the first line, above that section."
        return "`secrets.toml` has no `sheet_url`." + hint
    return ""


def connection_help(exc: Exception) -> str:
    """Plain-language fix for a failed connection to the Google Sheet."""
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()
    if "has not been used" in low or "service_disabled" in low or "is disabled" in low:
        tip = ("Turn on the **Google Sheets API** and **Google Drive API** in Google Cloud "
               "project MMCCCLInventory, wait a minute, then reload.")
    elif any(word in low for word in ("invalid_grant", "jwt", "pem", "private key", "invalid key")):
        tip = ("The key in secrets.toml is damaged or was deleted. Create a new JSON key for the "
               "service account and run make_secrets.py again.")
    elif "notfound" in low or "404" in low:
        tip = ("Check `sheet_url` in secrets.toml, and that the sheet is shared with the "
               "service account email.")
    elif "permission" in low or "403" in low:
        tip = ("Share the COE lab inventory sheet with the service account email "
               "(client_email in secrets.toml) as **Editor**.")
    else:
        tip = "Check the internet connection, then reload the page."
    return f"Could not connect to the Google Sheet. {tip}\n\nDetails: `{text[:300]}`"


def get_sheet() -> tuple[ic.InventorySheet, str]:
    """The live sheet and "", or the demo sheet and the reason demo mode is on."""
    check_core_version()
    problem = secrets_problem()
    if problem:
        return demo_sheet(), problem
    account = tuple(sorted(dict(st.secrets["gcp_service_account"]).items()))
    try:
        sheet = live_sheet(st.secrets["sheet_url"], account, ic.CORE_VERSION)
        if not hasattr(sheet, "location_details"):  # connection made by older code still in memory
            live_sheet.clear()
            sheet = live_sheet(st.secrets["sheet_url"], account, ic.CORE_VERSION)
        return sheet, ""
    except Exception as exc:  # shown on the page instead of a traceback; retried on reload
        st.title(APP_NAME)
        st.error(connection_help(exc))
        st.stop()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def load_items(_sheet: ic.InventorySheet) -> list[dict]:
    return _sheet.items()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def load_locations(_sheet: ic.InventorySheet) -> list[str]:
    return _sheet.locations()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def load_map_checks(_sheet: ic.InventorySheet) -> tuple[dict, list[str]]:
    """Old place names still in use, and built-in pins moved by hand (re-read every REFRESH_SECONDS)."""
    return _sheet.renamed_places_in_use(), _sheet.saved_pin_positions()


def refresh() -> None:
    load_items.clear()  # every session re-reads the sheet after a write
    load_locations.clear()
    load_map_checks.clear()


# --------------------------------------------------------------------------- helpers

def plural(unit: str, amount: float) -> str:
    if amount == 1 or not unit or unit.endswith("s") or unit in ("L", "mL", "uL", "kg", "g"):
        return unit
    return unit + ("es" if unit.endswith(("x", "ch", "sh")) else "s")


def fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


@dataclass
class Stock:
    """One item as the meter sees it: count, minimum alert level and optional full-stock level."""
    item_id: str
    item: str
    category: str
    unit: str
    on_hand: float | None   # None = not counted yet
    minimum: float | None   # alert at or below this; None or 0 = no minimum set
    full: float | None      # optional full-stock level (sheet column Target); sets the bar length
    when: str
    who: str
    cat_no: str
    location: str

    @property
    def state(self) -> str:
        if self.on_hand is None:
            return "none"
        if self.on_hand <= 0:
            return "out"
        if not self.minimum:
            return "nomin"
        return "low" if self.on_hand <= self.minimum else "ok"

    @property
    def scale(self) -> float | None:
        """Length of a full bar: the full-stock level, or twice the minimum when none is set."""
        scale = self.full or (2 * self.minimum if self.minimum else None)
        if scale and self.minimum and scale < self.minimum:
            scale = 2 * self.minimum
        return scale

    @property
    def suggested(self) -> float | None:
        """Quantity to order: up to the full-stock level, or back to twice the minimum."""
        if self.on_hand is None:
            return None
        if self.full and self.full > self.on_hand:
            return self.full - self.on_hand
        if self.minimum and 2 * self.minimum > self.on_hand:
            return 2 * self.minimum - self.on_hand
        return None

    @property
    def order(self) -> float | None:
        """Suggested order for items at or below their minimum."""
        return self.suggested if self.state in ("out", "low") else None


def stock_rows(items: list[dict]) -> list[Stock]:
    rows = []
    for i in items:
        minimum = ic.to_number(i.get("Reorder at"))
        rows.append(Stock(
            item_id=i["Item ID"], item=i["Item"], category=i.get("Category", ""), unit=i.get("Unit", ""),
            on_hand=ic.to_number(i.get("On hand")), minimum=minimum or None,
            full=ic.to_number(i.get("Target")) or None, when=i.get("Last checked", ""),
            who=i.get("Checked by", ""), cat_no=i.get("Cat. No.", ""),
            location=str(i.get("Location", "")).strip(),
        ))
    rows.sort(key=lambda r: (STATE_ORDER.index(r.state),
                             (r.on_hand or 0) / r.scale if r.scale else 1, r.item.lower()))
    return rows


def short_date(stamp: str) -> str:
    """'2026-10-21 09:45' -> '21 Oct' this year, '21 Oct 2025' otherwise."""
    try:
        when = datetime.strptime(str(stamp)[:10], "%Y-%m-%d")
    except ValueError:
        return str(stamp)
    text = f"{when.day} {when:%b}"
    return text if when.year == datetime.now().year else f"{text} {when.year}"


# --------------------------------------------------------------------------- look and feel

PAGE_CSS = """
<style>
:root {
  --ink: #1f2937; --muted: #5b6474; --line: #dfe3ea; --paper: #f2f4f7; --card: #ffffff;
  --magenta: #b8237a; --track: #e7ebf0;
}
.block-container, [data-testid="stMainBlockContainer"] {
  max-width: 1180px; padding-top: 4.5rem; padding-bottom: 4rem;
}
.num { font-variant-numeric: tabular-nums; }

/* masthead: center name on the first line, app name on the second */
.masthead { background: var(--card); color: var(--ink); border: 1px solid var(--line); border-radius: 20px; padding: 24px 28px;
            display: grid; grid-template-columns: auto minmax(0, 1fr); grid-template-areas: "logo text";
            gap: 12px 26px; align-items: center; margin: 0 0 20px; position: relative; }
.masthead .conn { position: absolute; right: 24px; bottom: 22px; }
.mast-logo { grid-area: logo; height: 58px; width: auto; display: block; }
.mast-text { grid-area: text; min-width: 0; border-left: 1px solid var(--line); padding-left: 26px; }
.conn { grid-area: conn; }
.mast-name { margin: 0; }
.mast-center { display: block; font-size: 19px; font-weight: 500; line-height: 1.35;
               color: var(--muted); }
.mast-title { display: block; font-size: 38px; font-weight: 700; line-height: 1.15; letter-spacing: -0.4px;
              color: var(--ink); margin-top: 2px; }
.conn { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600;
        color: var(--muted); white-space: nowrap; align-self: start; padding: 6px 12px; border-radius: 999px;
        background: var(--paper); border: 1px solid var(--line); }
.conn i { width: 8px; height: 8px; border-radius: 50%; background: #17a34a; display: inline-block; }
.conn.demo i { background: #e0a100; }

/* alert summary at the top of the meter */
.summary { border-radius: 16px; padding: 22px 26px; margin: 4px 0 18px; border: 1px solid; }
.summary.alert { background: #fff8e6; border-color: #f1d79c; }
.summary.clear { background: #effaf1; border-color: #bfe5c7; }
.summary.empty { background: var(--card); border-color: var(--line); }
.sum-big { font-size: 24px; font-weight: 600; color: var(--ink); line-height: 1.25; }
.sum-big b { font-size: 52px; font-weight: 700; letter-spacing: -1px; margin-right: 10px; vertical-align: -6px; }
.summary.alert .sum-big b { color: #8a5300; }
.summary.clear .sum-big b { color: #17692a; }
.sum-list { font-size: 17px; color: var(--ink); margin-top: 10px; line-height: 1.5; }
.sum-quiet { font-size: 15px; color: var(--muted); margin-top: 8px; }

/* status pills */
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px 3px 8px;
        border-radius: 999px; font-size: 14.5px; font-weight: 600; white-space: nowrap; }
.pill b { font-size: 11px; width: 14px; display: inline-flex; justify-content: center; }
.ico-ring, .ico-half { width: 10px; height: 10px; border-radius: 50%; border: 1.6px solid currentColor;
                       box-sizing: border-box; display: inline-block; }
.ico-half { background: linear-gradient(90deg, currentColor 50%, transparent 50%); }
.ico-dash { width: 10px; height: 2px; border-radius: 1px; background: currentColor; display: inline-block; }

/* item list, grouped by category */
.group { margin: 22px 0 0; }
.group-title { font-size: 18px; font-weight: 700; color: var(--ink); margin: 0 0 8px 2px; }
.group-title span { color: var(--muted); font-weight: 400; margin-left: 6px; }
.group-list { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
              padding: 2px 20px; }
.item { padding: 14px 0 13px; }
.item + .item { border-top: 1px solid var(--line); }
.item-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.item-loc { display: flex; align-items: center; gap: 5px; font-size: 15px; color: var(--muted); margin-top: 3px; }
.item-loc .pin { width: 15px; height: 15px; flex: none; }
.item-name { font-size: 18px; font-weight: 600; color: var(--ink); line-height: 1.3; }
.bar { position: relative; height: 10px; border-radius: 5px; background: var(--track); margin: 10px 0 8px; }
.bar.unknown { background: repeating-linear-gradient(135deg, #eef1f5 0 6px, #e2e6ec 6px 12px); }
.bar .fill { height: 100%; border-radius: 5px; background: var(--magenta); }
.bar .tick { position: absolute; top: -4px; width: 2px; height: 18px; border-radius: 1px;
             background: var(--ink); opacity: 0.7; }
.item-meta { display: flex; flex-wrap: wrap; gap: 4px 22px; font-size: 15.5px; color: var(--muted); }
.item-meta b { color: var(--ink); font-weight: 700; }
.item-meta .when { margin-left: auto; }
.list-foot { font-size: 15px; color: var(--muted); margin: 14px 2px 0; }

/* lab map */
.map-scroll { overflow-x: auto; border-radius: 14px; border: 1px solid var(--line); background: #fff; }
.map-wrap { position: relative; }
.map-wrap img { width: 100%; display: block; }
.mpin { position: absolute; transform: translate(-50%, -50%); min-width: 22px; height: 22px; padding: 0 5px;
       border-radius: 11px; background: var(--magenta); color: #fff; font-size: 12px; font-weight: 700;
       display: inline-flex; align-items: center; justify-content: center; box-sizing: border-box;
       border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.35); text-decoration: none !important;
       line-height: 1; cursor: pointer; }
a.mpin, a.mpin:visited, a.mpin:hover { color: #fff; }
a.mpin:hover { transform: translate(-50%, -50%) scale(1.2); z-index: 3; }
.mpin.low { background: #b45309; }
.mpin.out { background: #b42318; }
.mpin.empty { min-width: 12px; width: 12px; height: 12px; padding: 0; background: #fff; border: 2px solid #9aa3af;
             box-shadow: none; }
.mpin.sel { z-index: 4; transform: translate(-50%, -50%) scale(1.35); outline: 3px solid #1f2937; outline-offset: 2px;
           animation: pin-pulse 1.4s ease-out infinite; }
.mpin.dim { opacity: 0.3; }
.mpin.badge { position: static; transform: none; flex: none; box-shadow: none; cursor: default; }
.mpin.badge.empty { min-width: 14px; width: 14px; height: 14px; }
@keyframes pin-pulse { 0% { box-shadow: 0 0 0 0 rgba(31,41,55,0.55); } 100% { box-shadow: 0 0 0 16px rgba(31,41,55,0); } }
@media (prefers-reduced-motion: reduce) { .mpin.sel { animation: none; } }
.find-box { display: flex; gap: 12px; align-items: flex-start; background: #fff7fb; border: 1px solid #f3c6dd;
            border-radius: 14px; padding: 12px 16px; margin: 4px 0 12px; }
.find-box > svg.pin { position: static; transform: none; width: 22px; height: 22px; min-width: 0; padding: 0;
                      border: 0; box-shadow: none; background: none; color: var(--magenta); flex: none; margin-top: 2px;
                      cursor: default; }
.find-item { font-size: 18px; font-weight: 700; color: var(--ink); }
.find-item span { font-weight: 400; color: var(--muted); font-size: 15px; margin-left: 10px; }
.find-trail { font-size: 17px; color: var(--ink); margin-top: 2px; }
.find-note { font-size: 14px; color: var(--muted); margin-top: 4px; }
.room-head { font-size: 15px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
             color: var(--muted); margin: 22px 2px 0; }
.spot { font-size: 13px; font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; color: var(--muted);
        margin: 12px 0 0; }
.loc-empty.small { font-size: 14px; margin-top: 4px; }
.loc-card { scroll-margin-top: 90px; }
.loc-card:target { outline: 3px solid var(--magenta); outline-offset: 2px; }
.map-key { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 15px; color: var(--muted); margin: 10px 2px 4px; }
.map-key span { display: inline-flex; align-items: center; gap: 6px; }
.map-key i { width: 14px; height: 14px; border-radius: 50%; display: inline-block; }
.loc-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.loc-card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; }
.loc-head { display: flex; align-items: center; gap: 10px; }
.loc-name { font-size: 17px; font-weight: 700; color: var(--ink); line-height: 1.25; }
.loc-count { color: var(--muted); font-weight: 400; font-size: 15px; margin-left: 4px; }
.loc-note { font-size: 15px; color: var(--ink); background: #f6f7f9; border-radius: 8px; padding: 6px 10px;
            margin-top: 10px; white-space: pre-wrap; }
.loc-items { list-style: none; margin: 10px 0 0; padding: 0; }
.loc-items li { display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 15px;
                padding: 6px 0; border-top: 1px solid var(--line); }
.loc-items li span:first-child { min-width: 0; }
.loc-items .qty { color: var(--muted); white-space: nowrap; }
.loc-empty { font-size: 15px; color: var(--muted); margin-top: 8px; }

/* Streamlit pieces */
[data-testid="stWidgetLabel"] p { font-size: 16px !important; }
.st-key-view button p, .st-key-meter_filter button p, .st-key-refresh button p,
[data-testid="stPopover"] button p, [data-testid="stBaseButton-secondary"] p,
[data-testid="stBaseButton-primary"] p { font-size: 16px; }
input, textarea, [data-baseweb="select"] div { font-size: 16px !important; }
[data-testid="stCaptionContainer"] p { font-size: 15px; }
[data-testid="stForm"] { background: var(--card); border-radius: 14px; }
[data-testid="stExpander"] details { background: var(--card); border-radius: 14px; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }

.st-key-meter_filter [role="radiogroup"] { flex-wrap: wrap; overflow: visible; }

@media (max-width: 760px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding: 4rem 1rem 3rem; }
  .st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px; }
  .st-key-topbar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
  .st-key-topbar [data-testid="stColumn"]:nth-child(1) { flex: 1 1 0 !important; }
  .st-key-topbar [data-testid="stColumn"]:nth-child(2) { flex: 0 0 48px !important; }
  .st-key-refresh button p { display: none; }
  .st-key-refresh button { padding-left: 0; padding-right: 0; }
  .st-key-view [role="radiogroup"] { display: grid !important; grid-template-columns: repeat(3, minmax(0, 1fr));
                                      gap: 6px; }
  .st-key-view button { border-radius: 999px !important; margin: 0 !important; width: 100%; }
  .st-key-view button { padding-left: 4px !important; padding-right: 4px !important; }
  .st-key-view button p { font-size: 16px; }
  .masthead { grid-template-columns: auto 1fr; grid-template-areas: "logo conn" "text text";
              padding: 18px 18px 18px; gap: 16px 12px; border-radius: 16px; }
  .mast-logo { height: 38px; }
  .masthead .conn { position: static; }
  .mast-text { border-left: 0; padding-left: 0; border-top: 1px solid var(--line); padding-top: 14px; }
  .mast-center { font-size: 15px; }
  .conn { justify-self: end; font-size: 13px; padding: 4px 10px; }
  .mast-title { font-size: 24px; }
  .summary { padding: 18px 16px; }
  .map-wrap { min-width: 760px; }
  .loc-grid { grid-template-columns: 1fr; }
  .sum-big { font-size: 20px; }
  .sum-big b { font-size: 44px; }
  .sum-list { font-size: 16px; }
  .group-list { padding: 2px 14px; }
  .item-name { font-size: 17px; }
  .item-meta { gap: 2px 14px; font-size: 15px; }
  .item-meta .when { margin-left: 0; width: 100%; }
  button[kind="primary"], button[kind="secondary"] { min-height: 2.75rem; }
}
</style>
"""


def pill(state: str, count: int | None = None) -> str:
    label, icon, ink, tint = STATES[state]
    extra = f" {count}" if count is not None else ""
    mark = f'<i class="ico-{icon}"></i>' if icon in ("ring", "half", "dash") else icon
    return (f'<span class="pill" style="color:{ink};background:{tint};">'
            f'<b aria-hidden="true">{mark}</b>{label}{extra}</span>')


def summary_html(rows: list[Stock]) -> str:
    alerts = [r for r in rows if r.state in ("out", "low")]
    uncounted = sum(1 for r in rows if r.state == "none")
    no_min = sum(1 for r in rows if r.state == "nomin")
    quiet = []
    if uncounted:
        quiet.append(f"{uncounted} {'item is' if uncounted == 1 else 'items are'} not counted yet.")
    if no_min:
        quiet.append(f"{no_min} {'item has' if no_min == 1 else 'items have'} no minimum set. "
                     "Use Set minimums and locations below to add one.")
    quiet_html = "".join(f'<div class="sum-quiet">{q}</div>' for q in quiet)
    if alerts:
        names = ", ".join(html.escape(r.item) for r in alerts[:6])
        more = f" and {len(alerts) - 6} more" if len(alerts) > 6 else ""
        word = "item needs" if len(alerts) == 1 else "items need"
        return (f'<section class="summary alert"><div class="sum-big"><b class="num">{len(alerts)}</b>{word} '
                f'reordering</div><div class="sum-list">▲ At or below the minimum: {names}{more}.</div>'
                f"{quiet_html}</section>")
    if any(r.state == "ok" for r in rows):
        return (f'<section class="summary clear"><div class="sum-big"><b>✓</b>Everything is above its '
                f'minimum</div>{quiet_html}</section>')
    return (f'<section class="summary empty"><div class="sum-big">Count the shelf and set minimums to get '
            f'low-stock alerts</div>{quiet_html}</section>')


def item_html(r: Stock) -> str:
    unit_word = html.escape(plural(r.unit, r.on_hand if r.on_hand is not None else 2))
    meta = []
    if r.on_hand is None:
        bar = '<div class="bar unknown"></div>'
        meta.append("<span>Not counted yet</span>")
    else:
        meta.append(f'<span><b class="num">{fmt(r.on_hand)}</b> {unit_word} on hand</span>')
        if r.scale:
            tick = ""
            if r.minimum:
                tick = (f'<div class="tick" style="left:calc({min(r.minimum / r.scale, 1) * 100:.1f}% - 1px);" '
                        'title="Minimum"></div>')
            share = min(r.on_hand / r.scale, 1)
            bar = (f'<div class="bar"><div class="fill" style="width:{share * 100:.1f}%;"></div>{tick}</div>')
        else:
            bar = '<div class="bar unknown"></div>'
    if r.minimum:
        meta.append(f'<span>Minimum <span class="num">{fmt(r.minimum)}</span></span>')
    if r.full:
        meta.append(f'<span>Full stock <span class="num">{fmt(r.full)}</span></span>')
    if r.order:
        meta.append(f'<span>Order <span class="num">{fmt(r.order)}</span></span>')
    if r.when:
        by = f" by {html.escape(str(r.who))}" if r.who else ""
        meta.append(f'<span class="when">Checked {html.escape(short_date(r.when))}{by}</span>')
    where = (f'<div class="item-loc">{PIN}{html.escape(r.location)}</div>' if r.location else "")
    return (f'<div class="item"><div class="item-top"><div><div class="item-name">{html.escape(r.item)}</div>'
            f'{where}</div>{pill(r.state)}</div>{bar}<div class="item-meta">{"".join(meta)}</div></div>')


PIN = ('<svg class="pin" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
       'd="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5'
       'a2.5 2.5 0 0 1 0 5z"/></svg>')
NO_LOCATION = "No location set"


def groups_html(rows: list[Stock], group_order: list[str], by: str = "category") -> str:
    groups: dict[str, list[Stock]] = {}
    for r in rows:
        key = (r.category or "Other") if by == "category" else (r.location or NO_LOCATION)
        groups.setdefault(key, []).append(r)
    order = [c for c in group_order if c in groups] + sorted(c for c in groups if c not in group_order)
    if NO_LOCATION in order:  # unplaced items last
        order.remove(NO_LOCATION)
        order.append(NO_LOCATION)
    parts = []
    for cat in order:
        body = "".join(item_html(r) for r in groups[cat])
        parts.append(f'<section class="group"><div class="group-title">{html.escape(cat)}'
                     f'<span>{len(groups[cat])}</span></div><div class="group-list">{body}</div></section>')
    return "".join(parts)


# --------------------------------------------------------------------------- page helpers

def flash(message: str) -> None:
    """Re-read the sheet and rerun so every view shows the new numbers, then show the message."""
    st.session_state.flash = message
    refresh()
    st.rerun()


def location_options(items: list[dict]) -> list[str]:
    """Preset and added locations, plus any location already typed on an item."""
    known = sheet.locations() if demo else load_locations(sheet)
    lower = {k.lower() for k in known}
    extra = sorted({str(i.get("Location", "")).strip() for i in items} - {""}, key=str.lower)
    return known + [e for e in extra if e.lower() not in lower]


def remember_location(name: str) -> str:
    """Save a location typed in a form to the shared list (if it is new) and return its clean name."""
    name = " ".join(str(name or "").split())
    if name and name.lower() not in {k.lower() for k in location_options([])}:
        name = sheet.add_location(name, user)
    return name


def current_items() -> list[dict]:
    return sheet.items() if demo else load_items(sheet)  # demo data lives in this session only


def item_picker(items: list[dict], key: str, label: str = "Item") -> dict:
    by_id = {i["Item ID"]: i for i in items}
    chosen = st.selectbox(label, list(by_id), key=key,
                          format_func=lambda i: f"{by_id[i]['Item']} ({i})")
    return by_id[chosen]


def show_location(item: dict) -> None:
    place = str(item.get("Location", "")).strip()
    st.markdown(f'<div class="item-loc">{PIN}{html.escape(place) if place else "No location set"}</div>',
                unsafe_allow_html=True)


def on_hand_text(item: dict) -> str:
    value = ic.to_number(item["On hand"])
    if value is None:
        return "not counted"
    return f"{fmt(value)} {plural(item['Unit'] or 'units', value)}"


def needs_initials() -> bool:
    if not user:
        st.warning("Enter your initials at the top before saving.")
        return True
    return False


# --------------------------------------------------------------------------- page

def masthead(connection: str = "") -> None:
    st.markdown(
        f'<header class="masthead"><img class="mast-logo" src="{MEHARRY_LOGO}" alt="Meharry Medical College">'
        '<div class="mast-text">'
        f'<div class="mast-name" role="heading" aria-level="1"><span class="mast-center">{CENTER_NAME}</span>'
        f'<span class="mast-title">{APP_TITLE}</span></div></div>'
        f"{connection}</header>",
        unsafe_allow_html=True,
    )


def login_settings() -> dict | None:
    """User name and password from the [login] section of the secrets, or None when not set."""
    try:
        if "login" not in st.secrets:
            return None
        cfg = st.secrets["login"]
        return {"username": str(cfg.get("username", "")), "password": str(cfg.get("password", ""))}
    except Exception:  # no secrets file at all
        return None


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


MAX_TRIES, LOCK_SECONDS = 5, 60


def require_login() -> None:
    """Show the sign-in screen and stop until the right user name and password are entered."""
    cfg = login_settings()
    if cfg is None or st.session_state.get("signed_in"):
        return
    masthead()
    _, middle, _ = st.columns([1, 1.4, 1])
    with middle:
        locked_for = int(st.session_state.get("locked_until", 0) - time.time())
        with st.form("sign_in"):
            st.subheader("Sign in")
            name = st.text_input("User name", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", width="stretch",
                                              disabled=locked_for > 0)
        if locked_for > 0:
            st.warning(f"Too many tries. Wait {locked_for} seconds, then reload the page.")
        elif submitted:
            if same(name.strip(), cfg["username"]) and same(password, cfg["password"]):
                st.session_state.signed_in = True
                st.session_state.pop("failed_tries", None)
                st.rerun()
            tries = st.session_state.get("failed_tries", 0) + 1
            st.session_state.failed_tries = tries
            if tries >= MAX_TRIES:
                st.session_state.locked_until = time.time() + LOCK_SECONDS
                st.session_state.failed_tries = 0
                st.rerun()  # show the wait message and disable the button right away
            st.error("User name or password is incorrect.")
    st.stop()


st.markdown(PAGE_CSS, unsafe_allow_html=True)
require_login()
sheet, demo_reason = get_sheet()
demo = bool(demo_reason)
masthead('<span class="conn demo"><i></i>Demo data</span>' if demo
         else '<span class="conn"><i></i>Live from Google Sheets</span>')
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"), icon=":material/check_circle:")
if demo:
    st.info("Demo mode: example counts, not your inventory.\n\n**Why:** " + demo_reason)

with st.container(key="topbar"):
    top1, top2 = st.columns([4, 1], vertical_alignment="bottom", gap="small")
    user = top1.text_input("Your initials", key="user", max_chars=8, placeholder="e.g. DS",
                           help="Required. Saved with the date and time of every receive, use, count and change.")
    user = user.strip().upper()
    if top2.button("Refresh", key="refresh", icon=":material/refresh:", width="stretch",
                   help="Read the latest numbers from Google Sheets now."):
        refresh()
        st.rerun()

items = current_items()
if not items:
    st.warning("The inventory sheet is empty.")
    if st.button("Add COE starter item list", disabled=not user):
        added = sheet.seed_starter_items(user)
        flash(f"Added {added} starter items.")

VIEWS = ["Map", "Meter", "Order", "Receive", "Use", "Count", "Items", "Edit", "Log"]
view = st.segmented_control("Go to", VIEWS, default="Map", key="view", label_visibility="collapsed")
view = view or "Map"


# ---- Meter (the summary and list re-read the sheet on their own)
@st.fragment(run_every=REFRESH_SECONDS)
def meter_summary() -> None:
    st.markdown(summary_html(stock_rows(current_items())), unsafe_allow_html=True)


def clean_min(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value) or None


def add_location_clicked(box: str = "new_location") -> None:
    """Runs before the page redraws, so the text box can be cleared after saving."""
    who = st.session_state.get("user", "").strip().upper()
    if not who:
        st.session_state.location_error = "Enter your initials at the top before saving."
        return
    try:
        added = sheet.add_location(st.session_state.get(box, ""), who)
    except ic.InventoryError as exc:
        st.session_state.location_error = str(exc)
        return
    st.session_state[box] = ""
    refresh()
    st.session_state.flash = f"Added location: {added}."


def minimum_editor(items: list[dict]) -> None:
    with st.expander("Set minimums and locations", icon=":material/edit_note:"):
        st.caption("Each item turns Low stock, and shows in the alert above, when its count is at or below "
                   "its minimum. Leave a minimum blank or 0 for no alert. Pick each item's location from "
                   "the list; add a place that is missing with Add location.")
        places = location_options(items)
        n1, n2 = st.columns([3, 1], vertical_alignment="bottom")
        new_place = n1.text_input("Add a new location", key="new_location",
                                  placeholder="e.g. Cold room, shelf 2",
                                  help="Adds it to the Location list for everyone.")
        n2.button("Add location", icon=":material/add_location_alt:", width="stretch", key="add_location",
                  on_click=add_location_clicked)
        if "location_error" in st.session_state:
            st.error(st.session_state.pop("location_error"))
        order = list(dict.fromkeys(i["Category"] for i in items))
        ordered = sorted(items, key=lambda i: (order.index(i["Category"]), i["Item"].lower()))
        table = pd.DataFrame([{
            "Item ID": i["Item ID"], "Item": i["Item"], "On hand": ic.to_number(i["On hand"]),
            "Unit": i["Unit"], "Minimum": clean_min(ic.to_number(i["Reorder at"])),
            "Location": str(i.get("Location", "")).strip() or None,
        } for i in ordered])
        edited = st.data_editor(
            table, key="minimum_table", hide_index=True, width="stretch", num_rows="fixed",
            disabled=["Item", "On hand", "Unit"],
            column_config={
                "Item ID": None,
                "Item": st.column_config.TextColumn("Item", width="large"),
                "On hand": st.column_config.NumberColumn("On hand", format="%g"),
                "Minimum": st.column_config.NumberColumn("Minimum", min_value=0, step=1, format="%g",
                                                         help="Alert when the count is at or below this."),
                "Location": st.column_config.SelectboxColumn("Location", width="medium", options=places,
                                                             help="Where staff find the item. Add new "
                                                                  "places with Add location above."),
            },
        )
        if st.button("Save changes", type="primary", key="save_minimums") and not needs_initials():
            changed = []
            for (_, row), (_, before) in zip(edited.iterrows(), table.iterrows()):
                update = {}
                if clean_min(row["Minimum"]) != clean_min(before["Minimum"]):
                    minimum = clean_min(row["Minimum"])
                    update["Reorder at"] = minimum if minimum else ""
                after_place = "" if pd.isna(row["Location"]) else str(row["Location"]).strip()
                before_place = "" if pd.isna(before["Location"]) else str(before["Location"]).strip()
                if after_place != before_place:
                    update["Location"] = after_place
                if update:
                    changed.append((row["Item ID"], update))
            if not changed:
                st.info("Nothing changed.")
            else:
                for item_id, update in changed:
                    sheet.update_item(item_id, update, user)
                st.session_state.pop("minimum_table", None)
                flash(f"Saved changes to {len(changed)} item{'s' if len(changed) != 1 else ''} ({user}).")


@st.fragment(run_every=REFRESH_SECONDS)
def meter_list() -> None:
    items = current_items()
    rows = stock_rows(items)
    counts = {name: sum(1 for r in rows if r.state in states) for name, states in FILTERS.items()}
    f1, f2, f3 = st.columns([2.5, 1.1, 1.3], vertical_alignment="center")
    with f1:
        picked = st.pills("Show", [n for n in FILTERS if n == "All" or counts[n]], default="All",
                          key="meter_filter", label_visibility="collapsed",
                          format_func=lambda n: f"{n} {counts[n]}")
    by = f2.segmented_control("Group by", ["Category", "Location"], default="Category", key="meter_group",
                              label_visibility="collapsed") or "Category"
    if by == "Category":
        group_order = list(dict.fromkeys(i["Category"] for i in items if i.get("Category")))
        chosen = f3.selectbox("Category", ["All categories"] + group_order, key="meter_category",
                              label_visibility="collapsed")
        keep = lambda r: chosen == "All categories" or r.category == chosen  # noqa: E731
    else:
        group_order = sorted({r.location for r in rows if r.location}, key=str.lower)
        options = ["All locations"] + group_order + ([NO_LOCATION] if any(not r.location for r in rows) else [])
        chosen = f3.selectbox("Location", options, key="meter_location", label_visibility="collapsed")
        keep = lambda r: chosen == "All locations" or (r.location or NO_LOCATION) == chosen  # noqa: E731
    states = FILTERS.get(picked or "All", FILTERS["All"])
    shown = [r for r in rows if r.state in states and keep(r)]
    if shown:
        st.markdown(groups_html(shown, group_order, by.lower()), unsafe_allow_html=True)
        st.markdown(
            '<p class="list-foot">The magenta bar shows stock on hand against the full-stock level, or '
            "against twice the minimum when no full-stock level is set. The dark mark is the minimum. "
            f"Numbers update from the sheet every {REFRESH_SECONDS} seconds.</p>", unsafe_allow_html=True)
    else:
        st.caption("No items match this filter.")


# ---- Order list
def go_to_order() -> None:
    st.session_state.view = "Order"


def order_excel(table: pd.DataFrame, who: str) -> bytes | None:
    """The order list as an .xlsx file, or None when the Excel writer is not installed."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return None
    wb = Workbook()
    ws = wb.active
    ws.title = "Order list"
    ws["A1"] = f"{APP_TITLE}: order list"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = CENTER_NAME
    ws["A3"] = f"Prepared {datetime.now(ic.TIMEZONE):%Y-%m-%d %H:%M}" + (f" by {who}" if who else "")
    ws["A2"].font = ws["A3"].font = Font(color="5B6474")
    header_row = 5
    for col, name in enumerate(table.columns, 1):
        cell = ws.cell(row=header_row, column=col, value=name)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F2F4F7")
        cell.alignment = Alignment(vertical="center")
    for r_i, row in enumerate(table.itertuples(index=False), header_row + 1):
        for c_i, value in enumerate(row, 1):
            ws.cell(row=r_i, column=c_i, value=None if pd.isna(value) else value)
    widths = {"Item": 46, "Cat. No.": 14, "Unit": 10, "On hand": 10, "Minimum": 10, "Order qty": 11,
              "Location": 26, "Notes": 30}
    for col, name in enumerate(table.columns, 1):
        ws.column_dimensions[get_column_letter(col)].width = widths.get(name, 14)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def order_view(items: list[dict]) -> None:
    st.subheader("Order list")
    st.caption("Items at or below their minimum are ticked, with a suggested quantity: up to the full stock "
               "level, or back to twice the minimum. Change any quantity, tick other items you want to add, "
               "then download the list.")
    rows = stock_rows(items)
    rows.sort(key=lambda r: (r.state not in ("out", "low"), r.item.lower()))
    table = pd.DataFrame([{
        "Order": r.state in ("out", "low"), "Item ID": r.item_id, "Item": r.item, "Cat. No.": r.cat_no,
        "Unit": r.unit, "On hand": "" if r.on_hand is None else fmt(r.on_hand),
        "Minimum": "" if r.minimum is None else fmt(r.minimum), "Order qty": r.suggested,
        "Location": r.location, "Notes": "",
    } for r in rows])
    table["Order qty"] = pd.to_numeric(table["Order qty"], errors="coerce").astype(float)
    edited = st.data_editor(
        table, key="order_table", hide_index=True, width="stretch", num_rows="fixed",
        column_order=["Order", "Item", "Order qty", "Unit", "On hand", "Minimum", "Cat. No.", "Location", "Notes"],
        disabled=["Item", "Cat. No.", "Unit", "On hand", "Minimum", "Location"],
        column_config={
            "Order": st.column_config.CheckboxColumn("Order", width="small"),
            "Item ID": None,
            "Item": st.column_config.TextColumn("Item", width="medium"),
            "Order qty": st.column_config.NumberColumn("Order qty", min_value=0, step=1, format="%g",
                                                       help="How many units to order."),
            "Notes": st.column_config.TextColumn("Notes", help="Vendor, pack size or anything for the buyer."),
        },
    )
    chosen = edited[edited["Order"] & edited["Order qty"].fillna(0).gt(0)]
    missing_qty = edited[edited["Order"] & edited["Order qty"].fillna(0).le(0)]
    if not missing_qty.empty:
        st.warning("Enter an order quantity for: " + ", ".join(missing_qty["Item"]) + ".")
    if chosen.empty:
        st.info("Tick at least one item and give it an order quantity to download the list.")
        return
    def number(v):  # 1 rather than 1.0 in the files, blank when unknown
        if v is None or pd.isna(v):
            return None
        return int(v) if float(v).is_integer() else float(v)

    by_id = {r.item_id: r for r in rows}
    export = pd.DataFrame([{
        "Item": by_id[row["Item ID"]].item, "Cat. No.": by_id[row["Item ID"]].cat_no,
        "Unit": by_id[row["Item ID"]].unit, "On hand": number(by_id[row["Item ID"]].on_hand),
        "Minimum": number(by_id[row["Item ID"]].minimum), "Order qty": number(row["Order qty"]),
        "Location": by_id[row["Item ID"]].location, "Notes": "" if pd.isna(row["Notes"]) else row["Notes"],
    } for _, row in chosen.iterrows()])
    st.markdown(f"**{len(export)} item{'s' if len(export) != 1 else ''} on the order list.**")
    stamp = datetime.now(ic.TIMEZONE).strftime("%Y-%m-%d")
    d1, d2, d3 = st.columns(3)
    xlsx = order_excel(export, user)
    if xlsx is not None:
        d1.download_button("Download Excel", xlsx, file_name=f"order_list_{stamp}.xlsx", type="primary",
                           icon=":material/download:", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("Download CSV", export.to_csv(index=False), file_name=f"order_list_{stamp}.csv",
                       icon=":material/download:", width="stretch", mime="text/csv")
    if d3.button("Mark these as Ordered", icon=":material/local_shipping:", width="stretch",
                 help="Sets each ticked item's status to Ordered, saved with your initials."):
        if not needs_initials():
            for item_id in chosen["Item ID"]:
                sheet.update_item(item_id, {"Status": "Ordered"}, user)
            st.session_state.pop("order_table", None)
            flash(f"Marked {len(chosen)} item{'s' if len(chosen) != 1 else ''} as Ordered ({user}).")


# ---- Lab map
@st.cache_data(show_spinner=False)
def _map_uri(_modified: float) -> str:
    return "data:image/png;base64," + base64.b64encode(MAP_FILE.read_bytes()).decode()


def map_image() -> str | None:
    return _map_uri(MAP_FILE.stat().st_mtime) if MAP_FILE.exists() else None


PIN_KEY = [("ok", METER, "Has supplies"), ("low", "#b45309", "Something low"), ("out", "#b42318", "Something out"),
           ("empty", "#9aa3af", "Nothing stored yet")]


def place_state(stored: list[Stock]) -> str:
    states = {r.state for r in stored}
    if "out" in states:
        return "out"
    if "low" in states:
        return "low"
    return "ok" if stored else "empty"


def slug(name: str) -> str:
    return "loc-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def place_of(location: str, mains: dict) -> tuple[str, str]:
    """(main place, storage spot label) for an item's Location; the spot is "" when it sits on the place itself."""
    loc = " ".join(str(location or "").split())
    if not loc:
        return "", ""
    if loc.lower() in mains:
        return mains[loc.lower()], ""
    parent = ic.parent_place(loc)
    if parent:
        return parent, ic.spot_label(loc, parent)
    return loc, ""


def map_html(uri: str, pins: list[dict], highlight: str | None = None, moved: tuple | None = None) -> str:
    """The floor plan with one badge per place: the number of supplies stored there (incl. its cabinets
    and drawers), colored by stock state. Hover shows the name; a click jumps to the place's card."""
    marks = []
    for p in pins:
        x, y = moved if moved and p["name"] == highlight else (p["x"], p["y"])
        if x is None or y is None:
            continue
        n = p["count"]
        tip = f"{p['name']}: " + (f"{n} suppl{'y' if n == 1 else 'ies'}" if n else "nothing stored yet")
        tip += f", {p['low']} low or out" if p["low"] else ""
        cls = f"mpin {p['state']}" + ((" sel" if p["name"] == highlight else " dim") if highlight else "")
        marks.append(f'<a class="{cls}" href="#{slug(p["name"])}" style="left:{x}%;top:{y}%;" '
                     f'title="{html.escape(tip)}" aria-label="{html.escape(tip)}">{n or ""}</a>')
    return (f'<div class="map-scroll"><div class="map-wrap"><img src="{uri}" alt="Lab floor plan">'
            f'{"".join(marks)}</div></div>')


def item_line(r: Stock) -> str:
    qty = "not counted" if r.on_hand is None else f"{fmt(r.on_hand)} {plural(r.unit, r.on_hand)}"
    flag = pill(r.state) if r.state in ("out", "low") else ""
    return f'<li><span>{html.escape(r.item)}</span><span class="qty">{html.escape(qty)} {flag}</span></li>'


def place_card(p: dict, show_empty_spots: bool) -> str:
    """One card: the place, its note, then each storage spot (cabinet, drawer, shelf) with what is in it."""
    badge = f'<span class="mpin badge {p["state"]}">{p["count"] or ""}</span>'
    note = f'<div class="loc-note">{html.escape(p["note"])}</div>' if p.get("note") else ""
    where = "" if p["x"] is not None else '<div class="loc-empty">Not on the map.</div>'
    groups = []
    loose = sorted(p["spots"].get("", []), key=lambda r: r.item.lower())
    if loose:
        label = '<div class="spot">On the place itself</div>' if len(p["spots"]) > 1 else ""
        groups.append(f'{label}<ul class="loc-items">{"".join(item_line(r) for r in loose)}</ul>')
    for spot in p["spot_order"]:
        here = sorted(p["spots"].get(spot, []), key=lambda r: r.item.lower())
        if not here and not show_empty_spots:
            continue
        body = (f'<ul class="loc-items">{"".join(item_line(r) for r in here)}</ul>' if here
                else '<div class="loc-empty small">Empty</div>')
        groups.append(f'<div class="spot">{html.escape(spot)}</div>{body}')
    if not groups:
        groups.append('<div class="loc-empty">No supplies stored here yet.</div>')
    return (f'<div class="loc-card" id="{slug(p["name"])}"><div class="loc-head">{badge}'
            f'<div class="loc-name">{html.escape(p["name"])}<span class="loc-count">{p["count"]}</span></div></div>'
            f'{note}{where}{"".join(groups)}</div>')


def build_places(details: list[dict], rows: list[Stock]) -> tuple[list[dict], dict]:
    """Main places (with their storage spots and the supplies in each), and a lower-case name -> place lookup."""
    mains: dict[str, str] = {}
    for d in details:
        if not ic.parent_place(d["name"]):
            mains[d["name"].lower()] = d["name"]
    places = {d["name"]: {**d, "spots": {}, "spot_order": [], "count": 0, "low": 0}
              for d in details if d["name"].lower() in mains}
    for d in details:  # storage spots in list order, so cabinets and drawers read in number order
        parent = ic.parent_place(d["name"])
        if parent and parent in places:
            places[parent]["spot_order"].append(ic.spot_label(d["name"], parent))
    for r in rows:
        if not r.location:
            continue
        main, spot = place_of(r.location, mains)
        if main not in places:  # a place typed on an item that is not on the location list
            places[main] = {"name": main, "x": None, "y": None, "note": "", "preset": False, "saved": False,
                            "spots": {}, "spot_order": [], "count": 0, "low": 0}
        p = places[main]
        p["spots"].setdefault(spot, []).append(r)
        if spot and spot not in p["spot_order"]:
            p["spot_order"].append(spot)
        p["count"] += 1
        p["low"] += r.state in ("out", "low")
    for p in places.values():
        p["state"] = place_state([r for group in p["spots"].values() for r in group])
    return list(places.values()), mains


def map_view(items: list[dict]) -> None:
    st.subheader("Lab map")
    details = sheet.location_details()
    rows = stock_rows(items)
    places, mains = build_places(details, rows)
    by_name = {p["name"]: p for p in places}
    renamed, moved_pins = ((sheet.renamed_places_in_use(items), sheet.saved_pin_positions()) if demo
                           else load_map_checks(sheet))
    if renamed["items"] or renamed["places"]:
        r1, r2 = st.columns([3, 1.4], vertical_alignment="center")
        r1.info(f"Storage places were renamed on the new floor plan (e.g. Delivery desk → Desk #1, "
                f"Lab bench #5, QC → Bench #5, and the supply cabinets are now numbered 1-20). {renamed['items']} item{'s' if renamed['items'] != 1 else ''} and "
                f"{renamed['places']} saved place{'s' if renamed['places'] != 1 else ''} still use an old name.")
        if r2.button("Update to the new names", icon=":material/drive_file_rename_outline:", width="stretch",
                     key="map_rename") and not needs_initials():
            try:
                done = sheet.migrate_renamed_places(user)
                flash(f"Moved {done['items']} item{'s' if done['items'] != 1 else ''} to the new place names ({user}).")
            except ic.InventoryError as exc:
                st.error(str(exc))

    missing = [i for i in items if not str(i.get("Location", "")).strip() and i["Item"] in SUGGESTED_PLACES]
    if missing:
        m1, m2 = st.columns([3, 1.4], vertical_alignment="center")
        m1.info(f"{len(missing)} item{'s have' if len(missing) != 1 else ' has'} no location yet. Fill in the "
                "suggested place for each; you can change any of them below.")
        if m2.button("Fill in suggested locations", icon=":material/auto_fix_high:", width="stretch") \
                and not needs_initials():
            for i in missing:
                sheet.update_item(i["Item ID"], {"Location": SUGGESTED_PLACES[i["Item"]]}, user)
            flash(f"Filled in locations for {len(missing)} item{'s' if len(missing) != 1 else ''} ({user}).")

    # ---- find a supply: the answer new staff need most
    by_id = {r.item_id: r for r in rows}
    pick = st.selectbox("Find a supply", sorted(by_id, key=lambda i: by_id[i].item.lower()), index=None,
                        key="map_find", placeholder="Type a supply name to see where it is kept",
                        format_func=lambda i: by_id[i].item)
    highlight = None
    if pick:
        r = by_id[pick]
        main, spot = place_of(r.location, mains)
        qty = "not counted" if r.on_hand is None else f"{fmt(r.on_hand)} {plural(r.unit, r.on_hand)}"
        if not main:
            st.warning(f"**{r.item}** has no location yet. Set it under **Edit a location** below.")
        else:
            room = ic.ROOM_OF.get(main.lower(), "")
            trail = " › ".join(html.escape(t) for t in (room, main, spot) if t)
            on_map = by_name.get(main, {}).get("x") is not None
            st.markdown(f'<div class="find-box">{PIN}<div><div class="find-item">{html.escape(r.item)}'
                        f'<span>{html.escape(qty)}</span></div><div class="find-trail">{trail}</div>'
                        + ("" if on_map else '<div class="find-note">This place is not drawn on the map.</div>')
                        + '</div></div>', unsafe_allow_html=True)
            highlight = main if on_map else None

    uri = map_image()
    if uri:
        st.markdown(map_html(uri, places, highlight), unsafe_allow_html=True)
        st.markdown('<div class="map-key">' + "".join(f'<span><i style="background:{c};"></i>{t}</span>'
                                                      for _, c, t in PIN_KEY)
                    + "<span>The number is how many supplies are kept there. Tap a pin to see which cabinet "
                      "or drawer.</span></div>", unsafe_allow_html=True)
    else:
        st.info("The map picture is missing. Put lab_map.jpg in the same folder as app.py.")

    unplaced = [r for r in rows if not r.location]
    shown = st.segmented_control("Show", ["Places with supplies", "All places and empty spots"],
                                 default="Places with supplies", key="map_show",
                                 label_visibility="collapsed") or "Places with supplies"
    show_all = shown != "Places with supplies"
    sections = [(room, [by_name[n] for n in names if n in by_name]) for room, names in ic.ROOMS.items()]
    listed = {n.lower() for names in ic.ROOMS.values() for n in names}
    sections.append(("Other places", [p for p in places if p["name"].lower() not in listed]))
    for room, group in sections:
        cards = [p for p in group if show_all or p["count"]]
        if not cards:
            continue
        st.markdown(f'<div class="room-head">{html.escape(room)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="loc-grid">{"".join(place_card(p, show_all) for p in cards)}</div>',
                    unsafe_allow_html=True)
    if unplaced:
        names = ", ".join(html.escape(r.item) for r in unplaced)
        st.markdown(f'<p class="list-foot">No location set: {names}.</p>', unsafe_allow_html=True)

    with st.expander("Edit a location", icon=":material/edit_location_alt:"):
        all_names = [d["name"] for d in details] + [p["name"] for p in places if p["name"] not in
                                                    {d["name"] for d in details}]
        detail_of = {d["name"]: d for d in details}

        def label(n: str) -> str:
            parent = ic.parent_place(n)
            if parent:
                return f"{n}  (in {parent})"
            return n if by_name.get(n, {}).get("x") is not None else f"{n}  (not on the map)"

        pick = st.selectbox("Location", all_names, key="map_pick", format_func=label)
        d = detail_of.get(pick) or {"name": pick, "x": None, "y": None, "note": "", "preset": False, "saved": False}
        parent = ic.parent_place(pick)
        note = st.text_area("Note", value=d.get("note", ""), key=f"map_note_{pick}",
                            placeholder="e.g. Top shelf: tip boxes. Bottom shelf: spare cases.")
        loc_of = {i["Item ID"]: str(i.get("Location", "")).strip() for i in items}
        current = [i["Item ID"] for i in items if loc_of[i["Item ID"]].lower() == pick.lower()]
        ordered = sorted(items, key=lambda i: (loc_of[i["Item ID"]].lower() != pick.lower(),
                                               bool(loc_of[i["Item ID"]]), i["Item"].lower()))
        st.markdown("**Supplies stored here**")
        st.caption("Tick the supplies kept in this place. Ticking one that is stored elsewhere moves it here; "
                   "unticking one leaves it with no location.")
        picks = st.data_editor(
            pd.DataFrame([{"Here": loc_of[i["Item ID"]].lower() == pick.lower(), "Item ID": i["Item ID"],
                           "Item": i["Item"], "Now in": loc_of[i["Item ID"]] or "No location"} for i in ordered]),
            key=f"map_items_{pick}", hide_index=True, width="stretch", num_rows="fixed", height=280,
            disabled=["Item", "Now in"],
            column_config={"Here": st.column_config.CheckboxColumn("Here", width="small"), "Item ID": None,
                           "Item": st.column_config.TextColumn("Item", width="large")},
        )
        chosen = list(picks.loc[picks["Here"], "Item ID"])
        x = y = None
        if parent:
            st.caption(f"Cabinets, drawers and shelves have no pin of their own: they are listed in the "
                       f"**{parent}** card and found through its pin.")
        else:
            on_map = st.toggle("Show on the map", value=d["x"] is not None, key=f"map_on_{pick}")
            if on_map:
                c1, c2 = st.columns(2)
                x = c1.slider("Across (left to right)", 0.0, 100.0, float(d["x"] if d["x"] is not None else 50.0),
                              0.5, key=f"map_x_{pick}")
                y = c2.slider("Down (top to bottom)", 0.0, 100.0, float(d["y"] if d["y"] is not None else 50.0),
                              0.5, key=f"map_y_{pick}")
                st.caption("Put the pin in a free corner of the box so the name on the plan stays readable.")
                if uri:
                    preview = places if pick in by_name else places + [{**d, "count": 0, "low": 0, "state": "empty"}]
                    st.markdown(map_html(uri, preview, highlight=pick, moved=(x, y)), unsafe_allow_html=True)
        if st.button("Save location", type="primary", key="map_save", icon=":material/save:") and not needs_initials():
            try:
                if not d.get("preset") and not d.get("saved"):
                    sheet.add_location(pick, user)
                if parent:
                    x, y = d["x"], d["y"]  # storage spots keep whatever is saved; they are not drawn
                if (d["x"], d["y"]) != (x, y) or (d.get("note") or "") != note.strip():
                    sheet.update_location(pick, user, x, y, note)
                for item_id in set(chosen) - set(current):
                    sheet.update_item(item_id, {"Location": pick}, user)
                for item_id in set(current) - set(chosen):
                    sheet.update_item(item_id, {"Location": ""}, user)
                flash(f"Saved {pick} ({user}).")
            except ic.InventoryError as exc:
                st.error(str(exc))
        if moved_pins:
            st.divider()
            st.caption(f"{len(moved_pins)} built-in place{'s have' if len(moved_pins) != 1 else ' has'} a pin moved or "
                       "hidden by hand. If pins no longer sit on the right spot after a new floor plan, put them back "
                       "on their floor plan positions (notes and stored supplies are kept).")
            if st.button("Reset built-in pins to the floor plan", icon=":material/restart_alt:",
                         key="map_reset_pins") and not needs_initials():
                try:
                    n = sheet.reset_preset_pins(user)
                    flash(f"Reset {n} pin{'s' if n != 1 else ''} to the floor plan ({user}).")
                except ic.InventoryError as exc:
                    st.error(str(exc))
        st.divider()
        a1, a2 = st.columns([3, 1], vertical_alignment="bottom")
        a1.text_input("Add a new location", key="map_new_location", placeholder="e.g. Cold room, shelf 2",
                      help="Adds it to the location list for everyone; then pick it above to place it on the map.")
        a2.button("Add location", icon=":material/add_location_alt:", width="stretch", key="map_add_location",
                  on_click=add_location_clicked, args=("map_new_location",))
        if "location_error" in st.session_state:
            st.error(st.session_state.pop("location_error"))


# ---- Inventory table (re-reads the sheet on its own)
@st.fragment(run_every=REFRESH_SECONDS)
def inventory_view() -> None:
    items = current_items()
    if not items:
        st.caption("No items yet.")
        return
    df = pd.DataFrame(items)
    s1, s2, s3 = st.columns([2, 1, 1])
    query = s1.text_input("Search items", placeholder="Item name, catalog number or location", key="inv_query")
    cat_filter = s2.selectbox("Category", ["All"] + sorted(df["Category"].replace("", pd.NA).dropna().unique()),
                              key="inv_cat")
    status_filter = s3.selectbox("Status", ["All"] + ic.STATUS_OPTIONS, key="inv_status")
    if query:
        df = df[df["Item"].str.contains(query, case=False, regex=False)
                | df["Cat. No."].str.contains(query, case=False, regex=False)
                | df["Location"].astype(str).str.contains(query, case=False, regex=False)]
    if cat_filter != "All":
        df = df[df["Category"] == cat_filter]
    if status_filter != "All":
        df = df[df["Status"] == status_filter]
    df = df.drop(columns=["Per sample", "Per run"], errors="ignore").rename(
        columns={"Reorder at": "Minimum", "Target": "Full stock"})
    if not st.toggle("Show all columns", key="inv_all"):
        df = df[["Item", "On hand", "Unit", "Minimum", "Location", "Status", "Checked by", "Last checked"]]
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Download inventory (CSV)", pd.DataFrame(items).to_csv(index=False),
                       file_name="coe_lab_inventory.csv", mime="text/csv")


if view == "Meter":
    meter_summary()
    if items:
        st.button("Make an order list", icon=":material/shopping_cart:", on_click=go_to_order,
                  key="to_order", help="Opens the Order page with low-stock items already ticked.")
        minimum_editor(items)
    meter_list()

elif view == "Order":
    if items:
        order_view(items)

elif view == "Map":
    map_view(items)

elif view == "Receive":
    st.subheader("Receive supplies")
    mode = st.segmented_control("Item", ["On the list", "New item, not on the list"],
                                default="On the list", key="receive_mode", label_visibility="collapsed")
    if mode == "New item, not on the list":
        st.caption("Adds the item to the inventory with the quantity you received.")
        categories = sorted({i["Category"] for i in items if i["Category"]})
        with st.form("receive_new", clear_on_submit=True):
            name = st.text_input("Item name *", placeholder="e.g. Filter tips, 10 uL")
            n1, n2 = st.columns(2)
            qty = n1.number_input("Quantity received *", min_value=0.0, step=1.0)
            unit = n2.text_input("Unit *", placeholder="e.g. box, tip, kit")
            n3, n4 = st.columns(2)
            category = n3.selectbox("Category", categories + ["Other"])
            cat_no = n4.text_input("Cat. No.")
            location = st.selectbox("Location", location_options(items), index=None, accept_new_options=True,
                                    placeholder="Choose, or type a new location")
            submitted = st.form_submit_button("Add item and quantity", type="primary", width="stretch")
        if submitted and not needs_initials():
            if not unit.strip():
                st.error("Enter the unit, for example box or kit.")
            elif qty <= 0:
                st.error("Enter the quantity received.")
            else:
                try:
                    location = remember_location(location)
                    new_id = sheet.add_item({"Item": name, "Unit": unit, "On hand": qty,
                                             "Category": "" if category == "Other" else category,
                                             "Cat. No.": cat_no, "Location": location}, user)
                    flash(f"Added {name.strip()} ({new_id}) with {fmt(qty)} {plural(unit.strip(), qty)} "
                          f"received by {user}. Set its minimum under Meter, Set minimums and locations.")
                except ic.InventoryError as exc:
                    st.error(str(exc))
    elif items:
        current = item_picker(items, key="receive_item")
        show_location(current)
        st.metric("On hand now", on_hand_text(current))
        with st.form("receive_form", clear_on_submit=True):
            qty = st.number_input(f"Quantity received ({current['Unit'] or 'units'})", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Save received", type="primary", width="stretch")
        if submitted and not needs_initials():
            try:
                updated = sheet.adjust_on_hand(current["Item ID"], qty, 0, user)
                flash(f"Received {fmt(qty)}: {updated['Item']} is now {on_hand_text(updated)} "
                      f"(saved by {user}).")
            except ic.InventoryError as exc:
                st.error(str(exc))

elif view == "Use":
    st.subheader("Record supplies used")
    if items:
        current = item_picker(items, key="use_item")
        show_location(current)
        st.metric("On hand now", on_hand_text(current))
        with st.form("use_form", clear_on_submit=True):
            qty = st.number_input(f"Quantity used ({current['Unit'] or 'units'})", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Save used", type="primary", width="stretch")
        if submitted and not needs_initials():
            try:
                updated = sheet.adjust_on_hand(current["Item ID"], 0, qty, user)
                flash(f"Used {fmt(qty)}: {updated['Item']} is now {on_hand_text(updated)} "
                      f"({updated['Status']}, saved by {user}).")
            except ic.InventoryError as exc:
                st.error(str(exc))

elif view == "Count":
    st.subheader("Shelf check")
    if items:
        current = item_picker(items, key="count_item")
        show_location(current)
        st.metric("On hand in the app", on_hand_text(current),
                  help=f"Last checked {current['Last checked'] or 'never'} by {current['Checked by'] or '-'}")
        with st.form("count_form"):
            counted = st.number_input("Counted on the shelf", min_value=0.0, step=1.0,
                                      value=float(ic.to_number(current["On hand"]) or 0))
            submitted = st.form_submit_button("Save shelf count", type="primary", width="stretch")
        if submitted and not needs_initials():
            try:
                updated = sheet.update_item(current["Item ID"], {"On hand": counted}, user, reason="shelf count")
                flash(f"{updated['Item']}: shelf count {on_hand_text(updated)} saved by {user}.")
            except ic.InventoryError as exc:
                st.error(str(exc))
        b1, b2 = st.columns(2)
        if b1.button("Count is correct", width="stretch",
                     help="Records your initials and today's date as the last check, without changing the count."):
            if not needs_initials():
                sheet.update_item(current["Item ID"], {}, user)
                flash(f"{current['Item']}: check recorded by {user}.")
        if b2.button("Mark as ordered", width="stretch", disabled=current["Status"] == "Ordered"):
            if not needs_initials():
                sheet.update_item(current["Item ID"], {"Status": "Ordered"}, user)
                flash(f"{current['Item']} marked as Ordered by {user}.")

elif view == "Items":
    inventory_view()

elif view == "Edit":
    st.subheader("Edit item details")
    if items:
        current = item_picker(items, key="edit_item")
        st.caption(f"Last checked {current['Last checked'] or 'never'} by {current['Checked by'] or '-'}. "
                   "Change quantities under Receive, Use or Count.")
        with st.form("edit_form"):
            name = st.text_input("Item name", value=current["Item"])
            c1, c2 = st.columns(2)
            unit = c1.text_input("Unit", value=current["Unit"])
            category = c2.text_input("Category", value=current["Category"])
            c3, c4 = st.columns(2)
            new_reorder = c3.number_input("Minimum (alert at or below)", min_value=0.0, step=1.0,
                                          value=float(ic.to_number(current["Reorder at"]) or 0),
                                          help="0 means no low-stock alert for this item.")
            new_target = c4.number_input("Full stock level (optional)", min_value=0.0, step=1.0,
                                         value=float(ic.to_number(current["Target"]) or 0),
                                         help="How much you keep when fully stocked. Sets the bar length "
                                              "and the suggested order.")
            d1, d2 = st.columns(2)
            places = location_options(items)
            here = str(current["Location"]).strip()
            new_location = d1.selectbox("Location", places, index=places.index(here) if here in places else None,
                                        accept_new_options=True, placeholder="Choose, or type a new location")
            new_cat = d2.text_input("Cat. No.", value=current["Cat. No."])
            status_choice = st.selectbox("Status", ["Automatic"] + ic.STATUS_OPTIONS,
                                         help="Automatic sets In stock, Low or Out of stock from the count.")
            new_notes = st.text_area("Notes", value=current["Notes"])
            submitted = st.form_submit_button("Save details", type="primary", width="stretch")
        if submitted and not needs_initials():
            new_location = remember_location(new_location)
            proposed = {
                "Item": name, "Unit": unit, "Category": category, "Reorder at": new_reorder or "",
                "Location": new_location, "Cat. No.": new_cat, "Notes": new_notes,
                "Target": new_target or "",
            }
            changes = {}
            for field, value in proposed.items():
                old = current[field]
                if field in ic.NUMERIC_FIELDS:
                    if ic.to_number(old) != (ic.to_number(value) if value != "" else None):
                        changes[field] = value
                elif str(old).strip() != str(value).strip():
                    changes[field] = value
            if status_choice != "Automatic":
                changes["Status"] = status_choice
            try:
                updated = sheet.update_item(current["Item ID"], changes, user)
                flash(f"Saved {updated['Item']} (status {updated['Status'] or 'not set'}) by {user}.")
            except ic.InventoryError as exc:
                st.error(str(exc))

elif view == "Log":
    st.subheader("Who did what, and when")
    log = sheet.changes(limit=5000)
    if not log:
        st.caption("No changes recorded yet.")
    else:
        log_df = pd.DataFrame(log)
        log_df["Date"] = pd.to_datetime(log_df["Timestamp"].str[:10], errors="coerce").dt.date
        l1, l2, l3 = st.columns([1, 2, 2])
        staff = sorted(u for u in log_df["User"].unique() if u)
        who = l1.selectbox("Staff", ["Everyone"] + staff, key="log_user")
        dates = log_df["Date"].dropna()
        picked = l2.date_input("Dates", value=(dates.min(), dates.max()) if len(dates) else (), key="log_dates")
        find = l3.text_input("Item", placeholder="Search item name", key="log_item")
        shown = log_df
        if who != "Everyone":
            shown = shown[shown["User"] == who]
        if isinstance(picked, (list, tuple)) and len(picked) == 2:
            shown = shown[(shown["Date"] >= picked[0]) & (shown["Date"] <= picked[1])]
        if find:
            shown = shown[shown["Item"].str.contains(find, case=False, regex=False)]
        received = shown["Field"].str.contains("received", regex=False).sum()
        used = shown["Field"].str.contains("used", regex=False).sum()
        checks = shown["Field"].str.startswith(("(checked)", "On hand (shelf count)")).sum()
        st.caption(f"{len(shown)} entries · {received} receipts · {used} uses · {checks} shelf checks")
        st.dataframe(shown.drop(columns=["Date"]), hide_index=True, width="stretch")
        st.download_button("Download log (CSV)", shown.drop(columns=["Date"]).to_csv(index=False),
                           file_name="coe_inventory_change_log.csv", mime="text/csv")


# ---- footer
st.divider()
if login_settings() is not None:
    if st.button("Sign out", icon=":material/logout:", key="sign_out"):
        st.session_state.clear()
        st.rerun()
elif not demo:
    st.caption("Sign-in is off. Add a [login] section with username and password to the app's secrets "
               "to require it (see README).")
