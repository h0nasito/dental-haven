"""Read a simple table from an uploaded CSV or Excel (.xlsx) file, without extra packages.

Returns a list of dicts keyed by the header row (lower-cased, trimmed). Only the first worksheet is read.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MAX_ROWS = 2000


class SheetError(ValueError):
    pass


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "A").group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _xlsx_rows(data: bytes) -> list[list[str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SheetError("That file isn't a valid Excel (.xlsx) file.") from exc
    with zf:
        names = zf.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        sheet = "xl/worksheets/sheet1.xml" if "xl/worksheets/sheet1.xml" in names else \
            next((n for n in sorted(names) if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")), None)
        if not sheet:
            raise SheetError("The Excel file has no worksheet.")
        root = ET.fromstring(zf.read(sheet))
        rows = []
        for r in root.iter(f"{{{NS['m']}}}row"):
            cells = {}
            for c in r.findall("m:c", NS):
                kind, v = c.get("t"), c.find("m:v", NS)
                if kind == "s" and v is not None:
                    val = shared[int(v.text)] if v.text and int(v.text) < len(shared) else ""
                elif kind == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                else:
                    val = v.text if v is not None and v.text else ""
                cells[_col_index(c.get("r"))] = val.strip()
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            if len(rows) > MAX_ROWS + 1:
                raise SheetError(f"The file has more than {MAX_ROWS} rows.")
        return rows


def _csv_rows(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SheetError("Couldn't read the CSV file. Save it as CSV UTF-8 and try again.")
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text))]
    if len(rows) > MAX_ROWS + 1:
        raise SheetError(f"The file has more than {MAX_ROWS} rows.")
    return rows


def read_table(filename: str, data: bytes) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        rows = _xlsx_rows(data)
    elif name.endswith(".csv") or name.endswith(".txt"):
        rows = _csv_rows(data)
    elif name.endswith(".xls"):
        raise SheetError("Old Excel (.xls) files can't be read. In Excel, use File → Save As → Excel Workbook (.xlsx) or CSV.")
    else:
        raise SheetError("Upload an Excel (.xlsx) or CSV file.")
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        raise SheetError("The file is empty.")
    header = [" ".join(h.lower().split()) for h in rows[0]]
    return [{header[i]: (r[i] if i < len(r) else "") for i in range(len(header)) if header[i]} for r in rows[1:]]
