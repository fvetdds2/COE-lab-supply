"""Write .streamlit/secrets.toml from a Google service-account key file.

Usage (run inside the lab_inventory folder):
    python make_secrets.py PATH_TO_KEY.json
    python make_secrets.py PATH_TO_KEY.json "https://docs.google.com/spreadsheets/d/.../edit"

Without a sheet link, it uses the "COE lab inventory" sheet.
The key file is read once; secrets.toml is written next to app.py and stays out of Git.
"""

import json
import sys
from pathlib import Path

COE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1bXpaxpp3bL74qvXWlGuYeEK19wbQ2nWUw3nWwNtkDrM/edit"


def toml_string(value: str) -> str:
    """Quote a value as a TOML basic string (escapes backslashes, quotes and newlines)."""
    return json.dumps(value)  # JSON string escaping is valid TOML basic-string escaping


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit('Usage: python make_secrets.py KEY.json ["SHEET_URL"]')
    key_path = Path(sys.argv[1]).expanduser()
    sheet_url = sys.argv[2].strip() if len(sys.argv) == 3 else COE_SHEET_URL
    if not key_path.is_file():
        sys.exit(f"Key file not found: {key_path}")
    if "docs.google.com/spreadsheets" not in sheet_url:
        sys.exit("The second argument should be the Google Sheet link.")
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if key.get("type") != "service_account" or "private_key" not in key:
        sys.exit("This is not a service-account key file. Download a JSON key from the Keys tab.")

    lines = [f"sheet_url = {toml_string(sheet_url)}", "", "[gcp_service_account]"]
    lines += [f"{name} = {toml_string(str(value))}" for name, value in key.items()]
    target = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    target.parent.mkdir(exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    print(f"The sheet must be shared with this email as Editor: {key['client_email']}")


if __name__ == "__main__":
    main()
