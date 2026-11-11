"""Step 4: build print-ready PDF volumes.

    python build.py 1            build volume 1
    python build.py all          build every volume not yet marked done
    python build.py all --force  rebuild everything
    python build.py sample       build the layout sample (build/sample)

Pipeline per volume
  1. convert every article of the volume to print HTML (convert.py)
  2. render the body with headless Chrome            -> body.pdf
  3. read the page of every article / section anchor from the PDF
  4. render the front matter + table of contents with those page numbers
  5. merge, turn TOC entries into links, write bookmarks, stamp running
     headers, page numbers and code-continuation marks (PyMuPDF)
State is recorded in manifest/build_state.json so `all` resumes after an
interruption.
"""
import datetime
import html
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

import pymupdf as fitz

import bcd
from common import BUILD, DATA, MANIFEST_DIR, OUT, SCRIPTS, SITE, load_json, save_json
from convert import Converter

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
MM = 72 / 25.4
TOP, BOTTOM, INNER, OUTER = 19 * MM, 17 * MM, 22 * MM, 17 * MM
FONT_DIR = r"C:\Windows\Fonts"
FONTS = {"hr": "segoeui.ttf", "hb": "seguisb.ttf", "hi": "segoeuii.ttf"}
STATE = os.path.join(MANIFEST_DIR, "build_state.json")
TOTAL_VOLS = 9
BAR = (0x59 / 255,) * 3            # colour of the code block's left bar (see print.css)


def chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("No Chrome/Edge found; edit CHROME_CANDIDATES in build.py")


def chrome_pdf(html_path, pdf_path):
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    cmd = [chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           "--disable-pdf-tagging", "--disable-extensions", "--no-first-run",
           "--user-data-dir=" + os.path.join(BUILD, "chrome-profile"),
           "--allow-file-access-from-files",
           "--print-to-pdf=" + pdf_path,
           "file:///" + html_path.replace("\\", "/")]
    subprocess.run(cmd, check=False, capture_output=True, timeout=7200)
    if not os.path.exists(pdf_path):
        raise RuntimeError("Chrome produced no PDF for " + html_path)


def css():
    with open(os.path.join(SCRIPTS, "print.css"), encoding="utf-8") as f:
        return f.read()


def page_shell(title, body_class, inner):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}'
            f'</title><style>{css()}</style></head><body class="{body_class}">{inner}</body></html>')


def plain(html_text):
    return html.unescape(re.sub(r"<[^>]+>", "", html_text or "")).strip()


# --------------------------------------------------------------------------
def build_body(vol, arts, conv, wdir):
    parts, toc, stats_all = [], [], {}
    for a in arts:
        h, st = conv.article(a)
        parts.append(h)
        stats_all[a["key"]] = dict(st)
        toc.append({"type": "art", "level": a["level"], "title": a["title"], "anchor": a["key"]})
        idmap = conv.ids(a["path"])
        for sec in conv.doc(a["path"])["body"]:
            v = sec["value"]
            if v.get("title") and not v.get("isH3") and v.get("id"):
                toc.append({"type": "sec", "level": a["level"] + 1, "title": plain(v["title"]),
                            "anchor": idmap[html.unescape(v["id"])], "of": a["key"]})
    idx = ['<div id="anchor-index-top" style="height:12pt"></div><a href="#anchor-index-top">i</a>']
    idx += [f'<a href="#{t["anchor"]}">{i}</a>' for i, t in enumerate(toc)]
    inner = (f'<div id="body">{"".join(parts)}</div>'
             f'<div id="anchor-index">{" ".join(idx)}</div>')
    path = os.path.join(wdir, "body.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page_shell(vol["title"], vol.get("body_class", "ref"), inner))
    return path, toc, stats_all


def read_anchors(pdf_path, toc):
    doc = fitz.open(pdf_path)
    names = doc.resolve_names()
    if "anchor-index-top" not in names:
        raise RuntimeError("anchor index not found in body PDF")

    def locate(d):
        """(0-based page, distance from page top).  Chrome reports destinations in the
        coordinates of the page's content box; a target sitting exactly on a page boundary
        is reported at the bottom edge of the previous page, which is normalised here."""
        pno = d["page"]
        h = doc[pno].rect.height
        y = h - d["to"][1] + TOP
        if y >= h - BOTTOM - 1.5 and pno + 1 < len(doc):
            return pno + 1, TOP
        return pno, y

    n_body = locate(names["anchor-index-top"])[0]
    missing = []
    for t in toc:
        d = names.get(t["anchor"])
        if d is None or locate(d)[0] >= n_body:
            missing.append(t["anchor"])
            continue
        t["bpage"], y = locate(d)                                # 0-based page in body
        t["y"] = round(y, 1)                                     # distance from page top
    doc.close()
    if missing:
        raise RuntimeError(f"{len(missing)} anchors missing from PDF, e.g. {missing[:5]}")
    return n_body


# --------------------------------------------------------------------------
LEGEND = """
<h2>How to read this book</h2>
<ul>
<li><b>Text.</b> Article wording, headings, section order, notes, tables and code are MDN's, taken
programmatically from MDN's rendered pages. Only the layout was changed for paper.</li>
<li><b>Dashed boxes in italics starting with ▷</b> and the small grey lines under each article title
(breadcrumb, source URL, availability) are additions of this print edition, not MDN text.</li>
<li><b>Code</b> is printed character for character in a monospaced font. A line longer than about
92 characters wraps at the right edge and continues at the left edge of the code box; no characters
are added. Labels above a box give the language; <b>✗ bad example</b> and <b>✓ good example</b>
replace MDN's red/green colouring. “code continues” / “code continued” in the page margin mark a
code box that runs over a page break.</li>
<li><b>Interactive examples and live samples</b> cannot run on paper. Their source code is printed;
output is shown only where MDN's source states it (for example in <code>// Expected output</code>
comments).</li>
@@ROTATED@@<li><b>Links.</b> Dotted underlines mark links. In the PDF, links to articles in this volume jump to
them; all other links open the MDN page. Web API, DOM, HTML/CSS, Glossary and Learn pages are outside
the scope of this collection (only <code>/en-US/docs/Web/JavaScript/</code> is included) and remain
links to MDN.</li>
<li><b>Badges</b> such as <span class="badge">Deprecated</span> <span class="badge">Experimental</span>
<span class="badge">Non-standard</span> <span class="badge">Optional</span> reproduce MDN's status
icons and labels as text.</li>
<li><b>Browser compatibility tables</b> are rebuilt from MDN's browser-compat-data (the data the
website's tables are generated from). Each cell gives the first browser version that supports the
feature. <b>No</b> (grey cell) = not supported; <b>?</b> = unknown; <b>a–b</b> = supported from
version a, removed in version b (grey cell); <b>Prev.</b> = only in a preview release of that browser; ≤ = that
version or earlier; small raised numbers refer to the numbered notes below the table (flags,
prefixes, partial support and other remarks).</li>
<li><b>“Baseline” availability lines</b> are condensed from the Baseline status MDN shows at the top
of a page.</li>
</ul>
"""


ROTATED_NOTE = """<li><b>Very wide tables</b> (eight or more columns) are printed turned a quarter turn on a
page of their own; turn the book to read them.</li>
"""


def front_html(vol, toc, n_front, meta, sections_in_toc):
    v = vol
    rows = []
    for t in toc:
        if t["type"] == "sec" and not sections_in_toc:
            continue
        pg = t.get("bpage")
        num = "000" if pg is None or n_front is None else str(pg + 1 + n_front)
        cls = f'l{min(t["level"], 3)}' if t["type"] == "art" else \
            ("sec s2" if t["level"] > 2 else "sec")
        rows.append(f'<a class="{cls}" href="https://toc.invalid/#{t["anchor"]}"><span class="t">'
                    f'{html.escape(t["title"])}</span><span class="dots"></span>'
                    f'<span class="p">{num}</span></a>')
    n_art = sum(1 for t in toc if t["type"] == "art")
    sample = v.get("sample")
    head = f"""
<div class="front">
<h1>MDN JavaScript Documentation</h1>
<p class="vol">{'Layout sample' if sample else f'Volume {v["id"]} of {TOTAL_VOLS}'} — {html.escape(v['title'])}</p>
<p><b>Unofficial print compilation.</b> {html.escape(v.get('blurb') or '')}
This volume contains {n_art} MDN articles, reproduced without changes to their wording.</p>
<div class="rule"></div>
<h2>Source, attribution and licence</h2>
<p>All articles in this volume are from <b>MDN Web Docs</b>, <code>{SITE}/en-US/docs/Web/JavaScript</code>,
retrieved on <b>{meta['retrieved']}</b> from MDN's rendered pages. They are written
<b>by Mozilla Contributors</b> and licensed under the Creative Commons Attribution-ShareAlike
licence, <b>CC-BY-SA 2.5</b> or any later version
(<code>https://creativecommons.org/licenses/by-sa/2.5/</code>). The title and the URL of the specific
MDN page are printed at the head of every article; the list of authors of a page is available through
that page on MDN. Code samples added to MDN on or after 20 August 2010 are in the public domain
(<b>CC0</b>, <code>https://creativecommons.org/publicdomain/zero/1.0/</code>); older samples are under
the MIT licence. Browser compatibility data is from <code>@mdn/browser-compat-data</code>
{meta['bcd']} (CC0).</p>
<p><b>Modifications.</b> This is not an official MDN or Mozilla publication and is not endorsed by
Mozilla. The content was re-laid-out for A4 paper: website navigation, banners and interactive
widgets were removed or replaced by short print notes; compatibility and specification tables,
which the website generates from data, were re-rendered from the same data; in-volume links were
turned into PDF links. Wording, code and section order were not edited. Like the original, this
compilation is distributed under CC-BY-SA 2.5 or later. “MDN” and “Mozilla” are trademarks of the
Mozilla Foundation; its logos and website design are not part of the licensed content and are not
used here.</p>
{LEGEND.replace('@@ROTATED@@', ROTATED_NOTE if v.get('has_rotated') else '')}
</div>
<div class="toc-title">Contents</div>
<div class="toc {'' if sections_in_toc else 'cols2'}">{''.join(rows)}</div>
"""
    return page_shell(v["title"], "front-matter", head)


# --------------------------------------------------------------------------
EDGE = (0x9a / 255,) * 3           # colour of the code block's thin border


def code_fragments(page):
    """Code-box fragments on a page: [(y0, y1, closed_top, closed_bottom)].

    A fragment is recognised by its dark left bar.  The thin top / bottom border is only
    drawn where the box really starts / ends, so a missing border means the box is cut
    by the page break."""
    bars, rules = [], []
    try:
        drawings = page.get_drawings()
    except Exception:
        return []
    for d in drawings:
        fill = d.get("fill")
        if not fill or len(fill) != 3:
            continue
        r = d["rect"]
        if max(abs(fill[i] - BAR[i]) for i in range(3)) < 0.02 and 1.0 <= r.width <= 3.2                 and r.height > 6:
            bars.append(r)
        elif max(abs(fill[i] - EDGE[i]) for i in range(3)) < 0.02 and r.height < 1.3                 and r.width > 25:
            rules.append(r)
    out = []
    for b in bars:
        top = any(abs(h.y0 - b.y0) < 1.6 and h.x0 < b.x0 + 4 and h.x1 > b.x0 + 20 for h in rules)
        bot = any(abs(h.y1 - b.y1) < 1.6 and h.x0 < b.x0 + 4 and h.x1 > b.x0 + 20 for h in rules)
        out.append((b.y0, b.y1, top, bot))
    return out


def stamp(doc, vol, n_front, arts_pos, meta):
    fonts = {k: os.path.join(FONT_DIR, f) for k, f in FONTS.items()}
    fobj = {k: fitz.Font(fontfile=p) for k, p in fonts.items()}
    grey, black = (0.25, 0.25, 0.25), (0, 0, 0)
    left_head = f"MDN JavaScript · Vol. {vol['id']} · {vol['title']}" if not vol.get("sample") \
        else "MDN JavaScript · layout sample"
    cont = []                       # pages (0-based) whose code box continues on the next page
    n = len(doc)
    frags = {}
    for pno in range(n_front, n):
        frags[pno] = code_fragments(doc[pno])
    for pno in range(n_front, n - 1):
        page, nxt = doc[pno], doc[pno + 1]
        bottom = page.rect.height - BOTTOM
        # a bar that reaches the bottom of the text area, followed by one that starts at the
        # very top of the next page, is one code box split over the page break
        a = [f for f in frags[pno] if f[1] >= bottom - 3.0 and not f[3]]
        b = [f for f in frags[pno + 1] if f[0] <= TOP + 3.0 and not f[2]]
        if a and b:
            cont.append(pno)
    for pno in range(n):
        if pno == 0:
            continue
        page = doc[pno]
        W, H = page.rect.width, page.rect.height
        num = pno + 1
        right = num % 2 == 1
        landscape = W > H
        if landscape:
            xl, xr = 17 * MM, W - 17 * MM
        else:
            xl, xr = (INNER, W - OUTER) if right else (OUTER, W - INNER)
        for k, p in fonts.items():
            page.insert_font(fontname=k, fontfile=p)
        y_head = (TOP if not landscape else 22 * MM) - 6.2 * MM
        # header text
        if pno < n_front:
            title = "Contents and notes"
        else:
            title = ""
            for (p, y, t) in arts_pos:
                if p < pno or (p == pno and y <= TOP + 22 * MM):
                    title = t
                else:
                    break
            if not title and arts_pos:
                title = arts_pos[0][2]
        text = title if right else left_head
        fs = 8.2
        f = fobj["hi" if right else "hr"]
        maxw = xr - xl
        while f.text_length(text, fs) > maxw and len(text) > 8:
            text = text[:-2].rstrip() + "…"
        tw = f.text_length(text, fs)
        x = xr - tw if right else xl
        page.insert_text((x, y_head), text, fontname="hi" if right else "hr", fontsize=fs, color=grey)
        page.draw_line((xl, y_head + 3.2), (xr, y_head + 3.2), color=(0.45, 0.45, 0.45), width=0.4)
        # page number, outer corner
        s = str(num)
        fw = fobj["hb"].text_length(s, 9.5)
        y_foot = H - 8.2 * MM
        page.insert_text((xr - fw if right else xl, y_foot), s, fontname="hb", fontsize=9.5, color=black)
        # code continuation marks
        if pno in cont:
            s = "(code continues on the next page)"
            w = fobj["hi"].text_length(s, 7)
            page.insert_text((xr - w, H - BOTTOM + 10.5), s, fontname="hi", fontsize=7, color=grey)
        if pno - 1 in cont:
            s = "(code continued from the previous page)"
            page.insert_text((xl, TOP - 5), s, fontname="hi", fontsize=7, color=grey)
    return cont


def build_volume(vol, manifest, conv, force=False):
    name = "sample" if vol.get("sample") else f"vol{vol['id']:02d}"
    wdir = os.path.join(BUILD, name)
    os.makedirs(wdir, exist_ok=True)
    arts = vol["articles"]
    meta = {"retrieved": manifest["inventory_retrieved"], "bcd": bcd.version()}
    print(f"[{name}] converting {len(arts)} articles", flush=True)
    body_html, toc, stats = build_body(vol, arts, conv, wdir)
    vol["has_rotated"] = any(st.get("rotated_tables") for st in stats.values())
    body_pdf = os.path.join(wdir, "body.pdf")
    print(f"[{name}] rendering body", flush=True)
    chrome_pdf(body_html, body_pdf)
    n_body = read_anchors(body_pdf, toc)
    sections_in_toc = vol["id"] == 1 or vol.get("sample")
    # front matter: first pass to learn its length, second pass with page numbers
    front_html_path = os.path.join(wdir, "front.html")
    front_pdf = os.path.join(wdir, "front.pdf")
    with open(front_html_path, "w", encoding="utf-8") as f:
        f.write(front_html(vol, toc, None, meta, sections_in_toc))
    chrome_pdf(front_html_path, front_pdf)
    d = fitz.open(front_pdf)
    n1 = len(d)
    d.close()
    n_front = n1 + (n1 % 2)                 # body must start on a right-hand (odd) page
    with open(front_html_path, "w", encoding="utf-8") as f:
        f.write(front_html(vol, toc, n_front, meta, sections_in_toc))
    chrome_pdf(front_html_path, front_pdf)
    front = fitz.open(front_pdf)
    if len(front) != n1:
        raise RuntimeError("front matter changed length between passes")
    # ---- assemble ---------------------------------------------------------
    doc = fitz.open(body_pdf)
    doc.delete_pages(from_page=n_body, to_page=len(doc) - 1)
    doc.insert_pdf(front, start_at=0)
    if n_front != n1:
        r = doc[0].rect
        doc.new_page(pno=n1, width=r.width, height=r.height)
    front.close()
    for t in toc:
        t["page"] = t["bpage"] + n_front + 1          # printed page number (1-based)
    by_anchor = {t["anchor"]: t for t in toc}
    n_links = 0
    for pno in range(n1):
        page = doc[pno]
        for l in page.get_links():
            uri = l.get("uri") or ""
            if uri.startswith("https://toc.invalid/#"):
                t = by_anchor[uri.split("#", 1)[1]]
                page.delete_link(l)
                if l["from"].height < 3:        # sliver left behind when an entry moved to
                    continue                    # the next page/column: not a real link area
                page.insert_link({"kind": fitz.LINK_GOTO, "from": l["from"], "page": t["page"] - 1,
                                  "to": fitz.Point(0, max(0, t["y"] - 12))})
                n_links += 1
    outline = [[1, "Title, licence and contents", 1]]
    for t in toc:
        lvl = min(t["level"], 4)
        outline.append([lvl, t["title"], t["page"],
                        {"kind": fitz.LINK_GOTO, "page": t["page"] - 1,
                         "to": fitz.Point(0, max(0, t["y"] - 12))}])
    # outline levels may not skip
    prev = 0
    for o in outline:
        if o[0] > prev + 1:
            o[0] = prev + 1
        prev = o[0]
    doc.set_toc(outline, collapse=1)
    arts_pos = [(t["page"] - 1, t["y"], t["title"]) for t in toc if t["type"] == "art"]
    cont = stamp(doc, vol, n_front, arts_pos, meta)
    doc.set_metadata({
        "title": f"MDN JavaScript Documentation — "
                 + ("Layout sample" if vol.get("sample") else f"Vol. {vol['id']}: {vol['title']}"),
        "author": "Mozilla Contributors (MDN Web Docs); unofficial print compilation",
        "subject": f"Print compilation of {SITE}/en-US/docs/Web/JavaScript, retrieved "
                   f"{meta['retrieved']}. CC-BY-SA 2.5 or later.",
        "keywords": "JavaScript, MDN, reference, print",
        "creator": "mdn-js-print (Chrome headless + PyMuPDF)",
    })
    out_pdf = os.path.join(OUT if not vol.get("sample") else wdir, vol["file"])
    tmp = out_pdf + ".tmp"
    doc.subset_fonts()
    doc.save(tmp, garbage=3, deflate=True)
    n_pages = len(doc)
    doc.close()
    os.replace(tmp, out_pdf)
    info = {
        "volume": vol["id"], "title": vol["title"], "file": vol["file"], "pages": n_pages,
        "front_pages": n_front, "body_pages": n_body, "sheets_duplex": (n_pages + 1) // 2,
        "articles": len(arts), "toc_links": n_links, "code_continuations": [p + 1 for p in cont],
        "built": datetime.datetime.now().isoformat(timespec="seconds"),
        "sections_in_toc": bool(sections_in_toc),
        "toc": toc, "stats": stats, "issues": list(conv.issues),
        "bytes": os.path.getsize(out_pdf),
    }
    save_json(os.path.join(wdir, "volume.json"), info)
    print(f"[{name}] done: {n_pages} pages ({n_front} front), {info['bytes'] / 1e6:.1f} MB, "
          f"{len(cont)} code boxes continue over a page break", flush=True)
    return info


SAMPLE_PATHS = [
    "/Guide/Grammar_and_types",
    "/Reference/Operators/Operator_precedence",
    "/Reference/Global_Objects/Array/map",
    "/Reference/Global_Objects/Error/stack",
    "/Reference/Global_Objects/Math/hypot",
    "/Guide/Closures",
    "/Reference/Global_Objects/Date/getYear",
    "/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat",
    "/Reference/Global_Objects/Promise",
]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    manifest = load_json(os.path.join(MANIFEST_DIR, "manifest.json"))
    conv = Converter(manifest)
    state = load_json(STATE, {})
    what = args[0] if args else "all"
    if what == "sample":
        pref = "/en-US/docs/Web/JavaScript"
        arts = [dict(conv.by_path[pref + p]) for p in (args[1:] or SAMPLE_PATHS)]
        for a in arts:
            a["volume"] = 0
        # sample articles link to each other internally
        conv.articles = arts
        conv.by_path = {a["path"]: a for a in arts}
        vol = {"id": 0, "title": "Layout sample", "file": "sample.pdf", "sample": True,
               "articles": arts, "body_class": "guide ref",
               "blurb": "Representative pages used to verify the print template."}
        build_volume(vol, manifest, conv, True)
        return
    ids = [v["id"] for v in manifest["volumes"]] if what == "all" else [int(x) for x in args]
    for vid in ids:
        vol = dict(next(v for v in manifest["volumes"] if v["id"] == vid))
        if what == "all" and not force and state.get(str(vid), {}).get("done"):
            print(f"[vol{vid:02d}] already built, skipping")
            continue
        vol["articles"] = [a for a in manifest["articles"] if a["volume"] == vid]
        vol["body_class"] = "guide" if vid == 1 else "ref"
        conv.issues = []
        info = build_volume(vol, manifest, conv, force)
        state[str(vid)] = {"done": True, "pages": info["pages"], "file": info["file"],
                           "built": info["built"]}
        save_json(STATE, state)


if __name__ == "__main__":
    main()
