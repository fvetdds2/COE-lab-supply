from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import inventory_core as ic

st.set_page_config(page_title="COE Lab Supply Inventory", page_icon="🧪", layout="wide",
                   initial_sidebar_state="collapsed")

METER = "#d55181"  # magenta meter fill; clears 3:1 contrast on light and dark backgrounds
# Stock states, most urgent first: (label, icon, chip color, glyph color). Status colors follow
# the usual inventory convention and always come with an icon and a word, never color alone.
STATES = {
    "out": ("Out of stock", "✕", "#d03b3b", "#ffffff"),
    "low": ("Low stock", "▲", "#fab219", "#1a1a19"),
    "below": ("Below target", "◔", "#6b6a66", "#ffffff"),
    "ok": ("Stocked", "✓", "#0ca30c", "#ffffff"),
}
STATE_ORDER = list(STATES)
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


def get_sheet() -> tuple[ic.InventorySheet, bool]:
    try:
        has_secrets = "gcp_service_account" in st.secrets and "sheet_url" in st.secrets
    except Exception:  # no secrets.toml at all
        has_secrets = False
    if not has_secrets:
        return demo_sheet(), True
    account = tuple(sorted(dict(st.secrets["gcp_service_account"]).items()))
    return live_sheet(st.secrets["sheet_url"], account), False


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


def stock_state(row: ic.MeterRow, reorder_at: float | None) -> str:
    if row.on_hand <= 0:
        return "out"
    if row.fraction >= 1:
        return "ok"
    if reorder_at is not None and row.on_hand <= reorder_at:
        return "low"
    return "below"


# --------------------------------------------------------------------------- meter drawing

PAGE_CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
.meter-list {display:flex; flex-direction:column; gap:16px; margin-top:6px;}
.meter-row {display:grid; grid-template-columns:minmax(0, 2fr) minmax(0, 3fr) 128px; gap:16px; align-items:center;}
.meter-name {font-size:14px; line-height:1.3; font-weight:500;}
.meter-meta {font-size:12px; opacity:0.72; margin-top:2px; line-height:1.35;}
.meter-track {position:relative; height:12px; border-radius:4px; background:rgba(128,128,128,0.20);}
.meter-fill {height:100%; border-radius:4px;}
.meter-tick {position:absolute; top:-4px; width:2px; height:20px; border-radius:1px;
             background:currentColor; opacity:0.55;}
.chip {display:inline-flex; align-items:center; gap:6px; font-size:13px; font-weight:600; white-space:nowrap;}
.chip span {display:inline-block; width:18px; height:18px; line-height:18px; text-align:center;
            border-radius:50%; font-size:11px;}
.legend {display:flex; flex-wrap:wrap; gap:8px 18px; margin:6px 0 4px; font-size:13px;}
.legend .muted {opacity:0.7; font-weight:400;}
.hero {font-size:52px; font-weight:700; line-height:1.05; letter-spacing:-0.5px;}
.hero small {font-size:22px; font-weight:500; opacity:0.75;}
.hero-sub {font-size:15px; opacity:0.8; margin:6px 0 10px;}
.hero-track {height:14px; border-radius:4px; background:rgba(128,128,128,0.20); max-width:760px;}
@media (max-width: 640px) {
  .block-container {padding-left: 1rem; padding-right: 1rem; padding-top: 1.2rem;}
  h1 {font-size: 1.7rem !important;}
  .meter-row {grid-template-columns:minmax(0, 1fr) auto; gap:6px 10px;}
  .meter-row > div:first-child {grid-column:1 / -1;}
  .chip {font-size:12px;}
  .hero {font-size:40px;}
  .hero small {font-size:18px;}
  .hero-sub {font-size:14px;}
  button[kind="primary"], button[kind="secondary"] {min-height: 2.75rem;}
}
</style>
"""


def chip(state: str) -> str:
    label, icon, bg, ink = STATES[state]
    return f'<span class="chip"><span style="background:{bg};color:{ink};">{icon}</span>{label}</span>'


def meter_html(rows: list[ic.MeterRow], info: dict) -> str:
    parts = ['<div class="meter-list">']
    for r in rows:
        reorder, state, when, who = info[r.item_id]
        unit = plural(r.unit, r.needed)
        meta = f"{fmt(r.on_hand)} of {fmt(r.needed)} {html.escape(unit)}"
        if r.shortfall:
            meta += f" · order {fmt(r.shortfall)}"
        if reorder is not None:
            meta += f" · reorder at {fmt(reorder)}"
        if when:
            meta += f"<br>checked {html.escape(when[:10])}" + (f" by {html.escape(who)}" if who else "")
        covers = f"; covers {r.covered:,} samples" if r.covered is not None else ""
        tip = f"{r.item}: {fmt(r.on_hand)} of {fmt(r.needed)} {unit} ({r.fraction:.0%}){covers}"
        tick = ""
        if reorder is not None and r.needed:
            tick = (f'<div class="meter-tick" style="left:calc({min(reorder / r.needed, 1) * 100:.1f}% - 1px);" '
                    f'title="Reorder level"></div>')
        parts.append(
            f'<div class="meter-row" title="{html.escape(tip)}">'
            f'<div><div class="meter-name">{html.escape(r.item)}</div><div class="meter-meta">{meta}</div></div>'
            f'<div class="meter-track"><div class="meter-fill" style="width:{r.fraction * 100:.1f}%;'
            f'background:{METER};"></div>{tick}</div>'
            f"<div>{chip(state)}</div></div>"
        )
    parts.append("</div>")
    return "".join(parts)


def hero_html(summary: dict, rows: list[ic.MeterRow]) -> str:
    goal, covered = summary["goal"], summary["covered"]
    share = covered / goal if goal else 0
    limiting = summary["limiting_item"]
    limit_row = next((r for r in rows if r.item == limiting), None)
    if share >= 1:
        sub = f"Stock covers the full goal of {goal:,} samples ({summary['runs']} KingFisher runs)."
    elif limit_row:
        sub = (f"Stock covers {share:.0%} of the {goal:,}-sample goal. First to run out: "
               f"{html.escape(limiting)} ({fmt(limit_row.on_hand)} of {fmt(limit_row.needed)} "
               f"{html.escape(plural(limit_row.unit, limit_row.needed))}).")
    else:
        sub = "Add usage per sample or per run to items to see coverage."
    return (
        f'<div class="hero">{covered:,} <small>of {goal:,} samples</small></div>'
        f'<div class="hero-sub">{sub}</div>'
        f'<div class="hero-track"><div class="meter-fill" style="width:{min(share, 1) * 100:.1f}%;'
        f'background:{METER};"></div></div>'
    )


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

sheet, demo = get_sheet()
st.markdown(PAGE_CSS, unsafe_allow_html=True)
st.title("COE Lab Inventory")
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))
if demo:
    st.info("Demo mode: example counts, not your inventory. Add Google credentials to "
            "`.streamlit/secrets.toml` to use the COE lab inventory sheet (see README).")

top1, top2, top3 = st.columns([2, 2, 1], vertical_alignment="bottom")
user = top1.text_input("Your initials", key="user", max_chars=8, placeholder="e.g. DS",
                       help="Required. Saved with the date and time of every receive, use, count and change.")
user = user.strip().upper()
goal = int(top2.number_input("Sample goal", min_value=1, value=4000, step=96,
                             help="Targets for usage-based items scale with this number."))
if top3.button("Refresh", width="stretch", help="Read the latest numbers from Google Sheets now."):
    refresh()
    st.rerun()

items = current_items()
if not items:
    st.warning("The inventory sheet is empty.")
    if st.button("Add COE starter item list", disabled=not user):
        added = sheet.seed_starter_items(user, goal)
        flash(f"Added {added} starter items.")

VIEWS = ["Meter", "Receive", "Use", "Count", "Inventory", "Edit", "Log"]
view = st.segmented_control("Go to", VIEWS, default="Meter", key="view", label_visibility="collapsed")
view = view or "Meter"
st.caption(f"{ic.runs_needed(goal)} KingFisher runs of {ic.SAMPLES_PER_RUN} samples · "
           f"numbers refresh every {REFRESH_SECONDS} seconds")


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
        info[r.item_id] = (reorder, stock_state(r, reorder), item.get("Last checked", ""),
                           item.get("Checked by", ""))
    rows.sort(key=lambda r: (STATE_ORDER.index(info[r.item_id][1]), r.fraction, r.item))

    st.markdown(hero_html(summary, rows), unsafe_allow_html=True)
    counts = {s: sum(1 for v in info.values() if v[1] == s) for s in STATES}
    legend = " ".join(f'<span>{chip(s)} <span class="muted">{counts[s]}</span></span>' for s in STATES)
    st.markdown(f'<div class="legend">{legend}</div>', unsafe_allow_html=True)

    urgent = [r.item for r in rows if info[r.item_id][1] in ("out", "low")]
    if urgent:
        names = ", ".join(urgent[:4]) + (f" and {len(urgent) - 4} more" if len(urgent) > 4 else "")
        st.warning(f"{len(urgent)} items at or below their reorder level: {names}.")

    f1, f2 = st.columns([2, 1], vertical_alignment="bottom")
    categories = sorted({r.category for r in rows if r.category})
    chosen = f1.selectbox("Category", ["All categories"] + categories, key="meter_category")
    only_action = f2.toggle("Needs action only", key="meter_action",
                            help="Out of stock, low stock and below target.")
    shown = [r for r in rows if (chosen == "All categories" or r.category == chosen)
             and (not only_action or info[r.item_id][1] != "ok")]
    if shown:
        st.markdown(meter_html(shown, info), unsafe_allow_html=True)
        st.caption("Magenta bar: on hand as a share of the target. Thin mark: reorder level.")
    else:
        st.caption("Nothing to show for this filter.")

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

elif view == "Inventory":
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
