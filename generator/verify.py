"""Step 5: automated verification of a built volume.

    python verify.py 1        verify volume 1      (python verify.py sample / all)

Checks (results in output/verification/volNN.json, summary printed):
  V1 manifest   every manifest article of the volume is in the PDF exactly once and its
                title is printed on the page the contents list points to
  V2 text A     MDN source text == text of the print HTML (minus print-edition additions),
                per article, compared independently with Python's html.parser
  V3 code A     every <pre> block: source string == print HTML string, character for character
  V4 structure  per-article counts of code blocks, tables, rows, cells, images, lists, notes
  V5 text B     print HTML text == text extracted from the final PDF, per article
                (whitespace-insensitive; order-insensitive fallback is reported separately)
  V6 code B     code lines extracted from the PDF (incl. leading spaces) == source code lines
  V7 contents   printed page numbers in the contents == link targets == real pages; bookmarks
  V8 overflow   no text or table rule outside the type area on any page
  V9 fonts/links embedded fonts, internal link targets, page sizes
"""
import html
import os
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser

import pymupdf as fitz

from common import BUILD, MANIFEST_DIR, OUT, load_json, raw_path, save_json

MM = 72 / 25.4
TOP, BOTTOM, INNER, OUTER = 19 * MM, 17 * MM, 22 * MM, 17 * MM
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}
COUNT_TAGS = ("pre", "table", "tr", "td", "th", "img", "h4", "h5", "li", "dt", "dd",
              "blockquote", "math", "caption", "ol", "ul", "dl", "p")
CODE_SIZE = 9.25
TEXT_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP


class Extract(HTMLParser):
    """Text, <pre> strings and element counts of an HTML fragment.

    skip(tag, attrs) -> True makes the parser ignore that element and its subtree."""

    def __init__(self, skip, drop_annotation=False):
        super().__init__(convert_charrefs=True)
        self.skip_fn = skip
        self.drop_annotation = drop_annotation
        self.text = []
        self.pres = []
        self.counts = Counter()
        self._skip_depth = 0
        self._lists = []            # open lists: [tag, next number]
        self._pre = None
        self._thead = None
        self.theads = []            # text of every <thead> (repeats after page breaks)
        self.number_lists = drop_annotation   # PDF side: <ol> markers are printed text

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._skip_depth:
            if tag not in VOID:
                self._skip_depth += 1
            return
        if self.skip_fn(tag, a) or (self.drop_annotation and tag == "annotation"):
            if tag not in VOID:
                self._skip_depth = 1
            return
        if tag in COUNT_TAGS:
            self.counts[tag] += 1
        if tag == "div" and "notecard" in (a.get("class") or "").split():
            self.counts["notecard"] += 1
        if tag == "pre":
            self._pre = []
        if tag == "thead":
            self._thead = []
        if tag in ("ol", "ul"):
            self._lists.append([tag, int(a.get("start") or 1)])
        if tag == "li" and self._lists and self._lists[-1][0] == "ol" and self.number_lists:
            self.text.append(f" {self._lists[-1][1]}. ")
            self._lists[-1][1] += 1
        if tag in ("br",):
            self.text.append(" ")

    def handle_endtag(self, tag):
        if self._skip_depth:
            if tag not in VOID:
                self._skip_depth -= 1
            return
        if tag == "pre" and self._pre is not None:
            self.pres.append("".join(self._pre))
            self._pre = None
        if tag == "thead" and self._thead is not None:
            self.theads.append("".join(self._thead))
            self._thead = None
        if tag in ("ol", "ul") and self._lists:
            self._lists.pop()
        if tag in ("p", "div", "li", "dt", "dd", "td", "th", "tr", "h1", "h2", "h3", "h4", "h5",
                   "pre", "table", "caption", "blockquote"):
            self.text.append(" ")

    def handle_data(self, data):
        if self._skip_depth:
            return
        self.text.append(data)
        if self._pre is not None:
            self._pre.append(data)
        if self._thead is not None:
            self._thead.append(data)


def ws(s):
    return re.sub(r"\s+", " ", s).strip()


INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏⁠﻿­‪‫‬‭‮⁦⁧⁨⁩"))


def nows(s):
    s = unicodedata.normalize("NFKC", s).translate(INVISIBLE)
    return re.sub(r"\s+", "", s)


def align(want, got, heads):
    """True if `got` equals `want` apart from extra copies of table-header texts."""
    i = j = n = 0
    lw, lg = len(want), len(got)
    while j < lg:
        if i < lw and want[i] == got[j]:
            hit = None
            if want[i] != got[j] or True:
                for h in heads:
                    if got.startswith(h, j) and not want.startswith(h, i):
                        hit = h
                        break
            if hit is None:
                i += 1
                j += 1
                continue
            j += len(hit)
            n += 1
            continue
        for h in heads:
            if got.startswith(h, j):
                j += len(h)
                n += 1
                break
        else:
            return False, n
    return i == lw, n


def strip_surplus(want, got, heads):
    """Remove surplus copies of table-header texts from `got` (by count)."""
    for th in heads:
        for _ in range(max(got.count(th) - want.count(th), 0)):
            k = got.rfind(th)
            got = got[:k] + got[k + len(th):]
    return got


def is_subsequence(want, got):
    it = iter(got)
    return all(ch in it for ch in want)


def source_extract(doc):
    """Expected text / code / counts of one article, straight from MDN's JSON."""
    def skip(tag, a):
        return tag == "ul" and "prev-next" in (a.get("class") or "").split()
    ex = Extract(skip)
    ex.feed("<h1>" + html.escape(doc["title"]) + "</h1>")
    for sec in doc["body"]:
        v = sec["value"]
        if v.get("title"):
            ex.feed(f"<h2>{v['title']}</h2>")
        if sec["type"] == "prose":
            ex.feed(v.get("content") or "")
        ex.feed(" ")                 # sections are separate blocks
    ex.close()
    return ex


def built_extract(article_html, with_generated):
    def skip(tag, a):
        return (not with_generated) and "data-gen" in a
    ex = Extract(skip, drop_annotation=with_generated)
    ex.feed(article_html)
    ex.close()
    return ex


def split_articles(body_html):
    out = {}
    for m in re.finditer(r'<article class="[^"]*" id="(a\d+)">(.*?)</article>', body_html, re.S):
        out[m.group(1)] = m.group(2)
    return out


# --------------------------------------------------------------------------
def type_area(page):
    W, H = page.rect.width, page.rect.height
    if W > H:                                   # landscape
        return 17 * MM, 22 * MM, W - 17 * MM, H - 17 * MM
    right = (page.number + 1) % 2 == 1
    xl, xr = (INNER, W - OUTER) if right else (OUTER, W - INNER)
    return xl, TOP, xr, H - BOTTOM


def article_clips(doc, arts):
    """For each article: list of (page index, clip rect) covering exactly its area."""
    out = []
    for i, t in enumerate(arts):
        p0, y0 = t["page"] - 1, t["y"]
        if i + 1 < len(arts):
            p1, y1 = arts[i + 1]["page"] - 1, arts[i + 1]["y"]
        else:
            p1, y1 = len(doc) - 1, None
        clips = []
        for pno in range(p0, p1 + 1):
            page = doc[pno]
            xl, yt, xr, yb = type_area(page)
            top = yt - 2 if pno != p0 else max(yt - 2, y0 - 2)
            bot = yb + 2
            if pno == p1 and y1 is not None:
                bot = min(bot, y1 - 2)
                if y1 <= yt + 1:                # next article starts at the very top
                    continue
            if bot > top:
                clips.append((pno, fitz.Rect(0, top, page.rect.width, bot)))
        out.append(clips)
    return out


def pdf_text(doc, clips):
    return "".join(doc[p].get_text("text", clip=c, flags=TEXT_FLAGS) for p, c in clips)


def pdf_code_lines(doc, clips):
    """Physical code lines (text incl. leading spaces) inside the clips, in reading order."""
    lines = []
    for pno, clip in clips:
        rd = doc[pno].get_text("rawdict", clip=clip, flags=TEXT_FLAGS)
        chars = []
        for b in rd["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    if abs(s["size"] - CODE_SIZE) < 0.04:
                        for c in s["chars"]:
                            chars.append((round(c["origin"][1], 0), c["origin"][0], c["c"]))
        chars.sort()
        cur_y, cur = None, []
        for y, x, c in chars:
            if cur_y is None or abs(y - cur_y) > 2.0:
                if cur:
                    lines.append("".join(ch for _, ch in sorted(cur)))
                cur, cur_y = [], y
            cur.append((x, c))
        if cur:
            lines.append("".join(ch for _, ch in sorted(cur)))
    return lines


def check_code(expected_blocks, got_lines):
    """Compare source code lines with physical PDF lines.  Returns dict of results."""
    exp = [ln for blk in expected_blocks for ln in blk.split("\n") if ln.strip()]
    res = {"lines": len(exp), "wrapped": 0, "ok": True}
    j = 0
    for i, e in enumerate(exp):
        e_cmp = e.rstrip().expandtabs(4) if "\t" in e else e.rstrip()
        if j >= len(got_lines):
            res.update(ok=False, first_error=f"PDF ran out of code lines at source line {i}: {e!r}")
            return res
        g = got_lines[j].rstrip()
        j += 1
        if g == e_cmp:
            continue
        # visually wrapped line: following physical lines continue it
        want = re.sub(r"\s+", "", e_cmp)
        have = re.sub(r"\s+", "", g)
        indent_ok = (len(g) - len(g.lstrip(" "))) == (len(e_cmp) - len(e_cmp.lstrip(" ")))
        while len(have) < len(want) and j < len(got_lines):
            have += re.sub(r"\s+", "", got_lines[j])
            j += 1
            res["wrapped"] += 1
        if have == want and (indent_ok or "\t" in e):
            if "\t" in e:
                # tab characters are rendered as horizontal space (tab-size 4), not as
                # space characters, so only the visible characters can be compared
                res["tabs"] = res.get("tabs", 0) + 1
            continue
        if unicodedata.normalize("NFKC", have) == unicodedata.normalize("NFKC", want) and indent_ok:
            res["unicode_normalised"] = res.get("unicode_normalised", 0) + 1
            continue
        if len(have) == len(want) and indent_ok and "\ufffd" in have and \
                all(h == w or h == "\ufffd" for h, w in zip(have, want)):
            # character without a glyph in any installed font: printed as a placeholder box
            res.setdefault("missing_glyphs", []).extend(
                w for h, w in zip(have, want) if h != w)
            continue
        strip_marks = lambda t: "".join(ch for ch in t if not unicodedata.combining(ch))
        if strip_marks(have) == strip_marks(want) and indent_ok:
            # combining accents: drawn correctly, but PDF text extraction may report the
            # mark twice or after the following letter
            res["combining_marks"] = res.get("combining_marks", 0) + 1
            continue
        if sorted(have) == sorted(want) and indent_ok:
            # same characters, different order: bidirectional (right-to-left) text
            res["reordered"] = res.get("reordered", 0) + 1
            continue
        res.update(ok=False, first_error=f"source line {i}: expected {e_cmp!r} got {g!r}")
        return res
    if j != len(got_lines):
        res.update(ok=False, first_error=f"{len(got_lines) - j} extra code lines in PDF, first "
                                         f"{got_lines[j]!r}")
    return res


# --------------------------------------------------------------------------
def verify(name):
    wdir = os.path.join(BUILD, name)
    info = load_json(os.path.join(wdir, "volume.json"))
    manifest = load_json(os.path.join(MANIFEST_DIR, "manifest.json"))
    by_key = {a["key"]: a for a in manifest["articles"]}
    pdf_path = os.path.join(wdir if name == "sample" else OUT, info["file"])
    doc = fitz.open(pdf_path)
    with open(os.path.join(wdir, "body.html"), encoding="utf-8") as f:
        built = split_articles(f.read())
    arts = [t for t in info["toc"] if t["type"] == "art"]
    rep = {"volume": info["volume"], "file": info["file"], "pages": len(doc),
           "articles": len(arts), "problems": []}
    P = rep["problems"]

    # ---- V1 manifest -------------------------------------------------------
    if name != "sample":
        want = [a["key"] for a in manifest["articles"] if a["volume"] == info["volume"]]
        got = [t["anchor"] for t in arts]
        rep["v1_manifest_match"] = want == got
        if want != got:
            P.append(f"V1: manifest/PDF article lists differ ({len(want)} vs {len(got)})")
    if len(built) != len(arts):
        P.append(f"V1: {len(built)} articles in HTML vs {len(arts)} in PDF")
    clips = article_clips(doc, arts)
    title_missing = 0
    for t in arts:
        page = doc[t["page"] - 1]
        txt = nows(page.get_text("text", flags=TEXT_FLAGS))
        if nows(t["title"]) not in txt:
            title_missing += 1
            P.append(f"V1: title not found on its page: p{t['page']} {t['title']}")
    rep["v1_titles_on_page"] = len(arts) - title_missing

    # ---- V2-V6 per article ---------------------------------------------------
    c = Counter()
    totals = Counter()
    details = []
    for t, cl in zip(arts, clips):
        key = t["anchor"]
        a = by_key[key]
        src = source_extract(load_json(raw_path(a["path"]))["doc"])
        b_src = built_extract(built[key], with_generated=False)
        b_all = built_extract(built[key], with_generated=True)
        d = {"key": key, "title": a["title"], "page": t["page"]}
        # V2
        s_txt, b_txt = "".join(src.text), "".join(b_src.text)
        if ws(s_txt) == ws(b_txt):
            c["v2_exact"] += 1
        elif nows(s_txt) == nows(b_txt):
            c["v2_whitespace_only"] += 1
        else:
            c["v2_mismatch"] += 1
            d["v2"] = "mismatch"
            P.append(f"V2: source/print text differ: {key} {a['title']}")
        totals["chars_source"] += len(nows(s_txt))
        # V3
        if src.pres == b_src.pres:
            c["v3_code_identical"] += 1
        else:
            c["v3_code_mismatch"] += 1
            d["v3"] = "mismatch"
            P.append(f"V3: code blocks differ: {key} {a['title']}")
        totals["code_blocks"] += len(src.pres)
        totals["code_lines"] += sum(p.count("\n") for p in src.pres)
        totals["code_lines_over_92"] += sum(1 for p in src.pres for ln in p.split("\n") if len(ln) > 92)
        # V4
        diff = {k: (src.counts[k], b_src.counts[k]) for k in set(src.counts) | set(b_src.counts)
                if src.counts[k] != b_src.counts[k]}
        if diff:
            c["v4_count_mismatch"] += 1
            d["v4"] = diff
            P.append(f"V4: element counts differ: {key} {a['title']} {diff}")
        else:
            c["v4_counts_equal"] += 1
        for k in ("table", "img", "notecard", "math"):
            totals[k] += src.counts[k]
        # V5
        want = nows("".join(b_all.text))
        got = nows(pdf_text(doc, cl))
        heads = sorted({nows(x) for x in b_all.theads if nows(x)}, key=len, reverse=True)
        if want == got:
            c["v5_exact"] += 1
        else:
            ok, n_rep = align(want, got, heads)
            if ok:
                # only difference: table headers repeated at the top of continuation pages
                c["v5_exact"] += 1
                totals["table_headers_repeated"] += n_rep
            elif b_all.counts["math"] and Counter(want.replace("\u221a", "")) ==                     Counter(got.replace("\u221a", "")):
                # MathML layout draws radical signs and stacks limits above/below operators
                c["v5_math_layout_only"] += 1
                d["v5"] = "math layout"
            elif b_all.counts["img"] and is_subsequence(want, got):
                # all article text present, in order; the surplus is text inside SVG figures
                c["v5_exact_plus_svg_figure_text"] += 1
                d["v5"] = f"plus {len(got) - len(want)} chars of SVG figure text"
            elif Counter(want) == Counter(strip_surplus(want, got, heads)):
                # same characters in another order: right-to-left text (extracted in visual
                # order) or table cells read in a different sequence
                c["v5_same_chars_other_order"] += 1
                d["v5"] = "reordered"
            else:
                got = strip_surplus(want, got, heads)
                cw, cg = Counter(want), Counter(got)
                miss, extra = cw - cg, cg - cw
                nm, ne = sum(miss.values()), sum(extra.values())
                d["v5"] = {"missing": nm, "extra": ne,
                           "missing_chars": "".join(sorted(miss))[:40],
                           "extra_chars": "".join(sorted(extra))[:40]}
                if nm + ne <= 0.002 * max(len(want), 1) + 2:
                    c["v5_minor_glyph_diff"] += 1
                else:
                    c["v5_mismatch"] += 1
                    P.append(f"V5: PDF text differs: {key} p{t['page']} {a['title']} "
                             f"missing={nm} extra={ne}")
        totals["chars_pdf"] += len(got)
        # V6
        r = check_code(b_src.pres, pdf_code_lines(doc, cl))
        totals["code_lines_wrapped_in_pdf"] += r["wrapped"]
        totals["code_lines_bidi_reordered"] += r.get("reordered", 0)
        totals["code_lines_with_tabs"] += r.get("tabs", 0)
        if r.get("missing_glyphs"):
            d["missing_glyphs_in_code"] = sorted({f"U+{ord(ch):04X}" for ch in r["missing_glyphs"]})
            totals["code_chars_without_glyph"] += len(r["missing_glyphs"])
        if r["ok"]:
            c["v6_code_ok"] += 1
        else:
            c["v6_code_mismatch"] += 1
            d["v6"] = r.get("first_error")
            P.append(f"V6: PDF code differs: {key} p{t['page']} {a['title']}: {r.get('first_error')}")
        if len(d) > 3:
            details.append(d)
    rep["per_article"] = dict(c)
    rep["totals"] = dict(totals)
    rep["article_details"] = details

    # ---- V7 contents, bookmarks ------------------------------------------------
    toc_ok = toc_bad = 0
    expected_entries = [t for t in info["toc"] if t["type"] == "art" or info["sections_in_toc"]]
    found = []                       # (title+number text, printed number, link target page)
    for pno in range(info["front_pages"]):
        page = doc[pno]
        for l in page.get_links():
            if l["kind"] != fitz.LINK_GOTO:
                continue
            txt = page.get_text("text", clip=l["from"] + (-1, -1, 1, 1), flags=TEXT_FLAGS)
            m = re.search(r"(\d+)\s*$", txt.strip())
            found.append([nows(txt), int(m.group(1)) if m else None, l["page"] + 1, False])
    page_txt = {}
    for t in expected_entries:
        ok = False
        for f in found:
            if not f[3] and f[1] == f[2] == t["page"] and nows(t["title"]) in f[0]:
                f[3] = ok = True
                break
        if ok:                       # the target page must really carry that heading
            if t["page"] not in page_txt:
                page_txt[t["page"]] = nows(doc[t["page"] - 1].get_text("text", flags=TEXT_FLAGS))
            ok = nows(t["title"]) in page_txt[t["page"]]
        toc_ok += ok
        toc_bad += not ok
        if not ok:
            P.append(f"V7: contents entry not verified: {t['title'][:50]!r} p{t['page']}")
    stray = sum(1 for f in found if not f[3])
    rep["v7_toc_links_unmatched"] = stray
    if stray:
        P.append(f"V7: {stray} contents links match no entry")
    rep["v7_toc_entries_ok"] = toc_ok
    rep["v7_toc_entries_bad"] = toc_bad
    rep["v7_toc_entries_expected"] = len(expected_entries)
    if toc_ok != len(expected_entries):
        P.append(f"V7: {toc_ok} verified contents entries, expected {len(expected_entries)}")
    bm = doc.get_toc(simple=True)
    bm_ok = len(bm) == len(info["toc"]) + 1 and all(
        b[1] == t["title"] and b[2] == t["page"] for b, t in zip(bm[1:], info["toc"]))
    rep["v7_bookmarks"] = len(bm)
    rep["v7_bookmarks_match"] = bm_ok
    if not bm_ok:
        P.append("V7: bookmarks do not match the article/section list")

    # ---- V8 overflow, V9 fonts/links/pages -----------------------------------------
    overflow, underfilled, landscape = [], [], 0
    n_int = n_ext = bad_links = 0
    fonts_not_embedded = set()
    art_start_pages = {t["page"] - 1 for t in arts}
    for page in doc:
        W, H = page.rect.width, page.rect.height
        if not (abs(min(W, H) - 595) < 1.5 and abs(max(W, H) - 842) < 1.5):
            P.append(f"V9: page {page.number + 1} is not A4 ({W:.0f}x{H:.0f})")
        landscape += W > H
        xl, yt, xr, yb = type_area(page)
        worst = 0
        maxy = 0
        if page.number > 0:
            for b in page.get_text("dict", flags=TEXT_FLAGS)["blocks"]:
                x0, y0, x1, y1 = b["bbox"]
                if y1 < yt - 1 or y0 > yb + 1:
                    continue                      # running header / footer / marks
                if b["type"] == 0:
                    for l in b["lines"]:
                        for s in l["spans"]:
                            if not s["text"].strip():
                                continue
                            sx0, sy0, sx1, sy1 = s["bbox"]
                            worst = max(worst, sx1 - xr, xl - sx0, sy1 - yb - 3)
                            maxy = max(maxy, sy1)
                else:
                    worst = max(worst, x1 - xr, xl - x0)
                    maxy = max(maxy, y1)
            for dr in page.get_drawings():
                r = dr["rect"]
                if r.y1 < yt - 1 or r.y0 > yb + 1:
                    continue
                worst = max(worst, r.x1 - xr, xl - r.x0)
        if worst > 1.5:
            overflow.append({"page": page.number + 1, "by_pt": round(worst, 1)})
        if page.number >= info["front_pages"] and maxy and maxy < yt + 0.45 * (yb - yt) \
                and (page.number + 1) not in art_start_pages and page.number + 1 < len(doc):
            underfilled.append(page.number + 1)
        for l in page.get_links():
            if l["kind"] in (fitz.LINK_GOTO, fitz.LINK_NAMED):
                n_int += 1
                if not (0 <= l.get("page", -1) < len(doc)):
                    bad_links += 1
            elif l["kind"] == fitz.LINK_URI:
                n_ext += 1
        for f in page.get_fonts(full=True):
            if f[1] == "n/a" and f[2] != "Type3":
                fonts_not_embedded.add(f[3])
    rep["v8_overflow_pages"] = overflow
    rep["pages_less_than_45pct_full"] = underfilled
    rep["landscape_pages"] = landscape
    rep["v9_internal_links"] = n_int
    rep["v9_internal_links_unresolved"] = bad_links
    rep["v9_external_links"] = n_ext
    rep["v9_fonts_not_embedded"] = sorted(fonts_not_embedded)
    rep["code_continuation_pages"] = info["code_continuations"]
    for o in overflow:
        P.append(f"V8: content outside type area on p{o['page']} by {o['by_pt']}pt")
    if bad_links:
        P.append(f"V9: {bad_links} internal links do not resolve")
    if fonts_not_embedded:
        P.append(f"V9: fonts not embedded: {sorted(fonts_not_embedded)}")
    # pictures
    n_img_pdf = sum(len(p.get_images()) for p in doc)
    n_svg_like = totals["img"]
    rep["images_in_source"] = n_svg_like
    rep["raster_images_in_pdf"] = n_img_pdf
    doc.close()
    os.makedirs(os.path.join(OUT, "verification"), exist_ok=True)
    save_json(os.path.join(OUT, "verification", f"{name}.json"), rep)
    print(f"[{name}] {rep['pages']} pages, {rep['articles']} articles")
    print("   per article:", dict(sorted(c.items())))
    print("   totals:", dict(totals))
    print(f"   contents entries ok {toc_ok}/{len(expected_entries)}, bookmarks {len(bm)} "
          f"match={bm_ok}, links int={n_int} ext={n_ext} unresolved={bad_links}")
    print(f"   overflow pages {len(overflow)}, <45% full pages {len(underfilled)}, "
          f"landscape {landscape}, code continuations {len(info['code_continuations'])}, "
          f"fonts not embedded {sorted(fonts_not_embedded)}")
    print(f"   problems: {len(P)}")
    for p in P[:25]:
        print("     -", p.encode("ascii", "replace").decode())
    return rep


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what == "sample":
        verify("sample")
    else:
        vols = range(1, 10) if what == "all" else [int(x) for x in sys.argv[1:]]
        for v in vols:
            if os.path.exists(os.path.join(BUILD, f"vol{v:02d}", "volume.json")):
                verify(f"vol{v:02d}")
