# MDN JavaScript documentation — print compilation generator

Builds print-ready A4 PDF volumes from the official English MDN JavaScript
documentation (`https://developer.mozilla.org/en-US/docs/Web/JavaScript` and
everything below it).

This is an unofficial compilation. MDN content is by Mozilla Contributors and
licensed CC-BY-SA 2.5 or later; code samples are CC0 (MIT before 20 Aug 2010).
Not endorsed by Mozilla.

## Requirements

- Python 3.11+ with `pymupdf` and `lxml` (`pip install pymupdf lxml`)
- Google Chrome or Microsoft Edge (used headless to print HTML to PDF)
- Fonts: Cambria, Consolas, Segoe UI (Windows). On other systems change the
  font families in `scripts/print.css` and the font files in `FONTS` in
  `scripts/build.py`.
- The browser-compat-data package, unpacked to `data/bcd/package/data.json`:
  download the tarball named by `https://registry.npmjs.org/@mdn/browser-compat-data/latest`
  and extract `package/data.json`.

## Refreshing the collection

Put these files in a folder named `scripts` inside an empty project folder (the scripts create `data/`, `manifest/`, `build/` and `output/` next to it). Run from the `scripts` folder, in this order:

| Step | Command | What it does |
|---|---|---|
| 1 | `python fetch.py --refresh` | Reads MDN's sitemap and search index, retrieves every article's rendered JSON (`<url>/index.json`) at a polite rate, follows in-scope links to find aliases. Cached in `data/raw`, progress in `manifest/progress.json`; without `--refresh` it only fetches what is missing. |
| 2 | `python plan.py` | Builds `manifest/manifest.json` / `.csv`: MDN sidebar order, categories, volume assignment. Volume boundaries are the `VOLUMES` list at the top of the file. |
| 3 | `python build.py sample` | Builds the layout sample in `build/sample`. |
| 4 | `python build.py all --force` | Builds every volume into `output/`. `python build.py 3` builds one volume; without `--force`, `all` skips volumes already recorded in `manifest/build_state.json` (resume after interruption). |
| 5 | `python verify.py all` | Automated checks; results in `output/verification/`. |
| 6 | `python sheets.py vol01 chapters` | Contact sheets for visual inspection (`build/vol01/sheets`); `python sheets.py vol01 viewed` records the sheets you actually looked at. |
| 7 | `python report.py` | Master index PDF, final manifest with page numbers, verification report. |

## Files

- `scripts/common.py` — paths and helpers
- `scripts/fetch.py` — inventory and retrieval
- `scripts/plan.py` — manifest, ordering, volumes
- `scripts/convert.py` — article JSON → print HTML (the list of all transformations is in its docstring)
- `scripts/bcd.py` — print rendering of browser-compatibility tables
- `scripts/print.css` — page geometry and typography
- `scripts/build.py` — Chrome rendering, contents, bookmarks, running headers, page numbers
- `scripts/verify.py` — automated verification
- `scripts/sheets.py` — contact sheets for visual checks
- `scripts/report.py` — master index, manifest, report

## Layout parameters you may want to change

- Page size and margins: `@page` rules at the top of `print.css` **and** the
  `TOP/BOTTOM/INNER/OUTER` constants in `build.py` and `verify.py` (keep them equal).
- Body and code font sizes: `html { font-size }` and `pre.code { font-size }` in
  `print.css`. If you change the code size, change `CODE_SIZE` in `verify.py` too.
- How code blocks are split: `KEEP_LINES`, `CHUNK_LINES`, `CHUNK_MAX` in `convert.py`.
