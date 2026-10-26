"""CSV and XLSX exports (standard library only). Cells that a spreadsheet would run as a formula are neutralised."""
import csv
import hashlib
import io
import json
import zipfile
from xml.sax.saxutils import escape

from .icp.wizard import DEFAULT_EXPORT, EXPORT_COLUMNS
from .util import now

HEAD = dict(EXPORT_COLUMNS)


def safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not s[1:2].isdigit() else s


def flat(a):
    ea, aic = a.get("ea") or {}, a.get("aic") or {}
    return {**a, "eas": ea.get("s", ""), "ear": ea.get("r", ""), "eaq": ea.get("q", ""), "aics": aic.get("strength", ""),
            "aicq": aic.get("quote", ""), "aicu": aic.get("url", ""), "list": a.get("src") or a.get("list")}


def columns(cfg):
    cols = [c for c in ((cfg or {}).get("export", {}).get("columns") or DEFAULT_EXPORT) if c in HEAD]
    return cols or DEFAULT_EXPORT


def table(rows, cols, labels=None):
    head = [HEAD[c] for c in cols]
    if labels and labels.get("core"):
        head = [labels["core"].replace(" ", "_") if c == "sms" else h for c, h in zip(cols, head)]
    return head, [[safe(flat(a).get(c, "")) for c in cols] for a in rows]


def to_csv(rows, cols, labels=None):
    head, body = table(rows, cols, labels)
    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(head)
    w.writerows(body)
    return f.getvalue()


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def to_xlsx(rows, cols, labels=None, sheet="Accounts"):
    head, body = table(rows, cols, labels)
    out = io.BytesIO()
    xml_rows = []
    for ri, r in enumerate([head] + body, start=1):
        cells = "".join(f'<c r="{_col(ci)}{ri}" t="inlineStr"{" s=\"1\"" if ri == 1 else ""}><is><t xml:space="preserve">{escape(str(v)[:32000])}</t></is></c>'
                        for ci, v in enumerate(r))
        xml_rows.append(f'<row r="{ri}">{cells}</row>')
    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                 f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   f'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(sheet[:31])}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
                   '<cellXfs count="2"><xf fontId="0"/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>')
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return out.getvalue()


def manifest(files_map, cols, labels=None):
    m = {"generated": now(), "files": {}}
    for name, rows in files_map.items():
        body = to_csv(rows, cols, labels)
        m["files"][name + ".csv"] = {"rows": len(rows), "sha256": hashlib.sha256(body.encode()).hexdigest()}
    return json.dumps(m, indent=1)
