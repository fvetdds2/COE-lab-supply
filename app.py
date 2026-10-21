"""COE lab inventory tracker - Streamlit front end for the "COE lab inventory" Google Sheet.

Run locally:   streamlit run app.py
Secrets:       .streamlit/secrets.toml  (see secrets.toml.example and README.md)
No secrets?    The app opens in demo mode with example counts, so you can try it.

Works on phones and computers. Every receive, use, count and edit is saved with the
staff member's initials and the date in the sheet's Change log tab.
"""

from __future__ import annotations

import html
from datetime import datetime

import pandas as pd
import streamlit as st

import inventory_core as ic

st.set_page_config(page_title="COE Lab Inventory", page_icon="🧪", layout="wide",
                   initial_sidebar_state="collapsed")

METER = "#b8237a"  # magenta: meter fill and covered runs (5.9:1 on white)
# Stock states, most urgent first: (label, icon, text color, tint). Each state always shows an
# icon and a word, never color alone. Text colors pass 4.5:1 on their tint.
STATES = {
    "out": ("Out of stock", "✕", "#b42318", "#fde8e8"),
    "low": ("Low stock", "▲", "#8a5300", "#fff3d1"),
    "none": ("Not counted", "ring", "#4b5563", "#eef1f5"),
    "below": ("Below target", "half", "#33507a", "#e6edf7"),
    "ok": ("Stocked", "✓", "#17692a", "#e3f4e6"),
}
STATE_ORDER = list(STATES)
FILTERS = {  # status filter above the item list -> states it shows
    "All": set(STATES),
    "Needs action": {"out", "low"},
    "Not counted": {"none"},
    "Below target": {"below"},
    "Stocked": {"ok"},
}
REFRESH_SECONDS = 30  # how often the meter and inventory re-read the sheet

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

@st.cache_resource(show_spinner="Connecting to Google Sheets...")
def live_sheet(sheet_url: str, account: tuple) -> ic.InventorySheet:
    return ic.connect_service_account(sheet_url, info=dict(account))


def demo_sheet() -> ic.InventorySheet:
    if "demo_sheet" not in st.session_state:
        sheet = ic.InventorySheet(ic.MemorySpreadsheet())
        sheet.seed_starter_items("demo")
        for item in sheet.items():
            if item["Item"] in DEMO_COUNTS:
                sheet.update_item(item["Item ID"], {"On hand": DEMO_COUNTS[item["Item"]]}, "demo")
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
    problem = secrets_problem()
    if problem:
        return demo_sheet(), problem
    account = tuple(sorted(dict(st.secrets["gcp_service_account"]).items()))
    try:
        return live_sheet(st.secrets["sheet_url"], account), ""
    except Exception as exc:  # shown on the page instead of a traceback; retried on reload
        st.title("COE Lab Inventory")
        st.error(connection_help(exc))
        st.stop()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def load_items(_sheet: ic.InventorySheet) -> list[dict]:
    return _sheet.items()


def refresh() -> None:
    load_items.clear()  # every session re-reads the sheet after a write


# --------------------------------------------------------------------------- helpers

def plural(unit: str, amount: float) -> str:
    if amount == 1 or not unit or unit.endswith("s") or unit in ("L", "mL", "uL", "kg", "g"):
        return unit
    return unit + ("es" if unit.endswith(("x", "ch", "sh")) else "s")


def fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def stock_state(row: ic.MeterRow, reorder_at: float | None, counted: bool) -> str:
    if not counted:
        return "none"
    if row.on_hand <= 0:
        return "out"
    if row.fraction >= 1:
        return "ok"
    if reorder_at is not None and row.on_hand <= reorder_at:
        return "low"
    return "below"


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
  max-width: 1040px; padding-top: 2rem; padding-bottom: 4rem;
}
.num { font-variant-numeric: tabular-nums; }

/* header */
.app-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
            margin-bottom: 4px; }
.app-title { font-size: 30px; line-height: 1.15; font-weight: 700; color: var(--ink); margin: 0; }
.app-sub { color: var(--muted); font-size: 15px; margin: 4px 0 0; }
.conn { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600;
        color: var(--muted); white-space: nowrap; padding-top: 8px; }
.conn i { width: 8px; height: 8px; border-radius: 50%; background: #17a34a; display: inline-block; }
.conn.demo i { background: #e0a100; }

/* hero: one plate per KingFisher run */
.hero { background: var(--card); border: 1px solid var(--line); border-radius: 16px;
        padding: 24px 26px 20px; margin: 4px 0 18px; display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr); grid-template-areas: "main notes" "plates plates";
        gap: 20px 40px; }
.hero-main { grid-area: main; }
.hero-notes { grid-area: notes; display: flex; flex-direction: column; gap: 8px; justify-content: center;
              font-size: 15px; line-height: 1.45; color: var(--ink); }
.hero-plates { grid-area: plates; }
.hero-big { font-size: 22px; color: var(--muted); line-height: 1.1; }
.hero-big b { font-size: 60px; font-weight: 700; color: var(--ink); letter-spacing: -1.5px; margin-right: 8px; }
.hero-sub { font-size: 16px; color: var(--ink); margin-top: 10px; line-height: 1.45; max-width: 42ch; }
.hero-notes .warn { color: #8a5300; font-weight: 600; }
.plates { display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 7px; }
.plate { aspect-ratio: 3 / 2; border-radius: 4px;
         background:
           radial-gradient(circle, rgba(255,255,255,0.45) 0 1.1px, transparent 1.4px) 0 0 / calc(100% / 12) calc(100% / 8),
           linear-gradient(90deg, var(--magenta) var(--f), var(--track) var(--f)); }
.plate-key { display: flex; flex-wrap: wrap; gap: 6px 20px; font-size: 13px; color: var(--muted); margin-top: 12px; }
.plate-key span { display: inline-flex; align-items: center; gap: 6px; }
.plate-key i { width: 18px; height: 12px; border-radius: 3px; display: inline-block; }

/* status pills */
.pill { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px 3px 8px;
        border-radius: 999px; font-size: 13px; font-weight: 600; white-space: nowrap; }
.pill b { font-size: 11px; width: 14px; display: inline-flex; justify-content: center; }
.ico-ring, .ico-half { width: 10px; height: 10px; border-radius: 50%; border: 1.6px solid currentColor;
                       box-sizing: border-box; display: inline-block; }
.ico-half { background: linear-gradient(90deg, currentColor 50%, transparent 50%); }

/* item list, grouped by category */
.group { margin: 22px 0 0; }
.group-title { font-size: 15px; font-weight: 700; color: var(--ink); margin: 0 0 8px 2px; }
.group-title span { color: var(--muted); font-weight: 400; margin-left: 6px; }
.group-list { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
              padding: 2px 20px; }
.item { padding: 14px 0 13px; }
.item + .item { border-top: 1px solid var(--line); }
.item-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.item-name { font-size: 16px; font-weight: 600; color: var(--ink); line-height: 1.3; }
.bar { position: relative; height: 10px; border-radius: 5px; background: var(--track); margin: 10px 0 8px; }
.bar.unknown { background: repeating-linear-gradient(135deg, #eef1f5 0 6px, #e2e6ec 6px 12px); }
.bar .fill { height: 100%; border-radius: 5px; background: var(--magenta); }
.bar .tick { position: absolute; top: -4px; width: 2px; height: 18px; border-radius: 1px;
             background: var(--ink); opacity: 0.7; }
.item-meta { display: flex; flex-wrap: wrap; gap: 4px 20px; font-size: 14px; color: var(--muted); }
.item-meta b { color: var(--ink); font-weight: 700; }
.item-meta .when { margin-left: auto; }
.list-foot { font-size: 13px; color: var(--muted); margin: 14px 2px 0; }

/* Streamlit pieces */
[data-testid="stForm"] { background: var(--card); border-radius: 14px; }
[data-testid="stExpander"] details { background: var(--card); border-radius: 14px; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }

.st-key-meter_filter [role="radiogroup"] { flex-wrap: wrap; overflow: visible; }

@media (max-width: 760px) {
  .block-container, [data-testid="stMainBlockContainer"] { padding: 1.2rem 1rem 3rem; }
  .st-key-topbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px; }
  .st-key-topbar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
  .st-key-topbar [data-testid="stColumn"]:nth-child(1) { flex: 1 1 0 !important; }
  .st-key-topbar [data-testid="stColumn"]:nth-child(2) { flex: 1.35 1 0 !important; }
  .st-key-topbar [data-testid="stColumn"]:nth-child(3) { flex: 0 0 48px !important; }
  .st-key-refresh button p { display: none; }
  .st-key-refresh button { padding-left: 0; padding-right: 0; }
  .st-key-view [role="radiogroup"] { display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr));
                                      gap: 6px; }
  .st-key-view button { border-radius: 999px !important; margin: 0 !important; width: 100%; }
  .app-head { flex-direction: column; gap: 2px; }
  .app-title { font-size: 26px; }
  .conn { padding-top: 2px; }
  .hero { grid-template-columns: 1fr; grid-template-areas: "main" "plates" "notes";
          padding: 18px 16px 16px; gap: 16px; }
  .hero-notes { border-top: 1px solid var(--line); padding-top: 14px; }
  .hero-big b { font-size: 48px; }
  .hero-sub { max-width: none; }
  .plates { grid-template-columns: repeat(var(--cols-sm), minmax(0, 1fr)); gap: 5px; }
  .group-list { padding: 2px 14px; }
  .item-name { font-size: 15px; }
  .item-meta { gap: 2px 14px; font-size: 13px; }
  .item-meta .when { margin-left: 0; width: 100%; }
  button[kind="primary"], button[kind="secondary"] { min-height: 2.75rem; }
}
</style>
"""


def pill(state: str, count: int | None = None) -> str:
    label, icon, ink, tint = STATES[state]
    extra = f" {count}" if count is not None else ""
    mark = f'<i class="ico-{icon}"></i>' if icon in ("ring", "half") else icon
    return (f'<span class="pill" style="color:{ink};background:{tint};">'
            f'<b aria-hidden="true">{mark}</b>{label}{extra}</span>')


def plates_html(covered: int, goal: int) -> str:
    """One small 96-well plate per KingFisher run; the magenta share is what stock covers."""
    runs = ic.runs_needed(goal)
    if runs > 160:  # too many plates to draw; one long plate strip instead
        share = min(covered / goal, 1) if goal else 0
        return (f'<div class="plates" style="--cols:1;--cols-sm:1;"><span class="plate" '
                f'style="--f:{share * 100:.1f}%;aspect-ratio:12/1;"></span></div>')
    tiles = []
    for i in range(runs):
        size = min(ic.SAMPLES_PER_RUN, goal - i * ic.SAMPLES_PER_RUN)
        done = max(0, min(covered - i * ic.SAMPLES_PER_RUN, size))
        tiles.append(f'<span class="plate" style="--f:{done / size * 100:.1f}%;"></span>')
    full_runs = sum(1 for i in range(runs) if covered >= min((i + 1) * ic.SAMPLES_PER_RUN, goal))
    return (f'<div class="plates" style="--cols:{min(runs, 14)};--cols-sm:{min(runs, 7)};" role="img" '
            f'aria-label="{full_runs} of {runs} runs covered">{"".join(tiles)}</div>')


def hero_html(summary: dict, rows: list[ic.MeterRow], info: dict) -> str:
    goal, covered = summary["goal"], summary["covered"]
    runs = ic.runs_needed(goal)
    full_runs = min(covered // ic.SAMPLES_PER_RUN, runs) if covered < goal else runs
    uncounted = [r for r in rows if info[r.item_id][1] == "none"]
    counted = [r for r in rows if info[r.item_id][1] != "none"]

    if not counted:
        sub = "Nothing counted yet. Enter shelf counts under Count to see how many runs your stock covers."
    elif uncounted:
        sub = (f"{len(uncounted)} items are not counted yet, so they count as zero. Enter their counts "
               "under Count to see how far your stock goes.")
    elif covered >= goal:
        sub = f"Enough on the shelf for the full goal of {goal:,} samples."
    else:
        sub = f"Enough on the shelf for {covered:,} of {goal:,} samples."

    notes = []
    first = min(counted, key=lambda r: (r.covered if r.covered is not None else goal, r.fraction),
                default=None)
    if first is not None and first.fraction < 1:
        notes.append(f"Runs out first: <b>{html.escape(first.item)}</b>, {fmt(first.on_hand)} of "
                     f"{fmt(first.needed)} {html.escape(plural(first.unit, first.needed))}.")
    urgent = [r.item for r in rows if info[r.item_id][1] in ("out", "low")]
    if urgent:
        names = ", ".join(html.escape(n) for n in urgent[:4])
        more = f" and {len(urgent) - 4} more" if len(urgent) > 4 else ""
        notes.append(f'<span class="warn">▲ Reorder now: {names}{more}.</span>')
    notes_html = f'<div class="hero-notes">{"".join(f"<div>{n}</div>" for n in notes)}</div>' if notes else ""

    return (
        '<section class="hero">'
        f'<div class="hero-main"><div class="hero-big num"><b>{full_runs}</b>of {runs} runs</div>'
        f'<div class="hero-sub">{sub}</div></div>'
        f"{notes_html}"
        f'<div class="hero-plates">{plates_html(covered, goal)}'
        '<div class="plate-key">'
        f'<span><i style="background:{METER};"></i>Covered by stock</span>'
        '<span><i style="background:var(--track);"></i>Still to stock</span>'
        f'<span>Each plate is one KingFisher run of {ic.SAMPLES_PER_RUN} samples</span></div></div>'
        "</section>"
    )


def item_html(r: ic.MeterRow, reorder: float | None, state: str, when: str, who: str) -> str:
    unit = html.escape(plural(r.unit, r.needed))
    if state == "none":
        bar = '<div class="bar unknown"></div>'
        meta = [f"<span>Need <b class=\"num\">{fmt(r.needed)}</b> {unit}</span>"]
    else:
        tick = ""
        if reorder is not None and r.needed:
            tick = (f'<div class="tick" style="left:calc({min(reorder / r.needed, 1) * 100:.1f}% - 1px);" '
                    'title="Reorder level"></div>')
        bar = (f'<div class="bar" title="{r.fraction:.0%} of target"><div class="fill" '
               f'style="width:{r.fraction * 100:.1f}%;"></div>{tick}</div>')
        meta = [f'<span><b class="num">{fmt(r.on_hand)}</b> of <span class="num">{fmt(r.needed)}</span> {unit}</span>']
        if r.shortfall:
            meta.append(f'<span>Order <span class="num">{fmt(r.shortfall)}</span></span>')
    if reorder is not None:
        meta.append(f'<span>Reorder at <span class="num">{fmt(reorder)}</span></span>')
    if when:
        by = f" by {html.escape(str(who))}" if who else ""
        meta.append(f'<span class="when">Checked {html.escape(short_date(when))}{by}</span>')
    return (f'<div class="item"><div class="item-top"><div class="item-name">{html.escape(r.item)}</div>'
            f'{pill(state)}</div>{bar}<div class="item-meta">{"".join(meta)}</div></div>')


def groups_html(rows: list[ic.MeterRow], info: dict, category_order: list[str]) -> str:
    groups: dict[str, list[ic.MeterRow]] = {}
    for r in rows:
        groups.setdefault(r.category or "Other", []).append(r)
    order = [c for c in category_order if c in groups] + sorted(c for c in groups if c not in category_order)
    parts = []
    for cat in order:
        body = "".join(item_html(r, *info[r.item_id]) for r in groups[cat])
        parts.append(f'<section class="group"><div class="group-title">{html.escape(cat)}'
                     f'<span>{len(groups[cat])}</span></div><div class="group-list">{body}</div></section>')
    return "".join(parts)


# --------------------------------------------------------------------------- page helpers

def flash(message: str) -> None:
    """Re-read the sheet and rerun so every view shows the new numbers, then show the message."""
    st.session_state.flash = message
    refresh()
    st.rerun()


def current_items() -> list[dict]:
    return sheet.items() if demo else load_items(sheet)  # demo data lives in this session only


def item_picker(items: list[dict], key: str, label: str = "Item") -> dict:
    by_id = {i["Item ID"]: i for i in items}
    chosen = st.selectbox(label, list(by_id), key=key,
                          format_func=lambda i: f"{by_id[i]['Item']} ({i})")
    return by_id[chosen]


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

sheet, demo_reason = get_sheet()
demo = bool(demo_reason)
st.markdown(PAGE_CSS, unsafe_allow_html=True)
connection = ('<span class="conn demo"><i></i>Demo data</span>' if demo
              else '<span class="conn"><i></i>Live from Google Sheets</span>')
st.markdown(
    '<header class="app-head"><div>'
    '<div class="app-title" role="heading" aria-level="1">COE Lab Inventory</div>'
    '<p class="app-sub">Supplies for whole-blood DNA extraction on the KingFisher Apex</p>'
    f"</div>{connection}</header>",
    unsafe_allow_html=True,
)
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"), icon=":material/check_circle:")
if demo:
    st.info("Demo mode: example counts, not your inventory.\n\n**Why:** " + demo_reason)

with st.container(key="topbar"):
    top1, top2, top3 = st.columns([2, 1.4, 0.8], vertical_alignment="bottom", gap="small")
    user = top1.text_input("Your initials", key="user", max_chars=8, placeholder="e.g. DS",
                           help="Required. Saved with the date and time of every receive, use, count and change.")
    user = user.strip().upper()
    goal_now = int(st.session_state.get("goal", 4000))
    with top2.popover(f"Goal {goal_now:,}", icon=":material/flag:", width="stretch",
                      help="How many samples the stock should cover."):
        goal = int(st.number_input("Sample goal", min_value=1, value=4000, step=96, key="goal",
                                   help="Targets for usage-based items scale with this number."))
        st.caption(f"{ic.runs_needed(goal)} KingFisher runs of {ic.SAMPLES_PER_RUN} samples.")
    if top3.button("Refresh", key="refresh", icon=":material/refresh:", width="stretch",
                   help="Read the latest numbers from Google Sheets now."):
        refresh()
        st.rerun()

items = current_items()
if not items:
    st.warning("The inventory sheet is empty.")
    if st.button("Add COE starter item list", disabled=not user):
        added = sheet.seed_starter_items(user, goal)
        flash(f"Added {added} starter items.")

VIEWS = ["Meter", "Receive", "Use", "Count", "Items", "Edit", "Log"]
view = st.segmented_control("Go to", VIEWS, default="Meter", key="view", label_visibility="collapsed")
view = view or "Meter"


# ---- Meter (re-reads the sheet on its own)
@st.fragment(run_every=REFRESH_SECONDS)
def meter_view(goal: int) -> None:
    items = current_items()
    rows, summary = ic.restock_report(items, goal)
    by_id = {i["Item ID"]: i for i in items}
    info = {}
    for r in rows:
        item = by_id.get(r.item_id, {})
        reorder = ic.to_number(item.get("Reorder at"))
        counted = ic.to_number(item.get("On hand")) is not None
        info[r.item_id] = (reorder, stock_state(r, reorder, counted), item.get("Last checked", ""),
                           item.get("Checked by", ""))
    rows.sort(key=lambda r: (STATE_ORDER.index(info[r.item_id][1]), r.fraction, r.item))

    st.markdown(hero_html(summary, rows, info), unsafe_allow_html=True)

    counts = {name: sum(1 for v in info.values() if v[1] in states) for name, states in FILTERS.items()}
    f1, f2 = st.columns([3, 1], vertical_alignment="bottom")
    with f1:
        picked = st.pills("Show", [n for n in FILTERS if n == "All" or counts[n]], default="All",
                          key="meter_filter", label_visibility="collapsed",
                          format_func=lambda n: f"{n} {counts[n]}")
    category_order = list(dict.fromkeys(i["Category"] for i in items if i.get("Category")))
    chosen = f2.selectbox("Category", ["All categories"] + category_order, key="meter_category",
                          label_visibility="collapsed")
    states = FILTERS.get(picked or "All", FILTERS["All"])
    shown = [r for r in rows if info[r.item_id][1] in states
             and (chosen == "All categories" or r.category == chosen)]
    if shown:
        st.markdown(groups_html(shown, info, category_order), unsafe_allow_html=True)
        st.markdown(
            '<p class="list-foot">The magenta bar is stock on hand as a share of what the goal needs; '
            f"the dark mark is the reorder level. Numbers update from the sheet every {REFRESH_SECONDS} "
            "seconds.</p>", unsafe_allow_html=True)
    else:
        st.caption("No items match this filter.")

    tracked = {r.item_id for r in rows}
    untargeted = [i for i in items if i["Item ID"] not in tracked]
    if untargeted:
        with st.expander(f"Items without a target ({len(untargeted)})"):
            st.caption("Counted, but not on the meter until a target or usage is set under Edit.")
            st.dataframe(pd.DataFrame(untargeted)[["Item", "On hand", "Unit", "Checked by", "Last checked"]],
                         hide_index=True, width="stretch")

    short = [r for r in rows if r.shortfall > 0]
    with st.expander(f"Shopping list ({len(short)} items)"):
        if short:
            cat_no = {i["Item ID"]: i["Cat. No."] for i in items}
            shop = pd.DataFrame([{
                "Item": r.item, "Cat. No.": cat_no.get(r.item_id, ""), "Unit": r.unit,
                "On hand": r.on_hand, f"Target for {goal:,}": r.needed, "Order": r.shortfall,
                "Status": STATES[info[r.item_id][1]][0],
            } for r in short])
            st.dataframe(shop, hide_index=True, width="stretch")
            st.download_button("Download shopping list (CSV)", shop.to_csv(index=False),
                               file_name=f"shopping_list_{goal}_samples.csv", mime="text/csv")
        else:
            st.success("Nothing to order for this goal.")


# ---- Inventory table (re-reads the sheet on its own)
@st.fragment(run_every=REFRESH_SECONDS)
def inventory_view() -> None:
    items = current_items()
    if not items:
        st.caption("No items yet.")
        return
    df = pd.DataFrame(items)
    s1, s2, s3 = st.columns([2, 1, 1])
    query = s1.text_input("Search items", placeholder="Item name or catalog number", key="inv_query")
    cat_filter = s2.selectbox("Category", ["All"] + sorted(df["Category"].replace("", pd.NA).dropna().unique()),
                              key="inv_cat")
    status_filter = s3.selectbox("Status", ["All"] + ic.STATUS_OPTIONS, key="inv_status")
    if query:
        df = df[df["Item"].str.contains(query, case=False, regex=False)
                | df["Cat. No."].str.contains(query, case=False, regex=False)]
    if cat_filter != "All":
        df = df[df["Category"] == cat_filter]
    if status_filter != "All":
        df = df[df["Status"] == status_filter]
    if not st.toggle("Show all columns", key="inv_all"):
        df = df[["Item", "On hand", "Unit", "Status", "Checked by", "Last checked"]]
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Download inventory (CSV)", pd.DataFrame(items).to_csv(index=False),
                       file_name="coe_lab_inventory.csv", mime="text/csv")


if view == "Meter":
    meter_view(goal)

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
            location = st.text_input("Location", placeholder="e.g. Room 5149, shelf B")
            submitted = st.form_submit_button("Add item and quantity", type="primary", width="stretch")
        if submitted and not needs_initials():
            if not unit.strip():
                st.error("Enter the unit, for example box or kit.")
            elif qty <= 0:
                st.error("Enter the quantity received.")
            else:
                try:
                    new_id = sheet.add_item({"Item": name, "Unit": unit, "On hand": qty,
                                             "Category": "" if category == "Other" else category,
                                             "Cat. No.": cat_no, "Location": location}, user)
                    flash(f"Added {name.strip()} ({new_id}) with {fmt(qty)} {plural(unit.strip(), qty)} "
                          f"received by {user}. Set its target and reorder level under Edit.")
                except ic.InventoryError as exc:
                    st.error(str(exc))
    elif items:
        current = item_picker(items, key="receive_item")
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
            new_reorder = c3.number_input("Reorder at (low-stock level)", min_value=0.0, step=1.0,
                                          value=float(ic.to_number(current["Reorder at"]) or 0))
            status_choice = c4.selectbox("Status", ["Automatic"] + ic.STATUS_OPTIONS,
                                         help="Automatic sets In stock, Low or Out of stock from the count.")
            d1, d2 = st.columns(2)
            new_location = d1.text_input("Location", value=current["Location"])
            new_cat = d2.text_input("Cat. No.", value=current["Cat. No."])
            new_notes = st.text_area("Notes", value=current["Notes"])
            with st.expander("Target and usage"):
                new_target = st.number_input("Target (fixed amount to keep)", min_value=0.0, step=1.0,
                                             value=float(ic.to_number(current["Target"]) or 0))
                e1, e2 = st.columns(2)
                new_ps = e1.number_input("Used per sample", min_value=0.0, step=0.01, format="%.5f",
                                         value=float(ic.to_number(current["Per sample"]) or 0))
                new_pr = e2.number_input("Used per 96-sample run", min_value=0.0, step=1.0,
                                         value=float(ic.to_number(current["Per run"]) or 0))
                st.caption("With usage per sample or per run, the target follows the sample goal.")
            submitted = st.form_submit_button("Save details", type="primary", width="stretch")
        if submitted and not needs_initials():
            proposed = {
                "Item": name, "Unit": unit, "Category": category, "Reorder at": new_reorder or "",
                "Location": new_location, "Cat. No.": new_cat, "Notes": new_notes,
                "Target": new_target or "", "Per sample": new_ps or "", "Per run": new_pr or "",
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
