"""Step 1+2: discover the inventory and retrieve every article's rendered JSON.

Inventory sources (cross-checked against each other):
  * the official en-US sitemap        (sitemaps/en-us/sitemap.xml.gz)
  * the official en-US search index   (en-US/search-index.json)
  * every in-scope link found inside retrieved articles (link crawl), which
    is how redirects and aliases are discovered and resolved.

Each article is retrieved once from  <url>/index.json  (the rendered document
that the MDN website itself is built from - macros, includes and generated
content are already resolved).  Results are cached in data/raw and tracked in
manifest/progress.json so an interrupted run resumes without re-downloading.

Usage:  python fetch.py [--refresh]
"""
import datetime
import gzip
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import (DATA, MANIFEST_DIR, SCOPE_PREFIX, SITE, USER_AGENT,
                    in_scope, load_json, raw_path, save_json)

WORKERS = 3
DELAY = 0.25            # seconds between requests per worker (~10 req/s max, usually far less)
PROGRESS = os.path.join(MANIFEST_DIR, "progress.json")
lock = threading.Lock()


def http_get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return r.status, r.geturl(), body
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return e.code, url, b""
            last = e
            if e.code == 429:
                time.sleep(20 * (i + 1))
        except Exception as e:          # network hiccup: back off and retry
            last = e
        time.sleep(2 * (i + 1))
    return 0, url, repr(last).encode()


def discover():
    today = datetime.date.today().isoformat()
    st, _, body = http_get(SITE + "/sitemaps/en-us/sitemap.xml.gz")
    assert st == 200, "sitemap fetch failed"
    try:
        xml = gzip.decompress(body).decode("utf-8")
    except OSError:
        xml = body.decode("utf-8")
    sm = {u.replace(SITE, "").rstrip("/") for u in re.findall(r"<loc>([^<]*)</loc>", xml)}
    sm = {u for u in sm if in_scope(u)}
    st, _, body = http_get(SITE + "/en-US/search-index.json")
    assert st == 200, "search index fetch failed"
    si = {e["url"].rstrip("/") for e in json.loads(body) if in_scope(e["url"].rstrip("/"))}
    inv = {}
    for u in sorted(sm | si):
        inv[u] = {"sources": [s for s, ok in (("sitemap", u in sm), ("search-index", u in si)) if ok]}
    save_json(os.path.join(DATA, "inventory.json"),
              {"retrieved": today, "sitemap_count": len(sm), "search_index_count": len(si),
               "urls": inv})
    print(f"inventory: sitemap={len(sm)} search-index={len(si)} union={len(inv)}")
    return inv


def fetch_one(path, progress, refresh=False):
    rp = raw_path(path)
    with lock:
        done = progress.get(path)
    if done and done.get("status") in (200, 404, 410) and not refresh and \
            (done["status"] != 200 or os.path.exists(rp)):
        return
    url = SITE + urllib.parse.quote(path) + "/index.json"
    st, final, body = http_get(url)
    rec = {"requested": path, "status": st,
           "retrieved": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
    if st == 200:
        try:
            doc = json.loads(body)["doc"]
        except Exception as e:
            rec.update(status=-1, error=f"bad json: {e!r}")
        else:
            with open(rp, "wb") as f:
                f.write(body)
            rec.update(canonical=doc["mdn_url"], title=doc["title"],
                       final_url=final.replace(SITE, ""),
                       sha256=hashlib.sha256(body).hexdigest(),
                       modified=doc.get("modified"),
                       source_commit=(doc.get("source") or {}).get("last_commit_url"),
                       page_type=doc.get("pageType"), bytes=len(body))
    else:
        rec["error"] = body.decode("utf-8", "replace")[:200]
    with lock:
        progress[path] = rec
    time.sleep(DELAY)


def run_batch(paths, progress, refresh=False):
    n = [0]

    def job(p):
        fetch_one(p, progress, refresh)
        with lock:
            n[0] += 1
            if n[0] % 50 == 0:
                save_json(PROGRESS, progress)
                print(f"  {n[0]}/{len(paths)}", flush=True)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(job, paths))
    save_json(PROGRESS, progress)


def linked_paths(progress):
    """All in-scope paths linked from retrieved article bodies."""
    found = {}
    for path, rec in progress.items():
        if rec.get("status") != 200:
            continue
        doc = load_json(raw_path(path))["doc"]
        for sec in doc["body"]:
            html = sec["value"].get("content") or ""
            for href in re.findall(r'href="([^"]+)"', html):
                href = href.replace("&amp;", "&")
                if href.startswith(SITE):
                    href = href[len(SITE):]
                href = urllib.parse.unquote(href.split("#")[0].split("?")[0]).rstrip("/")
                if in_scope(href):
                    found.setdefault(href, path)
    return found


def main():
    refresh = "--refresh" in sys.argv
    inv = discover()
    progress = load_json(PROGRESS, {})
    run_batch(sorted(inv), progress, refresh)
    # Link crawl: anything in scope that articles link to but the inventory
    # does not list is requested too, so redirects / aliases get resolved.
    for rnd in range(3):
        extra = [p for p in linked_paths(progress) if p not in progress]
        print(f"link crawl round {rnd}: {len(extra)} unlisted in-scope link targets")
        if not extra:
            break
        run_batch(sorted(extra), progress, refresh)
    ok = sum(1 for r in progress.values() if r["status"] == 200)
    bad = {p: r["status"] for p, r in progress.items() if r["status"] != 200}
    print(f"done: {ok} ok, {len(bad)} not ok")
    for p, s in sorted(bad.items()):
        print("  ", s, p)


if __name__ == "__main__":
    main()
