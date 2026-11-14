"""Shared paths and helpers for the MDN JavaScript print compilation."""
import hashlib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
IMG = os.path.join(DATA, "img")
MANIFEST_DIR = os.path.join(ROOT, "manifest")
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "output")
SCRIPTS = os.path.dirname(os.path.abspath(__file__))  # this folder, whatever it is called

SITE = "https://developer.mozilla.org"
SCOPE_PREFIX = "/en-US/docs/Web/JavaScript"
USER_AGENT = "mdn-print-compiler/1.0 (personal offline study copy)"

for d in (RAW, IMG, MANIFEST_DIR, BUILD, OUT):
    os.makedirs(d, exist_ok=True)


def in_scope(path):
    """True if a site-relative path is inside the JavaScript subtree."""
    return path == SCOPE_PREFIX or path.startswith(SCOPE_PREFIX + "/")


def raw_name(path):
    """Stable, case-collision-free file name for a site-relative URL path."""
    h = hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
    tail = path[len("/en-US/docs/Web/"):]
    tail = re.sub(r"[^A-Za-z0-9_.-]+", "_", tail)[-80:]
    return f"{tail}__{h}.json"


def raw_path(path):
    return os.path.join(RAW, raw_name(path))


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, obj, indent=1):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, p)
