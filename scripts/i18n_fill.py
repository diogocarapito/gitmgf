"""Write the EN catalogue from the template plus a {msgid-json: translation} mapping.

Usage: python scripts/i18n_fill.py MAPPING.json  (maintenance helper; day-to-day, edit messages.po directly)
"""

import json
import sys
from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.pofile import read_po, write_po

ROOT = Path(__file__).resolve().parents[1]
POT = ROOT / "app" / "locales" / "messages.pot"
PO = ROOT / "app" / "locales" / "en" / "LC_MESSAGES" / "messages.po"


def key(msgid: object) -> str:
    return json.dumps(tuple(msgid) if isinstance(msgid, (list, tuple)) else msgid, ensure_ascii=False)


def main(mapping_path: str) -> None:
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    existing = {}
    if PO.exists():
        with PO.open("rb") as f:
            for m in read_po(f):
                if m.id and m.string:
                    existing[key(m.id)] = list(m.string) if isinstance(m.string, tuple) else m.string
    with POT.open("rb") as f:
        template = read_po(f)
    catalog = Catalog(locale="en", domain="messages", project="gitmgf", fuzzy=False)
    missing = []
    for m in template:
        if not m.id:
            continue
        value = mapping.get(key(m.id), existing.get(key(m.id)))
        if value is None:
            missing.append(m.id)
            continue
        catalog.add(m.id, tuple(value) if isinstance(value, list) else value, auto_comments=m.auto_comments)
    PO.parent.mkdir(parents=True, exist_ok=True)
    with PO.open("wb") as f:
        write_po(f, catalog, width=0, sort_output=True, omit_header=False)
    print(f"wrote {len(catalog)} entries; missing {len(missing)}")
    for m in missing:
        print("  missing:", m)


if __name__ == "__main__":
    main(sys.argv[1])
