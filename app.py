from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import inventory_core as ic

st.set_page_config(page_title="COE Lab Supply Inventory", page_icon="🧪", layout="wide")

GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"  # status palette: fixed, icon + label always shown

DEMO_COUNTS = {  # example counts for demo mode only
    "MagMAX DNA Multi-Sample Ultra 2.0 Kit": 8,
    "KingFisher Apex 96 deep-well plates, barcoded": 200,
    "KingFisher Apex 96 KF microplates, barcoded": 60,
    "KingFisher 96 deep-well tip combs, barcoded": 100,
    "Ethanol, 96-100%, molecular biology grade": 2.5,
    "Nuclease-free water": 1,
    "Filter tips, 20 uL": 4800,
    "Filter tips, 200 uL": 3000,
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


def refresh() -> None:
    load_items.clear()  # every session re-reads the sheet after a write


@st.cache_data(ttl=60, show_spinner=False)
def load_items(_sheet: ic.InventorySheet) -> list[dict]:
    return _sheet.items()


# --------------------------------------------------------------------------- meter drawing

def status_of(row: ic.MeterRow) -> tuple[str, str, str]:
    """(label, icon, color) for a meter row."""
    if row.fraction >= 1:
        return "Ready", "✓", GOOD
    if row.on_hand <= 0:
        return "Out", "✕", CRITICAL
    return "Restock", "▲", WARNING


def plural(unit: str, amount: float) -> str:
    if amount == 1 or not unit or unit.endswith("s") or unit in ("L", "mL", "uL", "kg", "g"):
        return unit
    return unit + ("es" if unit.endswith(("x", "ch", "sh")) else "s")


def fmt(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


METER_CSS = """
<style>
.meter-list {display:flex; flex-direction:column; gap:14px; margin-top:4px;}
.meter-row {display:grid; grid-template-columns:minmax(0, 2fr) minmax(0, 3fr) 96px; gap:16px; align-items:center;}
.meter-name {font-size:14px; line-height:1.3;}
.meter-meta {font-size:12px; opacity:0.72; margin-top:2px;}
.meter-track {height:10px; border-radius:4px; background:rgba(128,128,128,0.20); overflow:hidden;}
.meter-fill {height:100%; border-radius:0 4px 4px 0;}
.meter-chip {font-size:13px; font-weight:600; white-space:nowrap;}
.meter-chip span {display:inline-block; width:18px; height:18px; line-height:18px; text-align:center;
                  border-radius:50%; color:#fff; font-size:11px; margin-right:6px;}
.hero {font-size:52px; font-weight:700; line-height:1.05; letter-spacing:-0.5px;}
.hero-sub {font-size:15px; opacity:0.8; margin:6px 0 10px;}
.hero-track {height:14px; border-radius:4px; background:rgba(128,128,128,0.20); overflow:hidden; max-width:760px;}
@media (max-width: 640px) {
  .meter-row {grid-template-columns:1fr; gap:6px;}
  .hero {font-size:40px;}
}
</style>
"""


def meter_html(rows: list[ic.MeterRow]) -> str:
    parts = [METER_CSS, '<div class="meter-list">']
    for r in rows:
        label, icon, color = status_of(r)
        ink = "#1a1a19" if color == WARNING else "#ffffff"  # dark glyph on the light warning fill
        covers = f" · covers {r.covered:,} samples" if r.covered is not None else ""
        tip = (f"{r.item}: {fmt(r.on_hand)} of {fmt(r.needed)} {plural(r.unit, r.needed)} on hand "
               f"({r.fraction:.0%}){covers}; short {fmt(r.shortfall)}")
        meta = f"{fmt(r.on_hand)} / {fmt(r.needed)} {html.escape(plural(r.unit, r.needed))}"
        if r.shortfall:
            meta += f" · short {fmt(r.shortfall)}"
        parts.append(
            f'<div class="meter-row" title="{html.escape(tip)}">'
            f'<div><div class="meter-name">{html.escape(r.item)}</div><div class="meter-meta">{meta}</div></div>'
            f'<div class="meter-track"><div class="meter-fill" style="width:{r.fraction * 100:.1f}%;'
            f'background:{color};"></div></div>'
            f'<div class="meter-chip"><span style="background:{color};color:{ink};">{icon}</span>{label}</div>'
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def hero_html(summary: dict, rows: list[ic.MeterRow]) -> str:
    goal, covered = summary["goal"], summary["covered"]
    share = covered / goal if goal else 0
    color = GOOD if share >= 1 else (CRITICAL if covered == 0 else WARNING)
    limiting = summary["limiting_item"]
    limit_row = next((r for r in rows if r.item == limiting), None)
    if share >= 1:
        sub = f"Current stock covers the full goal of {goal:,} samples ({summary['runs']} KingFisher runs)."
    elif limit_row:
        sub = (f"Current stock covers {share:.0%} of the {goal:,}-sample goal. "
               f"Limiting item: {html.escape(limiting)} "
               f"({fmt(limit_row.on_hand)} of {fmt(limit_row.needed)} {html.escape(plural(limit_row.unit, limit_row.needed))}).")
    else:
        sub = "Add usage per sample or per run to items to see coverage."
    return (
        f'{METER_CSS}<div class="hero">{covered:,} <span style="font-size:22px;font-weight:500;opacity:0.75;">'
        f"of {goal:,} samples</span></div>"
        f'<div class="hero-sub">{sub}</div>'
        f'<div class="hero-track"><div class="meter-fill" style="width:{min(share, 1) * 100:.1f}%;'
        f'background:{color};"></div></div>'
    )


# --------------------------------------------------------------------------- page

sheet, demo = get_sheet()
items = sheet.items() if demo else load_items(sheet)  # demo data lives in this session only

with st.sidebar:
    st.header("CECTR Lab Inventory")
    user = st.text_input("Your initials", key="user", max_chars=8,
                         help="Recorded with every change in the Change log tab.")
    goal = st.number_input("Sample goal", min_value=1, value=4000, step=96,
                           help="Restock targets for usage-based items scale with this number.")
    st.caption(f"{ic.runs_needed(goal)} KingFisher runs of {ic.SAMPLES_PER_RUN} samples")
    if demo:
        st.info("Demo mode: example counts, not your inventory. Add Google credentials to "
                "`.streamlit/secrets.toml` to use your sheet (see README).")
    if not items:
        st.warning("The inventory sheet is empty.")
        if st.button("Add CECTR starter item list", disabled=not user.strip()):
            added = sheet.seed_starter_items(user, int(goal))
            refresh()
            st.success(f"Added {added} items.")
            st.rerun()
    if st.button("Reload from Google Sheets"):
        refresh()
        st.rerun()

st.title("Lab inventory")
tab_meter, tab_list, tab_add, tab_update, tab_log = st.tabs(
    ["Restock meter", "Inventory", "Add item", "Update or count", "Change log"]
)

# ---- Restock meter
with tab_meter:
    rows, summary = ic.restock_report(items, int(goal))
    st.markdown(hero_html(summary, rows), unsafe_allow_html=True)
    st.write("")
    ready = sum(1 for r in rows if status_of(r)[0] == "Ready")
    out = sum(1 for r in rows if status_of(r)[0] == "Out")
    c1, c2, c3 = st.columns(3)
    c1.metric("✓ Ready", ready)
    c2.metric("▲ Restock", len(rows) - ready - out)
    c3.metric("✕ Out", out)

    categories = sorted({r.category for r in rows if r.category})
    f1, f2 = st.columns([2, 1])
    chosen = f1.selectbox("Category", ["All categories"] + categories, key="meter_category")
    only_short = f2.toggle("Only items to restock", value=False)
    shown = [r for r in rows if (chosen == "All categories" or r.category == chosen)
             and (not only_short or r.shortfall > 0)]
    if shown:
        st.markdown(meter_html(shown), unsafe_allow_html=True)
    else:
        st.caption("Nothing to show for this filter.")

    short = [r for r in rows if r.shortfall > 0]
    with st.expander(f"Shopping list ({len(short)} items)", expanded=False):
        if short:
            cat_no = {i["Item ID"]: i["Cat. No."] for i in items}
            shop = pd.DataFrame([{
                "Item": r.item, "Cat. No.": cat_no.get(r.item_id, ""), "Unit": r.unit,
                "On hand": r.on_hand, f"Needed for {goal:,}": r.needed, "Short": r.shortfall,
            } for r in short])
            st.dataframe(shop, hide_index=True, width="stretch")
            st.download_button("Download shopping list (CSV)", shop.to_csv(index=False),
                               file_name=f"shopping_list_{goal}_samples.csv", mime="text/csv")
        else:
            st.success("Nothing to order for this goal.")

# ---- Inventory table
with tab_list:
    if items:
        df = pd.DataFrame(items)
        s1, s2, s3 = st.columns([2, 1, 1])
        query = s1.text_input("Search items", placeholder="Item name or catalog number")
        cat_filter = s2.selectbox("Category", ["All"] + sorted(df["Category"].replace("", pd.NA).dropna().unique()))
        status_filter = s3.selectbox("Status", ["All"] + ic.STATUS_OPTIONS)
        if query:
            mask = (df["Item"].str.contains(query, case=False, regex=False)
                    | df["Cat. No."].str.contains(query, case=False, regex=False))
            df = df[mask]
        if cat_filter != "All":
            df = df[df["Category"] == cat_filter]
        if status_filter != "All":
            df = df[df["Status"] == status_filter]
        st.dataframe(df, hide_index=True, width="stretch")
        st.download_button("Download inventory (CSV)", pd.DataFrame(items).to_csv(index=False),
                           file_name="lab_inventory.csv", mime="text/csv")
    else:
        st.caption("No items yet.")

# ---- Add item
with tab_add:
    with st.form("add_item", clear_on_submit=True):
        a1, a2, a3 = st.columns([3, 2, 1])
        name = a1.text_input("Item name *")
        category = a2.text_input("Category", placeholder="e.g. Pipetting")
        unit = a3.text_input("Unit", placeholder="e.g. box")
        b1, b2, b3, b4 = st.columns(4)
        cat_no_in = b1.text_input("Cat. No.")
        on_hand = b2.number_input("On hand", min_value=0.0, step=1.0)
        reorder = b3.number_input("Reorder at", min_value=0.0, step=1.0)
        target = b4.number_input("Target (if not usage-based)", min_value=0.0, step=1.0)
        u1, u2, u3 = st.columns(3)
        per_sample = u1.number_input("Used per sample", min_value=0.0, step=0.01, format="%.5f")
        per_run = u2.number_input("Used per 96-sample run", min_value=0.0, step=1.0)
        location = u3.text_input("Location", placeholder="e.g. Room 5149, shelf B")
        notes = st.text_area("Notes")
        if st.form_submit_button("Add item", type="primary"):
            try:
                new_id = sheet.add_item({
                    "Item": name, "Category": category, "Unit": unit, "Cat. No.": cat_no_in,
                    "On hand": on_hand, "Reorder at": reorder or "", "Target": target or "",
                    "Per sample": per_sample or "", "Per run": per_run or "",
                    "Location": location, "Notes": notes,
                }, user)
                refresh()
                st.success(f"Added {name} as {new_id}.")
            except ic.InventoryError as exc:
                st.error(str(exc))

# ---- Update or count
with tab_update:
    if not items:
        st.caption("No items yet.")
    else:
        labels = {f"{i['Item ID']} · {i['Item']}": i["Item ID"] for i in items}
        picked = st.selectbox("Item", list(labels))
        current = next(i for i in items if i["Item ID"] == labels[picked])
        st.caption(f"Last checked {current['Last checked'] or 'never'} by {current['Checked by'] or '-'}")
        with st.form("update_item"):
            c1, c2, c3 = st.columns(3)
            new_on_hand = c1.number_input("On hand", min_value=0.0, step=1.0,
                                          value=float(ic.to_number(current["On hand"]) or 0))
            status_choice = c2.selectbox("Status", ["Automatic"] + ic.STATUS_OPTIONS,
                                         help="Automatic sets In stock, Low or Out of stock from the count. "
                                              "Choose Ordered after placing an order.")
            new_reorder = c3.number_input("Reorder at", min_value=0.0, step=1.0,
                                          value=float(ic.to_number(current["Reorder at"]) or 0))
            d1, d2 = st.columns(2)
            new_location = d1.text_input("Location", value=current["Location"])
            new_cat = d2.text_input("Cat. No.", value=current["Cat. No."])
            new_notes = st.text_area("Notes", value=current["Notes"])
            with st.expander("Usage and target"):
                e1, e2, e3 = st.columns(3)
                new_ps = e1.number_input("Used per sample", min_value=0.0, step=0.01, format="%.5f",
                                         value=float(ic.to_number(current["Per sample"]) or 0))
                new_pr = e2.number_input("Used per 96-sample run", min_value=0.0, step=1.0,
                                         value=float(ic.to_number(current["Per run"]) or 0))
                new_target = e3.number_input("Target (if not usage-based)", min_value=0.0, step=1.0,
                                             value=float(ic.to_number(current["Target"]) or 0))
            if st.form_submit_button("Save", type="primary"):
                proposed = {
                    "On hand": new_on_hand, "Reorder at": new_reorder or "", "Location": new_location,
                    "Cat. No.": new_cat, "Notes": new_notes, "Per sample": new_ps or "",
                    "Per run": new_pr or "", "Target": new_target or "",
                }
                changes = {}
                for field, value in proposed.items():
                    old = current[field]
                    if field in ic.NUMERIC_FIELDS:
                        if ic.to_number(old) != (ic.to_number(value) if value != "" else None):
                            changes[field] = value
                    elif str(old) != str(value):
                        changes[field] = value
                if status_choice != "Automatic":
                    changes["Status"] = status_choice
                try:
                    updated = sheet.update_item(current["Item ID"], changes, user)
                    refresh()
                    st.success(f"Saved {updated['Item']}: on hand {updated['On hand']}, status {updated['Status']}.")
                except ic.InventoryError as exc:
                    st.error(str(exc))

# ---- Change log
with tab_log:
    log = sheet.changes()
    if log:
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
    else:
        st.caption("No changes recorded yet.")
