"""Step 3: build the source manifest - ordering, categories and volume assignment.

Ordering follows MDN's own JavaScript sidebar (taken from the retrieved landing
page), so categories and article order are MDN's, not invented here.  Articles
that the sidebar does not list individually (members of built-in objects,
sub-pages) are placed directly after their parent page, in the member order MDN
uses on reference pages: constructor, static methods, static properties,
instance methods, instance properties, then nested classes.

Writes manifest/manifest.json and manifest/manifest.csv.
"""
import csv
import os
import re
import urllib.parse

import lxml.html

from common import (MANIFEST_DIR, SCOPE_PREFIX, SITE, load_json, raw_path, save_json)

PROGRESS = os.path.join(MANIFEST_DIR, "progress.json")

# Volume plan.  Built-in objects are split alphabetically (MDN sidebar order) at
# the names given in `upto` (inclusive, last object of that volume).
VOLUMES = [
    dict(id=1, slug="Guide", title="JavaScript Guide",
         blurb="The MDN JavaScript landing page and the complete JavaScript Guide "
               "(fundamental, intermediate and advanced guides)."),
    dict(id=2, slug="Reference-Operators-Statements",
         title="Reference: Expressions & operators · Statements & declarations",
         blurb="The JavaScript reference landing page, every expression and operator "
               "page, and every statement and declaration page."),
    dict(id=3, slug="Reference-Functions-Classes-RegExp-Errors-Misc",
         title="Reference: Functions · Classes · Regular expressions · Errors · Misc",
         blurb="Functions, classes, regular expression syntax, the complete error "
               "reference, and the miscellaneous reference pages (lexical grammar, "
               "execution model, iteration protocols, strict mode and others)."),
    dict(id=4, slug="Builtins-A-to-Date", title="Built-in objects: AbstractModuleSource – Date",
         upto="Date"),
    dict(id=5, slug="Builtins-decodeURI-to-Iterator", title="Built-in objects: decodeURI() – Iterator",
         upto="Iterator"),
    dict(id=6, slug="Builtins-JSON-to-Proxy", title="Built-in objects: JSON – Proxy", upto="Proxy"),
    dict(id=7, slug="Builtins-RangeError-to-SyntaxError",
         title="Built-in objects: RangeError – SyntaxError", upto="SyntaxError"),
    dict(id=8, slug="Builtins-Temporal", title="Built-in objects: Temporal", upto="Temporal"),
    dict(id=9, slug="Builtins-TypedArray-to-WeakSet",
         title="Built-in objects: TypedArray – WeakSet", upto=None),
]
for v in VOLUMES:
    v["file"] = f"MDN-JavaScript-Vol{v['id']:02d}-{v['slug']}.pdf"

TYPE_RANK = {
    "javascript-constructor": 0,
    "javascript-static-method": 1,
    "javascript-static-data-property": 2,
    "javascript-static-accessor-property": 2,
    "javascript-instance-method": 3,
    "javascript-instance-data-property": 4,
    "javascript-instance-accessor-property": 4,
    "javascript-class": 5,
    "javascript-namespace": 5,
}
REF_CATS = ["Global_Objects", "Operators", "Statements", "Functions", "Classes",
            "Regular_expressions", "Errors"]
CAT_LABEL = {
    "Global_Objects": "Built-in objects", "Operators": "Expressions & operators",
    "Statements": "Statements & declarations", "Functions": "Functions",
    "Classes": "Classes", "Regular_expressions": "Regular expressions",
    "Errors": "Errors",
}


def sidebar_order(root_doc):
    """[(path, group label)] in MDN sidebar order."""
    tree = lxml.html.fromstring(root_doc["sidebarHTML"])
    out = []

    def walk(el, groups):
        for ch in el:
            if ch.tag == "details":
                s = ch.find("summary")
                label = s.text_content().strip() if s is not None else ""
                a = s.find(".//a") if s is not None else None
                if a is not None:
                    add(a, groups)
                walk(ch, groups + [label])
            elif ch.tag == "summary":
                continue
            elif ch.tag == "a":
                add(ch, groups)
            else:
                walk(ch, groups)

    def add(a, groups):
        href = urllib.parse.unquote(a.get("href", "")).rstrip("/")
        if href.startswith(SCOPE_PREFIX):
            out.append((href, groups[0] if groups else ""))

    walk(tree, [])
    return out


def main():
    progress = load_json(PROGRESS)
    docs = {}
    for path, rec in progress.items():
        if rec["status"] == 200:
            docs[rec["canonical"]] = rec
    root = load_json(raw_path(SCOPE_PREFIX))["doc"]
    sb = sidebar_order(root)
    sb_index, sb_group = {}, {}
    for i, (p, g) in enumerate(sb):
        sb_index.setdefault(p, i)
        sb_group.setdefault(p, g)

    children = {}
    for p in docs:
        if p == SCOPE_PREFIX:
            continue
        parent = p.rsplit("/", 1)[0]
        children.setdefault(parent, []).append(p)

    def sort_key(p):
        r = docs[p]
        return (sb_index.get(p, 10 ** 6), TYPE_RANK.get(r["page_type"], 6),
                r["title"].lower(), p)

    order = []

    def dfs(p):
        order.append(p)
        for c in sorted(children.get(p, []), key=sort_key):
            dfs(c)

    R = SCOPE_PREFIX + "/Reference"
    order.append(SCOPE_PREFIX)
    dfs(SCOPE_PREFIX + "/Guide")
    order.append(R)
    for cat in REF_CATS:
        dfs(f"{R}/{cat}")
    misc = [c for c in children[R] if c.rsplit("/", 1)[1] not in REF_CATS]
    for c in sorted(misc, key=sort_key):
        dfs(c)
    missing = set(docs) - set(order)
    assert not missing, f"unplaced articles: {sorted(missing)[:5]}"
    assert len(order) == len(set(order))

    # ---- volume assignment ------------------------------------------------
    go_tops = sorted([c for c in children[f"{R}/Global_Objects"]], key=sort_key)
    go_vol = {}
    vi = 3
    for top in go_tops:
        name = top.rsplit("/", 1)[1]
        go_vol[name] = VOLUMES[vi]["id"]
        if VOLUMES[vi].get("upto") == name:
            vi += 1

    def volume_of(p):
        rel = p[len(SCOPE_PREFIX):].strip("/").split("/")
        if rel == [""] or rel[0] == "Guide":
            return 1
        if len(rel) == 1:                       # /Reference
            return 2
        cat = rel[1]
        if cat in ("Operators", "Statements"):
            return 2
        if cat != "Global_Objects":
            return 3
        if len(rel) == 2:                       # Global_Objects index
            return 4
        return go_vol[rel[2]]

    def category_of(p):
        rel = p[len(SCOPE_PREFIX):].strip("/").split("/")
        if rel == [""]:
            return "JavaScript (landing page)"
        if rel[0] == "Guide":
            g = sb_group.get(p) or sb_group.get(p.rsplit("/", 1)[0]) or "JavaScript Guide"
            return "Guide › " + g
        if len(rel) == 1:
            return "Reference (landing page)"
        cat = rel[1]
        if cat == "Global_Objects":
            return "Reference › Built-in objects" + (f" › {rel[2]}" if len(rel) > 2 else "")
        if cat in CAT_LABEL:
            return "Reference › " + CAT_LABEL[cat]
        return "Reference › Misc"

    def level_and_break(p):
        """(level 1-3 inside the volume outline, forced page break before?)"""
        rel = p[len(SCOPE_PREFIX):].strip("/").split("/")
        r = docs[p]
        if rel == [""]:
            return 1, True
        if rel[0] == "Guide":
            return (1 if len(rel) <= 2 else 2), True
        if len(rel) == 1:
            return 1, True
        cat = rel[1]
        if cat == "Global_Objects":
            if len(rel) <= 3:
                return 1, True
            nested_class = r["page_type"] in ("javascript-class", "javascript-namespace")
            return min(len(rel) - 2, 3), nested_class
        if cat in CAT_LABEL:
            return (1, True) if len(rel) == 2 else (min(len(rel) - 1, 3), False)
        return 1, True

    manifest = []
    for i, p in enumerate(order):
        r = docs[p]
        lvl, brk = level_and_break(p)
        manifest.append({
            "key": f"a{i + 1:04d}",
            "order": i + 1,
            "title": r["title"],
            "requested_url": SITE + r["requested"],
            "canonical_url": SITE + p,
            "path": p,
            "category": category_of(p),
            "page_type": r["page_type"],
            "retrieved_utc": r["retrieved"],
            "retrieval_status": r["status"],
            "source_json": SITE + urllib.parse.quote(p) + "/index.json",
            "source_sha256": r["sha256"],
            "source_last_commit": r["source_commit"],
            "mdn_modified": r["modified"],
            "volume": volume_of(p),
            "volume_file": VOLUMES[volume_of(p) - 1]["file"],
            "level": lvl,
            "page_break_before": brk,
            "inclusion": "included",
            "reason": "canonical en-US article inside /en-US/docs/Web/JavaScript/",
        })
    # requested URLs that did not yield an own article (redirect aliases, errors)
    excluded = []
    for path, rec in progress.items():
        if rec["status"] != 200:
            excluded.append({"requested_url": SITE + path, "retrieval_status": rec["status"],
                             "inclusion": "excluded", "reason": "not retrievable: " + rec.get("error", "")})
        elif rec["canonical"] != path:
            excluded.append({"requested_url": SITE + path, "canonical_url": SITE + rec["canonical"],
                             "retrieval_status": 200, "inclusion": "excluded",
                             "reason": "alias/redirect of canonical article (included once)"})
    inv = load_json(os.path.join(os.path.dirname(MANIFEST_DIR), "data", "inventory.json"))
    save_json(os.path.join(MANIFEST_DIR, "manifest.json"), {
        "source": SITE + SCOPE_PREFIX,
        "inventory_retrieved": inv["retrieved"],
        "inventory_counts": {"sitemap": inv["sitemap_count"],
                             "search_index": inv["search_index_count"],
                             "union": len(inv["urls"])},
        "volumes": VOLUMES,
        "articles": manifest,
        "excluded": excluded,
    })
    cols = ["key", "order", "title", "requested_url", "canonical_url", "category", "page_type",
            "retrieved_utc", "retrieval_status", "volume", "volume_file", "inclusion", "reason",
            "source_sha256", "source_last_commit", "mdn_modified"]
    with open(os.path.join(MANIFEST_DIR, "manifest.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        for m in manifest + excluded:
            w.writerow(m)
    from collections import Counter
    c = Counter(m["volume"] for m in manifest)
    print(f"manifest: {len(manifest)} included, {len(excluded)} excluded")
    for v in VOLUMES:
        print(f"  vol {v['id']}: {c[v['id']]:4d} articles  {v['title']}")


if __name__ == "__main__":
    main()
