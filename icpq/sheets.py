"""Read an uploaded company list: CSV (any delimiter/encoding) or Excel .xlsx. Standard library only.

-> CSV text (comma-separated, header first), which the rest of the app uses."""
import csv
import io
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _num(v):
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() and abs(f) < 1e15 else v
    except ValueError:
        return v


def xlsx_rows(data):
    """Rows of the sheet with the most rows (lists are usually the biggest sheet)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(f"{REL}Relationship")}
    best = []
    for sh in wb.findall("m:sheets/m:sheet", NS):
        target = rels.get(sh.get(f"{{{NS['r']}}}id"), "")
        path = "xl/" + target.lstrip("/").removeprefix("xl/")
        if path not in z.namelist():
            continue
        rows = []
        for row in ET.fromstring(z.read(path)).iter(f"{{{NS['m']}}}row"):
            cells = {}
            for c in row.findall("m:c", NS):
                t, v = c.get("t"), c.find("m:v", NS)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                elif v is not None:
                    val = v.text if t in ("str", "b", "e") else _num(v.text or "")
                else:
                    val = ""
                if c.get("r"):
                    cells[_col(c.get("r"))] = val
                else:
                    cells[len(cells)] = val
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        rows = [r for r in rows if any(str(x).strip() for x in r)]
        if len(rows) > len(best):
            best = rows
    return best


def to_csv_text(data, filename=""):
    name = (filename or "").lower()
    if name.endswith(".xls") and not name.endswith(".xlsx"):
        raise ValueError("Old Excel .xls files aren't supported. In Excel choose File → Save As → .xlsx (or .csv) and upload that.")
    if name.endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        try:
            rows = xlsx_rows(data)
        except (zipfile.BadZipFile, KeyError, ET.ParseError):
            raise ValueError("This Excel file couldn't be read. Save it as .xlsx or .csv and try again.")
        if not rows:
            raise ValueError("The spreadsheet is empty.")
        width = max(len(r) for r in rows)
        buf = io.StringIO()
        csv.writer(buf).writerows([r + [""] * (width - len(r)) for r in rows])
        return buf.getvalue()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
