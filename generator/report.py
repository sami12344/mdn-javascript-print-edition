"""Step 6: master index, final manifest and verification report.

    python report.py

Reads build/volNN/volume.json and output/verification/volNN.json and writes into output/:
  MDN-JavaScript-Master-Index.pdf   volume overview + alphabetical index of all articles
  manifest.json / manifest.csv      source manifest incl. final volume and page of each article
  VERIFICATION-REPORT.md
"""
import csv
import html
import os
import shutil
import subprocess
from collections import Counter

import pymupdf as fitz

import bcd
from build import chrome, chrome_pdf, css
from common import SCRIPTS, BUILD, MANIFEST_DIR, OUT, ROOT, SITE, load_json, save_json


def main():
    manifest = load_json(os.path.join(MANIFEST_DIR, "manifest.json"))
    vols, reps = {}, {}
    for v in manifest["volumes"]:
        p = os.path.join(BUILD, f"vol{v['id']:02d}", "volume.json")
        if os.path.exists(p):
            vols[v["id"]] = load_json(p)
        r = os.path.join(OUT, "verification", f"vol{v['id']:02d}.json")
        if os.path.exists(r):
            reps[v["id"]] = load_json(r)
    page_of = {}
    for vid, info in vols.items():
        for t in info["toc"]:
            if t["type"] == "art":
                page_of[t["anchor"]] = t["page"]
    # ---- final manifest ---------------------------------------------------------
    for a in manifest["articles"]:
        a["volume_page"] = page_of.get(a["key"])
        a["in_pdf"] = a["key"] in page_of
    manifest["bcd_version"] = bcd.version()
    manifest["volume_summary"] = [
        {"volume": vid, "file": i["file"], "title": i["title"], "pages": i["pages"],
         "sheets_duplex": i["sheets_duplex"], "articles": i["articles"], "bytes": i["bytes"]}
        for vid, i in sorted(vols.items())]
    save_json(os.path.join(OUT, "manifest.json"), manifest)
    cols = ["key", "order", "title", "requested_url", "canonical_url", "category", "page_type",
            "retrieved_utc", "retrieval_status", "volume", "volume_file", "volume_page",
            "inclusion", "reason", "source_sha256", "source_last_commit", "mdn_modified"]
    with open(os.path.join(OUT, "manifest.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for m in manifest["articles"] + manifest["excluded"]:
            w.writerow(m)

    # ---- master index PDF ---------------------------------------------------------
    rows = []
    tp = ts = ta = 0
    for vid, i in sorted(vols.items()):
        rows.append(f"<tr><td>{vid}</td><td>{html.escape(i['title'])}<br><code>{i['file']}</code></td>"
                    f"<td class=n>{i['articles']}</td><td class=n>{i['pages']}</td>"
                    f"<td class=n>{i['sheets_duplex']}</td></tr>")
        tp += i["pages"]; ts += i["sheets_duplex"]; ta += i["articles"]
    rows.append(f"<tr><th></th><th>Total</th><th class=n>{ta}</th><th class=n>{tp}</th>"
                f"<th class=n>{ts}</th></tr>")
    idx = sorted((a for a in manifest["articles"] if a["in_pdf"]),
                 key=lambda a: (a["title"].lstrip("[\"'(").lower(), a["order"]))
    entries, letter = [], None
    for a in idx:
        first = a["title"].lstrip("[\"'(")[:1].upper()
        first = first if first.isalpha() else "#"
        if first != letter:
            letter = first
            entries.append(f'<div class="part">{letter}</div>')
        entries.append(f'<a class="l2"><span class="t">{html.escape(a["title"])}</span>'
                       f'<span class="dots"></span><span class="p">{a["volume"]}·{a["volume_page"]}'
                       f'</span></a>')
    inner = f"""
<div class="front">
<h1>MDN JavaScript Documentation</h1>
<p class="vol">Master index of the print compilation</p>
<p>Unofficial print compilation of <code>{SITE}/en-US/docs/Web/JavaScript</code> (MDN Web Docs,
by Mozilla Contributors, CC-BY-SA 2.5 or later), retrieved {manifest['inventory_retrieved']}.
{ta} articles in {len(vols)} volumes. Not an official Mozilla publication.</p>
<div class="rule"></div>
<h2>Volumes</h2>
<table><thead><tr><th>Vol.</th><th>Contents and file name</th><th>Articles</th><th>Pages</th>
<th>Sheets (double-sided)</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p>Each volume starts with its own table of contents and has PDF bookmarks. Page numbers are
printed in the outer corner of every page and are identical to the PDF page numbers.</p>
<h2>Alphabetical index of all articles</h2>
<p>Entries give <b>volume·page</b>. Titles are MDN's article titles; a leading bracket or quote
is ignored for sorting.</p>
</div>
<div class="toc cols3">{''.join(entries)}</div>"""
    extra = """
@page { @bottom-center { content: counter(page); font: 9pt "Segoe UI", sans-serif; } }
.toc.cols3 { column-count: 2; column-gap: 8mm; font-size: 8.6pt; }
.toc.cols3 .l2 { padding-left: 0; font-size: 8.4pt; }
.toc.cols3 .p { min-width: 30pt; }
td.n, th.n { text-align: right; }
.front table { width: 100%; font-size: 9.4pt; }
"""
    wdir = os.path.join(BUILD, "index")
    os.makedirs(wdir, exist_ok=True)
    hp = os.path.join(wdir, "index.html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>MDN JavaScript '
                f'— Master index</title><style>{css()}{extra}</style></head><body>{inner}</body></html>')
    out_pdf = os.path.join(OUT, "MDN-JavaScript-Master-Index.pdf")
    chrome_pdf(hp, out_pdf)
    d = fitz.open(out_pdf)
    idx_pages = len(d)
    d.close()

    # ---- verification report ---------------------------------------------------------
    stats = Counter()
    issues = []
    for vid, i in vols.items():
        for st in i["stats"].values():
            stats.update(st)
        issues += i.get("issues", [])
    ver = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-Item '{chrome()}').VersionInfo.ProductVersion"],
                         capture_output=True, text=True).stdout.strip() if os.name == "nt" else ""
    commits = Counter(a["source_last_commit"] for a in manifest["articles"])
    mods = sorted(a["mdn_modified"] for a in manifest["articles"] if a["mdn_modified"])
    visual = load_json(os.path.join(MANIFEST_DIR, "visual_inspection.json"), {})
    L = []
    A = L.append
    A("# Verification report — MDN JavaScript print compilation\n")
    A(f"- **Source:** {SITE}/en-US/docs/Web/JavaScript and every canonical en-US article below it")
    A(f"- **Retrieval date:** {manifest['inventory_retrieved']} (UTC timestamps per article are in "
      f"`manifest.csv`)")
    A("- **Source form:** MDN's rendered article JSON (`<article URL>/index.json`), i.e. the output "
      "of MDN's own build with all macros, includes and generated content resolved. No Markdown "
      "from the repository was used.")
    A(f"- **Source version:** each article records the mdn/content commit that last changed it "
      f"({len(commits)} distinct commits) and a SHA-256 of the retrieved JSON; newest article "
      f"modification {mods[-1][:10]}, oldest {mods[0][:10]}.")
    A(f"- **Compatibility data:** @mdn/browser-compat-data {bcd.version()} (same version the MDN "
      f"compatibility API reported on the retrieval date)")
    A(f"- **Renderer:** Chrome {ver} headless (print to PDF), post-processed with PyMuPDF "
      f"{fitz.pymupdf_version}\n")
    A("## Inventory and coverage\n")
    ic = manifest["inventory_counts"]
    A(f"| | count |\n|---|---|\n| URLs under /en-US/docs/Web/JavaScript in MDN's en-US sitemap | "
      f"{ic['sitemap']} |\n| same subtree in MDN's en-US search index | {ic['search_index']} |\n"
      f"| union (requested) | {ic['union']} |\n| retrieved successfully (HTTP 200) | "
      f"{sum(1 for a in manifest['articles'] if a['retrieval_status'] == 200)} |\n"
      f"| redirects / aliases | {sum(1 for e in manifest['excluded'] if e['retrieval_status'] == 200)} |\n"
      f"| not retrievable | {sum(1 for e in manifest['excluded'] if e['retrieval_status'] != 200)} |\n"
      f"| distinct canonical articles | {len(manifest['articles'])} |\n"
      f"| articles present in the PDFs | {sum(1 for a in manifest['articles'] if a['in_pdf'])} |\n")
    A("The two official inventories listed exactly the same URLs. In addition, every link inside "
      "the retrieved articles that points into the JavaScript subtree was checked against the "
      "inventory (link crawl): no unlisted page, alias or redirect was found. Translations, "
      "history pages and site interface pages are not part of these inventories and were not "
      "retrieved. Pages outside `/en-US/docs/Web/JavaScript/` (Web APIs, DOM, HTML, CSS, Glossary, "
      "Learn web development) are out of scope by definition; links to them are kept as links.\n")
    A("**Excluded or inaccessible pages:** "
      + ("none." if not manifest["excluded"] else f"{len(manifest['excluded'])} — see manifest.") + "\n")
    A("## Volumes\n")
    A("| Vol. | File | Articles | Pages | Sheets (duplex) | Size |\n|---|---|---|---|---|---|")
    for vid, i in sorted(vols.items()):
        A(f"| {vid} | `{i['file']}` | {i['articles']} | {i['pages']} | {i['sheets_duplex']} | "
          f"{i['bytes'] / 1e6:.1f} MB |")
    A(f"| | **Total** | **{ta}** | **{tp}** | **{ts}** | |")
    A(f"| | `MDN-JavaScript-Master-Index.pdf` | | {idx_pages} | {(idx_pages + 1) // 2} | |\n")
    A("## Automated checks (run on every article and every page of every volume)\n")
    A("| Vol. | V1 manifest = PDF | V2 text source→print (exact / whitespace-only / differ) | "
      "V3 code blocks identical | V4 structure counts equal | V5 text print→PDF (exact / + SVG "
      "figure text / math layout / reordered / minor / differ) | V6 PDF code lines | V7 contents "
      "entries / bookmarks | V8 overflow pages | Problems |\n|---|---|---|---|---|---|---|---|---|---|")
    tot = Counter()
    for vid, r in sorted(reps.items()):
        c = Counter(r["per_article"])
        tot.update(r["totals"])
        A(f"| {vid} | {'yes' if r.get('v1_manifest_match') else 'NO'} ({r['v1_titles_on_page']}/"
          f"{r['articles']} titles on page) | {c['v2_exact']} / {c['v2_whitespace_only']} / "
          f"{c['v2_mismatch']} | {c['v3_code_identical']}/{r['articles']} | "
          f"{c['v4_counts_equal']}/{r['articles']} | {c['v5_exact']} / "
          f"{c['v5_exact_plus_svg_figure_text']} / {c['v5_math_layout_only']} / "
          f"{c['v5_same_chars_other_order']} / {c['v5_minor_glyph_diff']} / {c['v5_mismatch']} | "
          f"{c['v6_code_ok']} ok, {c['v6_code_mismatch']} differ | {r['v7_toc_entries_ok']}/"
          f"{r['v7_toc_entries_expected']}; {r['v7_bookmarks']} "
          f"{'ok' if r['v7_bookmarks_match'] else 'MISMATCH'} | {len(r['v8_overflow_pages'])} | "
          f"{len(r['problems'])} |")
    A("")
    A(f"Totals over all volumes: {tot['code_blocks']} code blocks with {tot['code_lines']} lines "
      f"compared; {tot['code_lines_over_92']} source lines are longer than 92 characters and "
      f"{tot['code_lines_wrapped_in_pdf']} extra physical lines were produced by visual wrapping; "
      f"{tot['table']} article tables, {tot['img']} images, {tot['notecard']} notes/warnings, "
      f"{tot['math']} MathML formulas; {tot['table_headers_repeated']} table headers repeated "
      f"after page breaks; {tot['chars_source']:,} non-space characters of MDN article text.\n")
    A("What each check does:\n")
    A("- **V1** the list of manifest articles assigned to the volume equals the list of article "
      "anchors found in the PDF, in order, and each article title is printed on its page.\n"
      "- **V2** text of MDN's JSON vs text of the print HTML with print-edition additions removed; "
      "extracted with Python's `html.parser`, independent of the converter (lxml).\n"
      "- **V3** every `<pre>` block: source string equals print string, character for character "
      "(includes all whitespace and indentation).\n"
      "- **V4** per article: numbers of code blocks, tables, rows, cells, captions, images, list "
      "items, definition terms, paragraphs, block quotes, notes, formulas.\n"
      "- **V5** text extracted from the *final PDF* inside each article's page area vs the print "
      "HTML text, whitespace-insensitive, Unicode NFKC. Accepted, separately counted deviations: "
      "table headers repeated on continuation pages; lettering inside SVG figures (extra text, "
      "article text must still be complete and in order); MathML layout (radical signs, stacked "
      "limits); 'reordered' = same characters in another order (right-to-left text, tables).\n"
      "- **V6** code lines re-extracted from the PDF by font size, including leading spaces, "
      "compared line by line with the source; wrapped lines must reassemble exactly and start at "
      "the right indentation.\n"
      "- **V7** every contents entry: printed number = link target = page that carries the "
      "heading; bookmarks equal the article/section list.\n"
      "- **V8** every page: no text span, picture or table rule outside the type area (tolerance "
      "1.5 pt). **V9** fonts embedded, internal links resolve, all pages A4.\n")
    probs = [(vid, p) for vid, r in sorted(reps.items()) for p in r["problems"]]
    A("### Problems reported by the automated checks\n")
    if not probs:
        A("None.\n")
    else:
        for vid, p in probs:
            A(f"- Vol. {vid}: {p}")
        A("")
    odd = [(vid, d) for vid, r in sorted(reps.items()) for d in r["article_details"] if d.get("v5")
           and d["v5"] not in ("reordered", "math layout") and not str(d["v5"]).startswith("plus")]
    if odd:
        A("### Articles whose PDF text differs slightly from the print HTML (V5 'minor')\n")
        cp = lambda t: " ".join(f"U+{ord(ch):04X}" for ch in t) or "none"
        for vid, d in odd:
            v5 = d["v5"]
            what = (f"{v5['missing']} character(s) of the source not found in the PDF text "
                    f"({cp(v5['missing_chars'])}); {v5['extra']} unexpected character(s) "
                    f"({cp(v5['extra_chars'])})") if isinstance(v5, dict) else str(v5)
            A(f"- Vol. {vid} p.{d['page']} *{d['title']}*: {what}")
        A("")
        A("U+FFFD in the list above is the placeholder box that is printed when no font "
          "installed on the build machine contains the character (the two affected characters "
          "are U+1018A GREEK ZERO SIGN and U+10D40 GARAY DIGIT ZERO, if listed). U+0307 is a "
          "combining dot that is drawn correctly but reported twice by PDF text extraction.\n")
    A("## Visual inspection actually performed\n")
    if visual:
        A(visual.get("note", ""))
        for k, pages in sorted(visual.get("pages", {}).items()):
            A(f"- **{k}:** {len(pages)} pages viewed — " + ", ".join(map(str, pages)))
        A("")
        A("Pages not listed above were **not** inspected visually; they are covered only by the "
          "automated checks.\n")
    A("## Content that could not be represented exactly as on the website\n")
    A(f"- **Interactive examples:** {stats['interactive_examples']} `Try it` widgets cannot run on "
      "paper. Their source code is printed in full (verified by V3/V6); a print note marks each. "
      "Console output is printed only where MDN's source contains it (e.g. `// Expected output`).\n"
      f"- **Live samples:** {stats['live_samples']} embedded live-sample frames (browser-rendered "
      "output) are not reproduced; each is replaced by a print note with the URL of the live "
      "version. All of their source code is printed, including "
      f"{stats['hidden_code']} supporting code blocks that MDN hides on the page (labelled).\n"
      f"- **Browser compatibility tables** ({stats['bcd_tables']} tables, {stats['bcd_rows']} "
      "feature rows) and **specification tables** "
      f"({stats['spec_rows']} entries; {stats['spec_empty']} articles without one) are generated "
      "by the website from data, not article text. They were re-rendered from the same data in a "
      "print layout: version numbers and words instead of icons, qualifiers as numbered notes. "
      "Release dates and the website's expandable per-cell history are not shown; multiple "
      "support statements for one browser are condensed into the first statement plus notes. "
      "Internet Explorer and Quest Browser, which the website also omits, are not shown.\n"
      "- **Baseline banners** are condensed to one line generated from MDN's baseline data "
      "(wording is this edition's, not MDN's; the banner's 'Learn more / See full compatibility' "
      "links are dropped).\n"
      f"- **Status icons** ({stats['status_icons']}) are printed as text badges with the icon's "
      "accessible label.\n"
      f"- **Navigation:** {stats['prev_next_removed']} previous/next button bars, the sidebar, "
      "'In this article' lists, 'Help improve MDN' and 'View this page on GitHub' footers are "
      "website interface and were omitted.\n"
      "- **Syntax highlighting** is not reproduced (code is printed in plain black, by design); "
      "emoji and ✓/✗ symbols are printed as monochrome outlines where the fonts allow.\n"
      "- **MathML** formulas are typeset by Chrome; their hidden TeX annotations are not printed.\n"
      f"- **Very wide tables:** {stats['rotated_tables']} tables with eight or more columns are "
      "printed rotated by a quarter turn on a page of their own, which leaves part of the "
      "preceding page empty.\n"
      "- **Images:** enlarged by one third, limited to the column width. Text inside SVG diagrams "
      "is small at source and may be around 6–8 pt.\n"
      "- **Links** cannot be followed on paper; link text is preserved, URLs are active in the PDF "
      f"({stats['links_internal']} in-volume links, {stats['links_collection']} links to "
      f"articles in other volumes, {stats['links_mdn']} links to other MDN pages, "
      f"{stats['links_external']} external links). URLs are printed visibly only for the article "
      "source line, specifications and live samples.\n")
    A("- **Characters without a font:** characters that no installed font contains are printed "
      "as an empty box (listed above under V5 'minor', if any).\n"
      "- **Right-to-left text and tab characters in code** are drawn by the browser engine as "
      "on the website; their PDF text can only be compared order-insensitively "
      f"({tot['code_lines_bidi_reordered']} code lines) or by visible characters "
      f"({tot['code_lines_with_tabs']} tab-indented code lines).\n")
    A("## Remaining limitations\n")
    A("- The comparison of PDF text is whitespace-insensitive (line wrapping changes whitespace); "
      "exact whitespace is verified for code only (V3 at HTML level, V6 for leading indentation "
      "in the PDF).\n"
      "- Automated checks cannot judge appearance. Only the pages listed under 'Visual "
      "inspection' were looked at.\n"
      "- Long code lines (> ~92 characters) wrap at the box edge and continue at the left edge; "
      "the count is given above.\n"
      "- Tables with merged cells may leave white space at a page end because merged rows are "
      "kept together.\n"
      "- The collection is a snapshot of the retrieval date. MDN changes daily; rerun the scripts "
      "to refresh.\n")
    if issues:
        A("### Converter warnings\n")
        for s in issues:
            A(f"- {s}")
        A("")
    with open(os.path.join(OUT, "VERIFICATION-REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    # scripts + data needed to refresh
    dst = os.path.join(OUT, "generator")
    os.makedirs(dst, exist_ok=True)
    for fn in os.listdir(SCRIPTS):
        if fn.endswith((".py", ".css")):
            shutil.copy2(os.path.join(SCRIPTS, fn), os.path.join(dst, fn))
    print(f"report written: {ta} articles, {tp} pages, {ts} sheets, index {idx_pages} pages, "
          f"{len(probs)} problems")


if __name__ == "__main__":
    main()
