"""Print rendering of MDN browser-compatibility tables.

On the website these tables are generated in the browser from the
@mdn/browser-compat-data package (BCD).  The article JSON only carries the
query key, so the table is rebuilt here from the same data release.  The
layout is a documented print restructuring: one row per feature, one narrow
column per browser, version numbers as text and all qualifiers (flags,
prefixes, partial support, notes) as numbered notes under the table - nothing
relies on colour or icons.
"""
import html
import os

from common import DATA, load_json

GROUPS = [
    ("Desktop", ["chrome", "edge", "firefox", "opera", "safari"]),
    ("Mobile", ["chrome_android", "firefox_android", "opera_android", "safari_ios",
                "samsunginternet_android", "webview_android", "webview_ios"]),
    ("Server", ["bun", "deno", "nodejs"]),
]
_bcd = None


def data():
    global _bcd
    if _bcd is None:
        _bcd = load_json(os.path.join(DATA, "bcd", "package", "data.json"))
    return _bcd


def version():
    return data()["__meta"]["version"]


def lookup(query):
    node = data()
    for part in query.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _rows(name, node, depth=0):
    if "__compat" in node:
        yield name, node["__compat"], depth
    for k, v in node.items():
        if k != "__compat" and isinstance(v, dict):
            yield from _rows(k, v, depth + 1)


def _ver(v):
    if v is False:
        return "No"
    if v is None:
        return "?"
    if v is True:
        return "Yes"
    if v == "preview":
        return "Prev."              # "Preview" does not fit the narrow browser columns
    return str(v)


def _cell_label(st):
    added = st.get("version_added")
    label = _ver(added)
    if st.get("version_removed") not in (None, False):
        label = f"{label}–{_ver(st['version_removed'])}"
    return label


def _statement_notes(st, primary):
    """Human-readable qualifiers of one support statement (HTML strings)."""
    out = []
    lead = "" if primary else f"Also from version {html.escape(_cell_label(st))}: "
    if st.get("prefix"):
        out.append(f"{lead}implemented with the vendor prefix <code>{html.escape(st['prefix'])}</code>.")
    if st.get("alternative_name"):
        out.append(f"{lead}uses the non-standard name <code>{html.escape(st['alternative_name'])}</code>.")
    for fl in st.get("flags") or []:
        kind = {"preference": "preference", "runtime_flag": "runtime flag"}.get(fl.get("type"), "flag")
        val = f" (set to <code>{html.escape(str(fl['value_to_set']))}</code>)" if fl.get("value_to_set") else ""
        out.append(f"{lead}disabled by default; the user must enable the {kind} "
                   f"<code>{html.escape(fl.get('name', ''))}</code>{val}.")
    if st.get("partial_implementation"):
        out.append(f"{lead}partial support.")
    notes = st.get("notes")
    if isinstance(notes, str):
        notes = [notes]
    for n in notes or []:
        out.append(lead + n)            # BCD notes are HTML
    if not primary and not out:
        out.append(f"{lead}supported.")
    return [t[:1].upper() + t[1:] for t in out]


def render(query, key):
    """Return (html, n_feature_rows) for one compatibility query, or (None, 0)."""
    node = lookup(query)
    if node is None or not any(True for _ in _rows("", node)):
        return None, 0
    browsers = data()["browsers"]
    notes, note_no = [], {}

    def ref(text):
        if text not in note_no:
            notes.append(text)
            note_no[text] = len(notes)
        return note_no[text]

    cols = [b for _, bs in GROUPS for b in bs]
    head = ['<thead><tr class="grp"><th rowspan="2" class="feat">Feature</th>']
    for g, bs in GROUPS:
        head.append(f'<th colspan="{len(bs)}">{g}</th>')
    head.append("</tr><tr class=\"br\">")
    for b in cols:
        head.append(f'<th><span>{html.escape(browsers[b]["name"])}</span></th>')
    head.append("</tr></thead>")
    body = []
    n = 0
    root_name = query.split(".")[-1]
    for name, compat, depth in _rows(root_name, node):
        n += 1
        label = compat.get("description") or f"<code>{html.escape(name)}</code>"
        status = compat.get("status") or {}
        tags = []
        if status.get("experimental"):
            tags.append("Experimental")
        if status.get("deprecated"):
            tags.append("Deprecated")
        if status.get("standard_track") is False:
            tags.append("Non-standard")
        tagh = "".join(f' <span class="badge">{t}</span>' for t in tags)
        tr = [f'<tr><th class="feat d{min(depth, 3)}">{label}{tagh}</th>']
        for b in cols:
            st = compat["support"].get(b)
            if st is None:
                tr.append('<td class="unk">?</td>')
                continue
            sts = st if isinstance(st, list) else [st]
            first = sts[0]
            refs = []
            for i, s in enumerate(sts):
                for txt in _statement_notes(s, i == 0):
                    r = ref(txt)
                    if r not in refs:
                        refs.append(r)
            label_txt = html.escape(_cell_label(first))
            cls = "no" if first.get("version_added") is False or \
                first.get("version_removed") not in (None, False) else \
                ("unk" if first.get("version_added") is None else "yes")
            sup = f'<sup>{",".join(map(str, refs))}</sup>' if refs else ""
            tr.append(f'<td class="{cls}">{label_txt}{sup}</td>')
        tr.append("</tr>")
        body.append("".join(tr))
    out = [f'<div class="bcd" data-gen="bcd" data-query="{html.escape(query)}">',
           '<table class="bcdt">', "".join(head), "<tbody>", "".join(body), "</tbody></table>"]
    if notes:
        out.append('<ol class="bcd-notes">')
        out += [f"<li>{t}</li>" for t in notes]
        out.append("</ol>")
    out.append(f'<p class="bcd-src">Compatibility data: MDN browser-compat-data {version()}, '
               f'<code>{html.escape(query)}</code>. Numbers are the first version with support; '
               f'see “How to read this book” for the full legend.</p></div>')
    return "".join(out), n
