"""Render contact sheets (6 pages per image) for visual inspection.
   python sheets.py vol01 chapters|figures|code|pages:12,40,77 """
import os, sys
import pymupdf as fitz
from common import BUILD, OUT, load_json, save_json

def sheet(doc, pages, path, dpi=52, cols=3):
    pix = [doc[p - 1].get_pixmap(dpi=dpi) for p in pages]
    w = max(p.width for p in pix); h = max(p.height for p in pix)
    rows = (len(pix) + cols - 1) // cols
    out = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, cols * (w + 6), rows * (h + 6)), 0)
    out.clear_with(150)
    for i, p in enumerate(pix):
        p.set_origin((i % cols) * (w + 6) + 3, (i // cols) * (h + 6) + 3)
        out.copy(p, p.irect)
    out.save(path)

def main():
    name, what = sys.argv[1], sys.argv[2]
    d = os.path.join(BUILD, name, "sheets"); os.makedirs(d, exist_ok=True)
    logp = os.path.join(d, "log.json")
    log = load_json(logp, {})
    if what == "viewed":
        # record sheets that were actually looked at (all rendered sheets, or the named ones)
        from common import MANIFEST_DIR
        vp = os.path.join(MANIFEST_DIR, "visual_inspection.json")
        vis = load_json(vp, {"note": "", "pages": {}})
        names = sys.argv[3:] or sorted(log)
        pages = set(vis["pages"].get(name, []))
        for n in names:
            pages.update(log[n])
        vis["pages"][name] = sorted(pages)
        save_json(vp, vis)
        print(name, len(pages), "pages recorded as visually inspected")
        return
    info = load_json(os.path.join(BUILD, name, "volume.json"))
    doc = fitz.open(os.path.join(OUT if name != "sample" else os.path.join(BUILD, name), info["file"]))
    arts = [t for t in info["toc"] if t["type"] == "art"]
    if what.startswith("chapters"):
        maxlvl = int(what.split(":")[1]) if ":" in what else 9
        pages = []
        for i, t in enumerate(arts):
            if t["level"] > maxlvl:
                continue
            end = arts[i + 1]["page"] - 1 if i + 1 < len(arts) else len(doc)
            pages.append(min(t["page"] + (2 if i % 2 else 1), max(end, t["page"])))
        pages = sorted(set(pages))
    elif what == "figures":
        pages = [p.number + 1 for p in doc if len(p.get_images()) or len(p.get_drawings()) > 150][:36]
    elif what == "code":
        pages = info["code_continuations"][:18]
    elif what.startswith("spread"):
        n = int(what.split(":")[1]) if ":" in what else 24
        step = max(1, (len(doc) - info["front_pages"]) // n)
        pages = list(range(info["front_pages"] + 2, len(doc), step))[:n]
    else:
        pages = [int(x) for x in what.split(":")[1].split(",")]
    tag = (sys.argv[4] if len(sys.argv) > 4 else what.split(":")[0])
    for k in range(0, len(pages), 6):
        fn = f"{tag}_{k // 6 + 1:02d}.png"
        sheet(doc, pages[k:k + 6], os.path.join(d, fn))
        log[fn] = pages[k:k + 6]
        print(fn, pages[k:k + 6])
    save_json(logp, log)

main()
