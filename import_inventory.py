"""Import the lab's Inventory_List.csv into the "COE lab inventory" Google Sheet.

Run in the app folder (the one with .streamlit/secrets.toml):
    python import_inventory.py Inventory_List.csv --user DS            # preview only, changes nothing
    python import_inventory.py Inventory_List.csv --user DS --apply    # write to the sheet

Item names are kept exactly as written in the list. Nine supplies in the list are already in the
sheet's starter list under other names; those rows are updated (name, unit, count, minimum, full
stock, notes). Everything else is added as a new item. Every change is written to the Change log
with your initials. Running it again updates the same items instead of adding duplicates.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import tomllib
from pathlib import Path

import inventory_core as ic

COUNTED_BY = "Inventory list"  # shown as "Checked ... by Inventory list" for the imported counts

# Starter items that are the same supply as a row in the list: list name -> starter name
MATCHES = {
    "Pipette Tips 20": "Filter tips, 20 uL",
    "Pipette Tips 200": "Filter tips, 200 uL",
    "Pipette Tips 300": "Filter tips, 300 uL",
    "Pipette Tips 1250": "Filter tips, 1,000 or 1,250 uL",
    "96 deep well plates": "KingFisher Apex 96 deep-well plates, barcoded",
    "Tip combs": "KingFisher 96 deep-well tip combs, barcoded",
    "200 ul plates": "KingFisher Apex 96 KF microplates, barcoded",
    "Ethanol 200 proof": "Ethanol, 96-100%, molecular biology grade",
    "Molecular water": "Nuclease-free water",
}

# Category and counting unit for each row of the list, keyed by (name, room). The first value is a
# plain description for reference only; the item keeps the name written in the list.
# Pack sizes and other unit text from the list go into Notes.
CLEAN = {
    ("4ml K2edta tubes", "Exam Room"): ("K2EDTA tubes, 4 mL", "Blood collection", "pack"),
    ("BD Vacutainer Gold STT tubes", "Exam Room"): ("BD Vacutainer SST tubes, gold top", "Blood collection", "pack"),
    ("Kawasumi: K-Shield Advantage, Blood Collection Set 21 Guage", "Exam Room"):
        ("Kawasumi K-Shield Advantage blood collection set, 21 gauge", "Blood collection", "pack"),
    ("Nitrile Gloves (Small)", "Exam Room"): ("Nitrile gloves, small", "Safety and waste", "box"),
    ("BD Vacutainer Saftey Lok Blood collection set 23guage", "Exam Room"):
        ("BD Vacutainer Safety-Lok blood collection set, 23 gauge", "Blood collection", "pack"),
    ("Alcohol Preps", "Exam Room"): ("Alcohol prep pads", "Blood collection", "pack"),
    ("Hypoallergenic Clear Tape", "Exam Room"): ("Hypoallergenic clear tape", "Blood collection", "pack"),
    ('Standard tube holder "Hubs/Vacutainer"', "Exam Room"):
        ("Standard tube holders (Vacutainer hubs)", "Blood collection", "holder"),
    ("Adhesive Bandages  Fabric Strip", "Exam Room"): ("Adhesive bandages, fabric strip", "Blood collection", "pack"),
    ("Woven Gauze Sponge Non-Sterile 2x2'", "Exam Room"):
        ("Woven gauze sponges, non-sterile, 2 x 2 in", "Blood collection", "pack"),
    ("Torniquetts", "Exam Room"): ("Tourniquets", "Blood collection", "box"),
    ("DNA/RNA Shield tubes", "Exam Room"): ("DNA/RNA Shield collection tubes", "Sample collection", "pack"),
    ("DNA/RNA labels", "Exam Room"): ("DNA/RNA labels", "Labels and printing", "pack"),
    ("Ribbion for the printer", "Exam Room"): ("Printer ribbon, exam room", "Labels and printing", "roll"),
    ("Nitrile Gloves (Medium)", "Exam Room"): ("Nitrile gloves, medium", "Safety and waste", "box"),
    ("Nitrile Gloves (Large)", "Exam Room"): ("Nitrile gloves, large", "Safety and waste", "box"),
    ("Nitrile Gloves (Extra Large)", "Exam Room"): ("Nitrile gloves, extra large", "Safety and waste", "box"),
    ("Wheaton 2ml tubes", "Laboratory"): ("Wheaton tubes, 2 mL", "Tubes and storage", "pack"),
    ("Pipette Tips 1250", "Laboratory"): ("Pipette tips, 1,250 uL", "Pipetting", "rack"),
    ("Pipette Tips 300", "Laboratory"): ("Pipette tips, 300 uL", "Pipetting", "rack"),
    ("Pipette Tips 200", "Laboratory"): ("Pipette tips, 200 uL", "Pipetting", "rack"),
    ("Pipette Tips 20", "Laboratory"): ("Pipette tips, 20 uL", "Pipetting", "rack"),
    ("Pipette tips 10 XL", "Laboratory"): ("Pipette tips, 10 uL XL", "Pipetting", "rack"),
    ("Bentop/ Auto clave bags", "Laboratory"): ("Benchtop autoclave bags", "Safety and waste", "case"),
    ("96 deep well plates", "Laboratory"): ("96 deep-well plates", "KingFisher consumables", "case"),
    ("Tip combs", "Laboratory"): ("Tip combs", "KingFisher consumables", "case"),
    ("200 ul plates", "Laboratory"): ("200 uL plates", "KingFisher consumables", "case"),
    ("MAGMAX DNA ULTRA 2.0 PROK", "Laboratory"): ("MagMAX DNA Ultra 2.0 proteinase K", "Extraction kit", "bottle"),
    ("MAGMAX DNA ULTRA 2.0 BEADS", "Laboratory"): ("MagMAX DNA Ultra 2.0 binding beads", "Extraction kit", "bottle"),
    ("MAGMAX DNA ULTRA 2.0 WASH 1", "Laboratory"): ("MagMAX DNA Ultra 2.0 Wash I solution", "Extraction kit", "bottle"),
    ("MAGMAX DNA ULTRA 2.0 LYS/BIN", "Laboratory"):
        ("MagMAX DNA Ultra 2.0 lysis/binding solution", "Extraction kit", "bottle"),
    ("MAGMAX DNA ULTRA ENHANCER", "Laboratory"): ("MagMAX DNA Ultra 2.0 enhancer solution", "Extraction kit", "bottle"),
    ("PBS X1", "Laboratory"): ("PBS, 1X", "Reagents", "bottle"),
    ("Ethanol 70%", "Laboratory"): ("Ethanol, 70%", "Reagents", "gallon"),
    ("Ethanol 200 proof", "Laboratory"): ("Ethanol, 200 proof", "Reagents", "pint bottle"),
    ("Clorox", "Laboratory"): ("Clorox bleach", "Safety and waste", "gallon"),
    ("15ml Centrifuge tubes", "Laboratory"): ("Centrifuge tubes, 15 mL", "Tubes and storage", "case"),
    ("Boxes for freezer Plasma/Serum", "Laboratory"): ("Freezer boxes, plasma/serum", "Tubes and storage", "box"),
    ("Boxes for Freezer DNA/RNA", "Laboratory"): ("Freezer boxes, DNA/RNA", "Tubes and storage", "box"),
    ("Buccal Swab", "Laboratory"): ("Buccal swabs", "Sample collection", "box"),
    ("Salivia Kit", "Laboratory"): ("Saliva kits", "Sample collection", "box"),
    ("Integra Pipette tips 1250", "Laboratory"): ("Integra pipette tips, 1,250 uL", "Pipetting", "tip"),
    ("Integra Pipette tips 300", "Laboratory"): ("Integra pipette tips, 300 uL", "Pipetting", "tip"),
    ("Integra pipette bags", "Laboratory"): ("Integra pipette bags", "Pipetting", ""),
    ("Serum/Plasma labels", "Laboratory"): ("Serum/plasma labels", "Labels and printing", ""),
    ("Ribbion for the printer", "Laboratory"): ("Printer ribbon, laboratory", "Labels and printing", ""),
    ("Molecular water", "Laboratory"): ("Molecular-grade water", "Reagents", ""),
    ("MAGMAX Ultra  DNA Elution", "Laboratory"): ("MagMAX DNA Ultra 2.0 elution solution", "Extraction kit", "bottle"),
}

# Pack-size text from the list's Units column, rewritten for Notes ("" = nothing to add).
PACK_TEXT = {
    "Packs of 50": "Pack of 50", "Pack of 50": "Pack of 50", "Packs of 100": "Pack of 100",
    "Pack of 12": "Pack of 12", "1 pk 250": "Pack of 250", "1 pk 100": "Pack of 100",
    "Packs of 200": "Pack of 200", "Boxes of 250": "Box of 250", "Boxes of 100": "Box of 100",
    "Roll of 1000 labels": "Roll of 1,000 labels", "50 per pack": "Pack of 50", "Racks/pack": "",
    "Case of 1000": "Case of 1,000", "Case of 50": "Case of 50", "Case of 10": "Case of 10",
    "1 unit/48 pcs": "48 per case", "45ml bottles": "45 mL bottle", "1.1 Liter": "1.1 L bottle",
    "450ml": "450 mL bottle", "45ml": "45 mL bottle", "500ml bottles": "500 mL bottle",
    "Cases of 500": "Case of 500", "1250ul": "1,250 uL tips", "300ul": "300 uL tips",
    "Boxes": "", "Gallons": "", "Pint bottles": "",
}
ROOMS = {"Exam Room": "Exam room", "Laboratory": "Laboratory"}
# Rows whose count or unit is unclear in the list, keyed by (name, room); listed in the preview.
CHECK = {
    ('Standard tube holder "Hubs/Vacutainer"', "Exam room"):
        "count 2,500 with 'pk 250' and reorder levels 3-12: holders or packs?",
    ("Tip combs", "Laboratory"): "count 14 with 'Case of 10': cases or combs?",
    ("Molecular water", "Laboratory"): "no unit in the list",
    ("Serum/Plasma labels", "Laboratory"): "no unit in the list",
    ("Ribbion for the printer", "Laboratory"): "no unit in the list",
    ("Integra pipette bags", "Laboratory"): "no count or unit in the list",
    ("MAGMAX Ultra DNA Elution", "Laboratory"): "no count in the list",
}


def squash(text: str) -> str:
    return " ".join(str(text or "").split())


def number(text: str) -> float | None:
    value = ic.to_number(squash(text))
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def iso_date(text: str) -> str:
    try:
        month, day, year = (int(p) for p in squash(text).split("/"))
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return ic.now_text()


def read_list(path: Path) -> list[dict]:
    """The list's rows, cleaned into the sheet's columns."""
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            raw = {squash(k): v for k, v in raw.items() if k}
            name, room = squash(raw.get("Supplies")), squash(raw.get("Location"))
            if not name:
                continue
            key = next((k for k in CLEAN if squash(k[0]) == name and k[1] == room), None)
            if key is None:
                raise SystemExit(f"Row not recognised: {name} ({room}). Add it to CLEAN in this script.")
            _, category, unit = CLEAN[key]
            item = name  # keep the name exactly as written in the list
            minimum = (number(raw.get("Reorder Point")) or number(raw.get("Minimum Stock"))
                       or number(raw.get("Critical Low")))
            notes = []
            if squash(raw.get("Notes")):
                text = squash(raw.get("Notes")).lstrip("*").strip()
                notes.append(text[0].upper() + text[1:] + ("" if text.endswith(".") else "."))
            pack = PACK_TEXT.get(squash(raw.get("Units")), squash(raw.get("Units")))
            if pack:
                notes.append(pack + ".")
            vendor = squash(raw.get("Vendor"))
            if vendor:
                notes.append(f"Vendor: {vendor}.")
            order_unit = squash(raw.get("Ordering units"))
            if order_unit:
                notes.append(f"Ordering unit: {order_unit.lower()}.")
            levels = [f"{label} {fmt}" for label, fmt in (("critical low", squash(raw.get("Critical Low"))),
                                                         ("minimum stock", squash(raw.get("Minimum Stock"))))
                      if fmt]
            if levels:
                notes.append("List levels: " + ", ".join(levels) + ".")
            rows.append({
                "source": name, "Item": item, "Category": category, "Unit": unit,
                "On hand": number(raw.get("Quantity")), "Reorder at": minimum,
                "Target": number(raw.get("Target Stock")), "Location": ROOMS.get(room, room),
                "Notes": " ".join(notes), "Last checked": iso_date(raw.get("Last Updated")),
            })
    return rows


def cell(value) -> str | float:
    return "" if value is None else ic.clean_number(value)


def plan(sheet: ic.InventorySheet, rows: list[dict]) -> tuple[list, list]:
    """(updates, adds): updates are (sheet row, old item, new item); adds are new items."""
    values = sheet.inventory.get_all_values()
    existing: dict[str, list] = {}
    for row_number, row in enumerate(values[1:], start=2):
        if any(c.strip() for c in row):
            item = {h: (row[i] if i < len(row) else "") for i, h in enumerate(ic.HEADERS)}
            existing.setdefault(" ".join(item["Item"].split()).lower(), []).append((row_number, item))

    def find(name: str, place: str):
        found = existing.get(name.lower(), [])
        same_place = [f for f in found if f[1]["Location"].strip().lower() == place.lower()]
        return (same_place or found or [None])[0]

    updates, adds = [], []
    for r in rows:
        match = find(r["Item"], r["Location"]) or find(MATCHES.get(r["source"], ""), r["Location"])
        new = {
            "Item": r["Item"], "Unit": r["Unit"], "On hand": cell(r["On hand"]), "Reorder at": cell(r["Reorder at"]),
            "Target": cell(r["Target"]), "Notes": r["Notes"], "Last checked": r["Last checked"],
            "Checked by": COUNTED_BY,
        }
        if match:
            row_number, old = match
            updated = dict(old)
            updated.update(new)
            updated["Per sample"] = updated["Per run"] = ""  # goal-based usage no longer applies
            if not str(old["Location"]).strip():  # keep a place staff already chose
                updated["Location"] = r["Location"]
            if not str(old["Category"]).strip():
                updated["Category"] = r["Category"]
            updated["Status"] = ic.auto_status(ic.to_number(updated["On hand"]), ic.to_number(updated["Reorder at"]),
                                               "", ic.to_number(updated["Target"]))
            updates.append((row_number, old, updated))
        else:
            record = {h: "" for h in ic.HEADERS}
            record.update(new)
            record["Category"], record["Location"] = r["Category"], r["Location"]
            record["Status"] = ic.auto_status(ic.to_number(record["On hand"]), ic.to_number(record["Reorder at"]),
                                              "", ic.to_number(record["Target"]))
            adds.append(record)
    return updates, adds


def apply(sheet: ic.InventorySheet, updates: list, adds: list, user: str, source: str) -> None:
    """Write everything in a few batched calls (Google limits how many calls a minute an app makes)."""
    numbers = [int(i["Item ID"].rsplit("-", 1)[-1]) for i in sheet.items()
               if i["Item ID"].rsplit("-", 1)[-1].isdigit()]
    next_number = (max(numbers) + 1) if numbers else 1
    stamp, log = ic.now_text(), []
    last_col = ic.column_letter(len(ic.HEADERS))
    data = []
    for row_number, old, new in updates:
        data.append({"range": f"A{row_number}:{last_col}{row_number}", "values": [[new[h] for h in ic.HEADERS]]})
        for field in ic.HEADERS:
            if field not in ("Last checked", "Checked by") and str(old[field]) != str(new[field]):
                log.append([stamp, user, old["Item ID"], new["Item"], f"{field} (imported from {source})",
                            str(old[field]), str(new[field])])
    new_rows = []
    for record in adds:
        record["Item ID"] = f"INV-{next_number:04d}"
        next_number += 1
        new_rows.append([record[h] for h in ic.HEADERS])
        log.append([stamp, user, record["Item ID"], record["Item"], f"(new item, imported from {source})", "",
                    f"On hand {record['On hand'] if record['On hand'] != '' else 'not counted'}"])
    ws = sheet.inventory
    if data:
        if hasattr(ws, "batch_update"):
            ws.batch_update(data, value_input_option="USER_ENTERED")
        else:
            for d in data:
                ws.update(values=d["values"], range_name=d["range"], value_input_option="USER_ENTERED")
    for target, rows in ((ws, new_rows), (sheet.log, log)):
        if not rows:
            continue
        if hasattr(target, "append_rows"):
            target.append_rows(rows, value_input_option="USER_ENTERED")
        else:
            for row in rows:
                target.append_row(row, value_input_option="USER_ENTERED")


def plural(unit: str, amount) -> str:
    if not unit or amount == 1:
        return unit
    head, _, rest = unit.partition(" ")
    if rest:  # "pint bottle" -> "pint bottles"
        return f"{head} {plural(rest, amount)}"
    return unit + ("es" if unit.endswith(("x", "ch", "sh")) else "s")


def show(updates: list, adds: list) -> None:
    def line(item):
        amount = item["On hand"]
        count = "not counted" if amount == "" else f"{amount:,g} {plural(item['Unit'], amount)}".strip()
        extra = f", minimum {item['Reorder at']}" if item["Reorder at"] != "" else ""
        extra += f", full stock {item['Target']}" if item["Target"] != "" else ""
        return f"{item['Item']}: {count}{extra}; {item['Location']}; {item['Status'] or 'no status'}"
    print(f"\nUpdate {len(updates)} items already in the sheet:")
    for _, old, new in updates:
        print(f"  {old['Item ID']}  {old['Item']}  ->  {line(new)}")
    print(f"\nAdd {len(adds)} new items:")
    for record in adds:
        print(f"  {line(record)}")
    unclear = [(n, place, why) for (n, place), why in CHECK.items()]
    if unclear:
        print("\nCheck these after the import (Edit page):")
        for name, place, why in unclear:
            print(f"  {name} ({place}): {why}")


def connect() -> ic.InventorySheet:
    secrets = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not secrets.exists():
        raise SystemExit(f"No secrets file at {secrets}. Run this in the app folder.")
    s = tomllib.loads(secrets.read_text(encoding="utf-8"))
    return ic.connect_service_account(s["sheet_url"], info=dict(s["gcp_service_account"]))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--user", required=True, help="Your initials, saved in the Change log")
    parser.add_argument("--apply", action="store_true", help="Write to the sheet (without it, only a preview)")
    args = parser.parse_args(argv)
    if not args.csv_file.exists():
        raise SystemExit(f"File not found: {args.csv_file}")
    rows = read_list(args.csv_file)
    sheet = connect()
    updates, adds = plan(sheet, rows)
    show(updates, adds)
    if not args.apply:
        print("\nPreview only; nothing was written. Add --apply to write these changes.")
        return
    apply(sheet, updates, adds, args.user.strip().upper(), args.csv_file.name)
    print(f"\nDone: updated {len(updates)} and added {len(adds)} items. Each change is in the Change log.")


if __name__ == "__main__":
    main(sys.argv[1:])
