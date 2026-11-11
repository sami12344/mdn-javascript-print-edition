# Verification report — MDN JavaScript print compilation

- **Source:** https://developer.mozilla.org/en-US/docs/Web/JavaScript and every canonical en-US article below it
- **Retrieval date:** 2026-11-10 (UTC timestamps per article are in `manifest.csv`)
- **Source form:** MDN's rendered article JSON (`<article URL>/index.json`), i.e. the output of MDN's own build with all macros, includes and generated content resolved. No Markdown from the repository was used.
- **Source version:** each article records the mdn/content commit that last changed it (121 distinct commits) and a SHA-256 of the retrieved JSON; newest article modification 2026-11-09, oldest 2025-07-08.
- **Compatibility data:** @mdn/browser-compat-data 8.1.8 (same version the MDN compatibility API reported on the retrieval date)
- **Renderer:** Chrome 157.0.8103.39 headless (print to PDF), post-processed with PyMuPDF 2.1

## Inventory and coverage

| | count |
|---|---|
| URLs under /en-US/docs/Web/JavaScript in MDN's en-US sitemap | 1346 |
| same subtree in MDN's en-US search index | 1346 |
| union (requested) | 1346 |
| retrieved successfully (HTTP 200) | 1346 |
| redirects / aliases | 0 |
| not retrievable | 0 |
| distinct canonical articles | 1346 |
| articles present in the PDFs | 1346 |

The two official inventories listed exactly the same URLs. In addition, every link inside the retrieved articles that points into the JavaScript subtree was checked against the inventory (link crawl): no unlisted page, alias or redirect was found. Translations, history pages and site interface pages are not part of these inventories and were not retrieved. Pages outside `/en-US/docs/Web/JavaScript/` (Web APIs, DOM, HTML, CSS, Glossary, Learn web development) are out of scope by definition; links to them are kept as links.

**Excluded or inaccessible pages:** none.

## Volumes

| Vol. | File | Articles | Pages | Sheets (duplex) | Size |
|---|---|---|---|---|---|
| 1 | `MDN-JavaScript-Vol01-Guide.pdf` | 38 | 383 | 192 | 5.4 MB |
| 2 | `MDN-JavaScript-Vol02-Reference-Operators-Statements.pdf` | 114 | 448 | 224 | 5.4 MB |
| 3 | `MDN-JavaScript-Vol03-Reference-Functions-Classes-RegExp-Errors-Misc.pdf` | 179 | 427 | 214 | 5.0 MB |
| 4 | `MDN-JavaScript-Vol04-Builtins-A-to-Date.pdf` | 195 | 497 | 249 | 6.4 MB |
| 5 | `MDN-JavaScript-Vol05-Builtins-decodeURI-to-Iterator.pdf` | 179 | 497 | 249 | 6.0 MB |
| 6 | `MDN-JavaScript-Vol06-Builtins-JSON-to-Proxy.pdf` | 162 | 478 | 239 | 5.8 MB |
| 7 | `MDN-JavaScript-Vol07-Builtins-RangeError-to-SyntaxError.pdf` | 160 | 382 | 191 | 5.2 MB |
| 8 | `MDN-JavaScript-Vol08-Builtins-Temporal.pdf` | 242 | 457 | 229 | 6.2 MB |
| 9 | `MDN-JavaScript-Vol09-Builtins-TypedArray-to-WeakSet.pdf` | 77 | 175 | 88 | 2.6 MB |
| | **Total** | **1346** | **3744** | **1875** | |
| | `MDN-JavaScript-Master-Index.pdf` | | 12 | 6 | |

## Automated checks (run on every article and every page of every volume)

| Vol. | V1 manifest = PDF | V2 text source→print (exact / whitespace-only / differ) | V3 code blocks identical | V4 structure counts equal | V5 text print→PDF (exact / + SVG figure text / math layout / reordered / minor / differ) | V6 PDF code lines | V7 contents entries / bookmarks | V8 overflow pages | Problems |
|---|---|---|---|---|---|---|---|---|---|
| 1 | yes (38/38 titles on page) | 38 / 0 / 0 | 38/38 | 38/38 | 35 / 3 / 0 / 0 / 0 / 0 | 38 ok, 0 differ | 292/292; 293 ok | 0 | 0 |
| 2 | yes (114/114 titles on page) | 114 / 0 / 0 | 114/114 | 114/114 | 114 / 0 / 0 / 0 / 0 / 0 | 114 ok, 0 differ | 114/114; 884 ok | 0 | 0 |
| 3 | yes (179/179 titles on page) | 179 / 0 / 0 | 179/179 | 179/179 | 177 / 1 / 0 / 0 / 1 / 0 | 179 ok, 0 differ | 179/179; 1121 ok | 0 | 0 |
| 4 | yes (195/195 titles on page) | 195 / 0 / 0 | 195/195 | 195/195 | 190 / 1 / 0 / 4 / 0 / 0 | 195 ok, 0 differ | 195/195; 1430 ok | 0 | 0 |
| 5 | yes (179/179 titles on page) | 179 / 0 / 0 | 179/179 | 179/179 | 175 / 1 / 0 / 2 / 1 / 0 | 179 ok, 0 differ | 179/179; 1273 ok | 0 | 0 |
| 6 | yes (162/162 titles on page) | 162 / 0 / 0 | 162/162 | 162/162 | 153 / 0 / 7 / 2 / 0 / 0 | 162 ok, 0 differ | 162/162; 1267 ok | 0 | 0 |
| 7 | yes (160/160 titles on page) | 160 / 0 / 0 | 160/160 | 160/160 | 151 / 8 / 0 / 0 / 1 / 0 | 160 ok, 0 differ | 160/160; 1176 ok | 0 | 0 |
| 8 | yes (242/242 titles on page) | 242 / 0 / 0 | 242/242 | 242/242 | 242 / 0 / 0 / 0 / 0 / 0 | 242 ok, 0 differ | 242/242; 1412 ok | 0 | 0 |
| 9 | yes (77/77 titles on page) | 77 / 0 / 0 | 77/77 | 77/77 | 77 / 0 / 0 / 0 / 0 / 0 | 77 ok, 0 differ | 77/77; 580 ok | 0 | 0 |

Totals over all volumes: 6857 code blocks with 49890 lines compared; 337 source lines are longer than 92 characters and 341 extra physical lines were produced by visual wrapping; 156 article tables, 51 images, 580 notes/warnings, 55 MathML formulas; 85 table headers repeated after page breaks; 4,148,267 non-space characters of MDN article text.

What each check does:

- **V1** the list of manifest articles assigned to the volume equals the list of article anchors found in the PDF, in order, and each article title is printed on its page.
- **V2** text of MDN's JSON vs text of the print HTML with print-edition additions removed; extracted with Python's `html.parser`, independent of the converter (lxml).
- **V3** every `<pre>` block: source string equals print string, character for character (includes all whitespace and indentation).
- **V4** per article: numbers of code blocks, tables, rows, cells, captions, images, list items, definition terms, paragraphs, block quotes, notes, formulas.
- **V5** text extracted from the *final PDF* inside each article's page area vs the print HTML text, whitespace-insensitive, Unicode NFKC. Accepted, separately counted deviations: table headers repeated on continuation pages; lettering inside SVG figures (extra text, article text must still be complete and in order); MathML layout (radical signs, stacked limits); 'reordered' = same characters in another order (right-to-left text, tables).
- **V6** code lines re-extracted from the PDF by font size, including leading spaces, compared line by line with the source; wrapped lines must reassemble exactly and start at the right indentation.
- **V7** every contents entry: printed number = link target = page that carries the heading; bookmarks equal the article/section list.
- **V8** every page: no text span, picture or table rule outside the type area (tolerance 1.5 pt). **V9** fonts embedded, internal links resolve, all pages A4.

### Problems reported by the automated checks

None.

### Articles whose PDF text differs slightly from the print HTML (V5 'minor')

- Vol. 3 p.121 *Character class: [...], [^...]*: 3 character(s) of the source not found in the PDF text (U+1018A); 3 unexpected character(s) (U+FFFD)
- Vol. 5 p.202 *Intl.supportedValuesOf()*: 1 character(s) of the source not found in the PDF text (U+10D40); 1 unexpected character(s) (U+FFFD)
- Vol. 7 p.297 *String.prototype.toLocaleLowerCase()*: 0 character(s) of the source not found in the PDF text (none); 1 unexpected character(s) (U+0307)

U+FFFD in the list above is the placeholder box that is printed when no font installed on the build machine contains the character (the two affected characters are U+1018A GREEK ZERO SIGN and U+10D40 GARAY DIGIT ZERO, if listed). U+0307 is a combining dot that is drawn correctly but reported twice by PDF text extraction.

## Visual inspection actually performed

Pages of the final PDFs were rendered to images (contact sheets of six pages, about 52 dpi) and looked at by the compiling assistant for layout faults: overlapping or clipped elements, stranded headings, broken tables, missing figures, header/footer placement. At this resolution body text is recognisable but small print was not proof-read. Selection: the opening pages of each chapter or built-in object, evenly spaced pages, every page flagged by the automated checks, the title/contents pages of several volumes, and all pages with tables of eight or more columns. Earlier builds were inspected the same way while the template was being fixed; only pages of the final build are listed here.
- **vol01:** 34 pages viewed — 1, 2, 3, 105, 111, 112, 113, 114, 117, 118, 123, 137, 140, 152, 167, 179, 185, 191, 201, 221, 237, 249, 272, 288, 305, 314, 316, 317, 320, 324, 335, 350, 353, 361
- **vol02:** 24 pages viewed — 2, 3, 4, 28, 52, 76, 100, 124, 148, 172, 196, 197, 198, 199, 200, 220, 244, 268, 292, 316, 340, 364, 388, 412
- **vol03:** 25 pages viewed — 2, 3, 6, 29, 52, 75, 98, 121, 122, 134, 135, 144, 167, 190, 213, 236, 259, 282, 305, 328, 351, 353, 354, 374, 397
- **vol04:** 17 pages viewed — 6, 10, 12, 18, 206, 227, 242, 247, 256, 262, 268, 299, 319, 324, 328, 338, 387
- **vol05:** 24 pages viewed — 2, 6, 10, 12, 30, 33, 37, 66, 69, 78, 83, 94, 98, 174, 178, 182, 186, 190, 199, 200, 201, 202, 203, 431
- **vol06:** 14 pages viewed — 6, 32, 70, 85, 164, 169, 220, 243, 322, 345, 350, 354, 401, 428
- **vol07:** 14 pages viewed — 6, 10, 15, 50, 69, 124, 132, 169, 184, 195, 258, 321, 329, 379
- **vol08:** 25 pages viewed — 1, 2, 5, 6, 7, 8, 9, 10, 11, 12, 25, 74, 107, 117, 188, 228, 254, 265, 281, 302, 318, 339, 363, 376, 413
- **vol09:** 17 pages viewed — 4, 32, 60, 88, 93, 97, 116, 117, 122, 126, 131, 134, 136, 141, 144, 161, 167

Pages not listed above were **not** inspected visually; they are covered only by the automated checks.

## Content that could not be represented exactly as on the website

- **Interactive examples:** 589 `Try it` widgets cannot run on paper. Their source code is printed in full (verified by V3/V6); a print note marks each. Console output is printed only where MDN's source contains it (e.g. `// Expected output`).
- **Live samples:** 9 embedded live-sample frames (browser-rendered output) are not reproduced; each is replaced by a print note with the URL of the live version. All of their source code is printed, including 5 supporting code blocks that MDN hides on the page (labelled).
- **Browser compatibility tables** (1164 tables, 3063 feature rows) and **specification tables** (1256 entries; 1 articles without one) are generated by the website from data, not article text. They were re-rendered from the same data in a print layout: version numbers and words instead of icons, qualifiers as numbered notes. Release dates and the website's expandable per-cell history are not shown; multiple support statements for one browser are condensed into the first statement plus notes. Internet Explorer and Quest Browser, which the website also omits, are not shown.
- **Baseline banners** are condensed to one line generated from MDN's baseline data (wording is this edition's, not MDN's; the banner's 'Learn more / See full compatibility' links are dropped).
- **Status icons** (75) are printed as text badges with the icon's accessible label.
- **Navigation:** 39 previous/next button bars, the sidebar, 'In this article' lists, 'Help improve MDN' and 'View this page on GitHub' footers are website interface and were omitted.
- **Syntax highlighting** is not reproduced (code is printed in plain black, by design); emoji and ✓/✗ symbols are printed as monochrome outlines where the fonts allow.
- **MathML** formulas are typeset by Chrome; their hidden TeX annotations are not printed.
- **Very wide tables:** 3 tables with eight or more columns are printed rotated by a quarter turn on a page of their own, which leaves part of the preceding page empty.
- **Images:** enlarged by one third, limited to the column width. Text inside SVG diagrams is small at source and may be around 6–8 pt.
- **Links** cannot be followed on paper; link text is preserved, URLs are active in the PDF (11634 in-volume links, 7938 links to articles in other volumes, 1099 links to other MDN pages, 1333 external links). URLs are printed visibly only for the article source line, specifications and live samples.

- **Characters without a font:** characters that no installed font contains are printed as an empty box (listed above under V5 'minor', if any).
- **Right-to-left text and tab characters in code** are drawn by the browser engine as on the website; their PDF text can only be compared order-insensitively (14 code lines) or by visible characters (2 tab-indented code lines).

## Remaining limitations

- The comparison of PDF text is whitespace-insensitive (line wrapping changes whitespace); exact whitespace is verified for code only (V3 at HTML level, V6 for leading indentation in the PDF).
- Automated checks cannot judge appearance. Only the pages listed under 'Visual inspection' were looked at.
- Long code lines (> ~92 characters) wrap at the box edge and continue at the left edge; the count is given above.
- Tables with merged cells may leave white space at a page end because merged rows are kept together.
- The collection is a snapshot of the retrieval date. MDN changes daily; rerun the scripts to refresh.

### Converter warnings

- /en-US/docs/Web/JavaScript/Reference/Global_Objects/AbstractModuleSource: no compatibility data for query 'javascript.builtins.AbstractModuleSource'
