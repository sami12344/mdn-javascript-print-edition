"""Convert one retrieved MDN article (rendered JSON) into print HTML.

The article text is never regenerated: section HTML is parsed, website-only
elements are removed or replaced, ids/links are rewritten for the PDF, and the
tree is serialized again.  Everything this script *adds* (source line,
availability line, print notes, labels, compatibility tables) carries a
`data-gen` attribute so the verifier can separate MDN text from additions.

Documented transformations (the complete list):
  T1  prev/next navigation buttons (ul.prev-next) are removed.
  T2  div.code-example -> print code block; the language name is kept as a
      label; example-bad / example-good colour coding becomes a text label.
      Code text is copied verbatim; long blocks are divided into chunks at
      blank lines purely so that page breaks fall between logical paragraphs.
  T3  <interactive-example> widgets -> a print note; their source code block
      (which follows in the MDN HTML) is kept.
  T4  live-sample <iframe>s -> a print note with the URL of the live output.
  T5  code blocks that MDN hides on the page (class "hidden", supporting code
      of live samples) are kept and labelled as hidden-on-MDN.
  T6  self-links on definition terms (<dt><a href="#id">) are unwrapped.
  T7  ids are prefixed with the article key; links to articles in the same
      volume become internal PDF links, all others absolute MDN URLs.
  T8  status icons (empty <span class="icon" aria-label="...">) become text
      badges showing their label.
  T9  tables whose first row consists only of header cells get that row moved
      into <thead> so it repeats after a page break.
  T10 images are downloaded and embedded.
  T11 Specifications and Browser compatibility sections, which the website
      builds client-side from data, are rendered from that same data.
  T12 tables with 8 or more columns are printed rotated by 90 degrees on a page
      of their own (the print equivalent of a landscape page), because they
      cannot be set legibly across the portrait column.
"""
import datetime
import hashlib
import html
import os
import re
import urllib.parse
import urllib.request

import lxml.html
from lxml import etree

import bcd
from common import IMG, SCOPE_PREFIX, SITE, USER_AGENT, load_json, raw_path

KEEP_LINES = 14        # code blocks up to this many lines are never split
CHUNK_LINES = 8        # target size of break-free chunks in longer blocks
CHUNK_MAX = 10         # a blank-line-free run longer than this may break anywhere
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _gen(tag, cls, text=None, **attrs):
    el = etree.Element(tag)
    el.set("class", cls)
    el.set("data-gen", "1")
    for k, v in attrs.items():
        el.set(k, v)
    if text:
        el.text = text
    return el


def split_code(text):
    """Split code into chunks at blank lines.  ''.join(result) == text, always."""
    lines = re.split(r"(?<=\n)", text)
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) <= KEEP_LINES:
        return [text]
    paras, cur = [], []
    for i, ln in enumerate(lines):
        cur.append(ln)
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        if ln.strip() == "" and nxt is not None and nxt.strip() != "":
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    out, buf = [], []
    for p in paras:
        if buf and len(buf) + len(p) > CHUNK_LINES:
            out.append(buf)
            buf = []
        buf = buf + p
    if buf:
        out.append(buf)
    chunks = ["".join(c) for c in out]
    assert "".join(chunks) == text
    return chunks


def month_year(iso):
    try:
        d = datetime.date.fromisoformat(iso[:10])
        return f"{MONTHS[d.month - 1]} {d.year}"
    except Exception:
        return iso or ""


class Converter:
    def __init__(self, manifest):
        self.articles = manifest["articles"]
        self.by_path = {a["path"]: a for a in self.articles}
        self._ids = {}
        self._docs = {}
        self.issues = []

    # ---- helpers --------------------------------------------------------
    def doc(self, path):
        if path not in self._docs:
            self._docs[path] = load_json(raw_path(path))["doc"]
        return self._docs[path]

    def ids(self, path):
        """Map original id -> sanitized, article-prefixed id."""
        if path not in self._ids:
            key = self.by_path[path]["key"]
            doc = self.doc(path)
            found = []
            for sec in doc["body"]:
                v = sec["value"]
                if v.get("id"):
                    found.append(v["id"])
                found += re.findall(r'\sid="([^"]+)"', v.get("content") or "")
            m, used = {}, set()
            for i in found:
                i = html.unescape(i)
                if i in m:
                    continue
                s = key + "--" + re.sub(r"[^A-Za-z0-9_.-]", "_", i)
                while s in used:
                    s += "_"
                used.add(s)
                m[i] = s
            self._ids[path] = m
        return self._ids[path]

    def resolve(self, href, art):
        """Rewrite a link for the PDF.  Returns (new_href, kind)."""
        if href.startswith("#"):
            frag = urllib.parse.unquote(href[1:])
            m = self.ids(art["path"])
            return "#" + m.get(frag, art["key"]), "internal"
        full = href
        if full.startswith(SITE):
            full = full[len(SITE):]
        if full.startswith("/"):
            path, _, frag = full.partition("#")
            path = urllib.parse.unquote(path.split("?")[0]).rstrip("/")
            target = self.by_path.get(path)
            if target is not None and target["volume"] == art["volume"]:
                frag = urllib.parse.unquote(frag)
                if frag:
                    return "#" + self.ids(path).get(frag, target["key"]), "internal"
                return "#" + target["key"], "internal"
            return SITE + full, ("collection" if target is not None else "mdn")
        return href, "external"

    def image(self, src):
        """Download (once) and return a file:// URL for an article image."""
        url = SITE + src if src.startswith("/") else src
        name = hashlib.sha1(url.encode()).hexdigest()[:10] + "_" + \
            re.sub(r"[^A-Za-z0-9_.-]", "_", url.rsplit("/", 1)[-1])
        dest = os.path.join(IMG, name)
        if not os.path.exists(dest):
            req = urllib.request.Request(urllib.parse.quote(url, safe=":/%"),
                                         headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                with open(dest, "wb") as f:
                    f.write(data)
            except Exception as e:
                self.issues.append(f"image not retrievable: {url} ({e!r})")
                return None
        return "file:///" + dest.replace("\\", "/")

    # ---- code -----------------------------------------------------------
    def code_block(self, div, art, stats):
        pre = div.find(".//pre")
        iframe = div.find(".//iframe")
        if iframe is not None and pre is None:
            stats["live_samples"] += 1
            lid = iframe.get("data-live-id") or ""
            url = SITE + art["path"] + ("#" + lid if lid else "")
            note = _gen("p", "pnote")
            note.text = (f"▷ Live sample output (“{iframe.get('title') or lid}”) is rendered in the "
                         f"browser on MDN and cannot be reproduced on paper. See it running at ")
            a = etree.SubElement(note, "a", href=url)
            a.text = url.replace("https://", "")
            a.tail = " ."
            return note
        if pre is None:
            return None
        classes = (pre.get("class") or "").split()
        lang = ""
        if "brush:" in classes:
            i = classes.index("brush:")
            lang = classes[i + 1] if i + 1 < len(classes) else ""
        text = pre.text_content()
        stats["code_blocks"] += 1
        chunks = split_code(text)
        n_lines = text.count("\n") + (0 if text.endswith("\n") else 1)
        block = etree.Element("div")
        cls = ["codeblock"]
        labels = [lang] if lang and lang != "plain" else []
        if "example-bad" in classes:
            cls.append("bad")
            labels.append("✗ bad example")
        if "example-good" in classes:
            cls.append("good")
            labels.append("✓ good example")
        if "interactive-example" in classes:
            labels.append("interactive example source")
        if "hidden" in classes:
            stats["hidden_code"] += 1
            labels.append("hidden on the MDN page (supporting code for the live sample)")
        if len(chunks) == 1 and n_lines <= KEEP_LINES:
            cls.append("keep")
        block.set("class", " ".join(cls))
        if labels:
            # the language name is MDN text (span.language-name); qualifiers are additions
            lab = etree.SubElement(block, "div")
            lab.set("class", "codelabel")
            rest = labels
            src_lang = div.xpath('.//span[contains(@class,"language-name")]')
            if src_lang:
                sp = etree.SubElement(lab, "span")
                sp.set("class", "lang")
                sp.text = src_lang[0].text_content()
                if lang and lang != "plain":
                    rest = labels[1:]
            if rest:
                lab.append(_gen("span", "qual", (" · " if len(lab) else "") + " · ".join(rest)))
        npre = etree.SubElement(block, "pre")
        npre.set("class", "code")
        code = etree.SubElement(npre, "code")
        if len(chunks) == 1:
            code.text = text
        else:
            for c in chunks:
                sp = etree.SubElement(code, "span")
                sp.set("class", "ck" if c.count("\n") <= CHUNK_MAX else "ck long")
                sp.text = c
        return block

    # ---- prose sections ---------------------------------------------------
    def prose(self, content, art, stats):
        root = lxml.html.fragment_fromstring(content, create_parent="div")
        # T1 navigation buttons
        for ul in root.xpath('.//ul[contains(concat(" ",@class," ")," prev-next ")]'):
            stats["prev_next_removed"] += 1
            ul.drop_tree()
        # T3 interactive examples
        for ie in root.xpath(".//interactive-example"):
            stats["interactive_examples"] += 1
            note = _gen("p", "pnote")
            note.text = (f"▷ Interactive example on MDN: “{ie.get('name') or ''}”. It runs live in the "
                         f"browser there; its source code follows.")
            note.tail = ie.tail
            ie.getparent().replace(ie, note)
        # T2/T4/T5 code blocks
        for div in root.xpath('.//div[contains(concat(" ",@class," ")," code-example ")]'):
            new = self.code_block(div, art, stats)
            if new is None:
                continue
            new.tail = div.tail
            div.getparent().replace(div, new)
        for pre in root.xpath('.//pre[not(@class="code")]'):
            # any <pre> not wrapped in div.code-example: keep verbatim, style as code
            stats["code_blocks"] += 1
            pre.set("class", "code bare")
        for fr in root.xpath(".//iframe"):
            self.issues.append(f"{art['path']}: unhandled iframe")
        # T8 status icons
        for sp in root.xpath('.//span[contains(concat(" ",@class," ")," icon ")][@aria-label]'):
            stats["status_icons"] += 1
            sp.set("class", "badge icon-badge")
            sp.set("data-gen", "1")
            sp.text = sp.get("aria-label")
            for a in ("role", "title", "aria-label"):
                sp.attrib.pop(a, None)
        # T6 dt self links
        for a in root.xpath(".//dt[@id]/a[starts-with(@href,'#')]"):
            if a.get("href") == "#" + a.getparent().get("id"):
                a.drop_tag()
        # T9 header rows
        for table in root.xpath(".//table"):
            stats["tables"] += 1
            if table.find("thead") is None:
                tb = table.find("tbody")
                rows = (tb if tb is not None else table).findall("tr")
                if len(rows) > 1 and all(c.tag == "th" for c in rows[0]) and \
                        not any(c.get("rowspan") for c in rows[0]):
                    thead = etree.Element("thead")
                    thead.set("data-moved", "1")
                    rows[0].getparent().remove(rows[0])
                    thead.append(rows[0])
                    cap = table.find("caption")
                    idx = 0 if cap is None else list(table).index(cap) + 1
                    table.insert(idx, thead)
            ncols = max((sum(int(c.get("colspan") or 1) for c in tr) for tr in table.iter("tr")),
                        default=0)
            table.set("data-cols", str(ncols))
            if ncols >= 8:
                # T12: rotate very wide tables (wrapper carries the rotation, see print.css)
                stats["rotated_tables"] += 1
                target = table.getparent() if table.getparent().tag == "figure" else table
                wrap = etree.Element("div")
                wrap.set("class", "rot")
                wrap.tail = target.tail
                target.tail = None
                target.getparent().replace(target, wrap)
                wrap.append(target)
            # rows that carry a tall merged cell may be split at a page break; otherwise the
            # whole merged group would be pushed to the next page
            for tr in table.iter("tr"):
                if any(int(c.get("rowspan") or 1) >= 4 for c in tr):
                    tr.set("class", ((tr.get("class") or "") + " rs").strip())
        # T10 images
        for img in root.xpath(".//img"):
            stats["images"] += 1
            local = self.image(img.get("src"))
            if local:
                img.set("src", local)
            img.attrib.pop("loading", None)
            # figures are enlarged by one third (1 CSS px -> 1 pt) so that lettering inside
            # diagrams stays readable on paper; never wider than the text column (CSS)
            w = img.get("width")
            if w is None and local and local.lower().endswith(".svg"):
                try:
                    with open(local[len("file:///"):], encoding="utf-8", errors="replace") as f:
                        head = f.read(3000)
                    tag = re.search(r"<svg[^>]*>", head, re.S).group(0)
                    m = re.search(r'\swidth="([\d.]+)(?:px)?"', tag)
                    vb = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)', tag)
                    w = m.group(1) if m else (vb.group(1) if vb else None)
                except Exception:
                    w = None
            try:
                img.set("width", str(round(min(float(w) * 4 / 3, 646))))
                img.attrib.pop("height", None)
            except (TypeError, ValueError):
                pass
        for d in root.xpath(".//details"):
            d.set("open", "open")
        # T7 ids and links
        idmap = self.ids(art["path"])
        for el in root.xpath(".//*[@id]"):
            el.set("id", idmap.get(el.get("id"), art["key"] + "--" + el.get("id")))
        for a in root.xpath(".//a[@href]"):
            if a.get("data-gen-link"):
                continue
            new, kind = self.resolve(a.get("href"), art)
            a.set("href", new)
            stats["links_" + kind] += 1
            for attr in ("target", "title", "rel"):
                a.attrib.pop(attr, None)
            if kind == "internal":
                a.set("class", "xi")
        out = (root.text or "") and html.escape(root.text)
        return out + "".join(lxml.html.tostring(ch, encoding="unicode") for ch in root)

    # ---- generated sections ------------------------------------------------
    def specifications(self, v, stats):
        specs = v.get("specifications") or []
        if not specs:
            stats["spec_empty"] += 1
            return ('<p class="pnote" data-gen="1">▷ MDN lists no specification for this '
                    'feature.</p>')
        rows = []
        for s in specs:
            stats["spec_rows"] += 1
            url = s.get("bcdSpecificationURL") or ""
            frag = url.partition("#")[2]
            rows.append(
                f'<tr><td><a href="{html.escape(url)}">{html.escape(s.get("title") or url)}</a>'
                + f'<br><span class="specurl">{html.escape(url)}</span></td></tr>')
        return ('<table class="specs" data-gen="spec"><thead><tr><th>Specification</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>')

    def compat(self, v, art, stats):
        q = v.get("query")
        out, n = bcd.render(q, art["key"]) if q else (None, 0)
        if out is None:
            stats["bcd_missing"] += 1
            self.issues.append(f"{art['path']}: no compatibility data for query {q!r}")
            return (f'<p class="pnote" data-gen="1">▷ No compatibility data found for '
                    f'<code>{html.escape(str(q))}</code>.</p>')
        stats["bcd_tables"] += 1
        stats["bcd_rows"] += n
        return out

    def baseline(self, doc):
        b = doc.get("baseline")
        if not b:
            return ""
        lvl = b.get("baseline")
        if lvl == "high":
            t = ("<b>Baseline: Widely available</b> — available across major browsers since "
                 f"{month_year(b.get('baseline_low_date'))}.")
        elif lvl == "low":
            y = (b.get("baseline_low_date") or "")[:4]
            t = (f"<b>Baseline {y}: Newly available</b> — works across the latest browser versions "
                 f"since {month_year(b.get('baseline_low_date'))}; may not work in older ones.")
        else:
            t = ("<b>Limited availability</b> — not Baseline: does not work in some of the most "
                 "widely-used browsers.")
        return f'<div class="avail" data-gen="1">{t}</div>'

    # ---- whole article ------------------------------------------------------
    def article(self, art):
        """Return (html, stats) for one manifest entry."""
        from collections import Counter
        stats = Counter()
        doc = self.doc(art["path"])
        key = art["key"]
        idmap = self.ids(art["path"])
        crumbs = " › ".join(p["title"] for p in doc.get("parents", [])[1:-1])
        url = SITE + art["path"]
        mod = (doc.get("modified") or "")[:10]
        cls = f"art lvl{art['level']}" + (" brk" if art["page_break_before"] else "")
        out = [] if art["page_break_before"] else ['<div class="need n-art"></div>']
        out += [f'<article class="{cls}" id="{key}">', '<header class="art-head">']
        if crumbs:
            out.append(f'<div class="crumbs" data-gen="1">{html.escape(crumbs)}</div>')
        out.append(f'<h1 class="art-title">{html.escape(doc["title"])}</h1>')
        out.append(f'<div class="src" data-gen="1">Source: <a href="{html.escape(url)}">'
                   f'{html.escape(url.replace("https://", ""))}</a>'
                   f'{" · MDN page last modified " + mod if mod else ""}</div>')
        out.append(self.baseline(doc))
        out.append("</header>")
        sections = []                     # [html, contains a table too wide for portrait]
        for sec in doc["body"]:
            v = sec["value"]
            sid = v.get("id")
            part = []
            if v.get("title"):
                tag = "h3" if v.get("isH3") else "h2"
                ida = f' id="{idmap[html.unescape(sid)]}"' if sid else ""
                part.append(f'<div class="need n-{tag}"></div><{tag}{ida}>{v["title"]}</{tag}>')
                stats[tag] += 1
            if sec["type"] == "prose":
                part.append(self.prose(v.get("content") or "", art, stats))
            elif sec["type"] == "specifications":
                part.append(self.specifications(v, stats))
            elif sec["type"] == "browser_compatibility":
                part.append(self.compat(v, art, stats))
            else:
                self.issues.append(f"{art['path']}: unknown section type {sec['type']}")
            h = "".join(part)
            sections.append([h, bool(re.search(r'<table[^>]*data-cols="(?:[89]|1[0-9])"', h))])
        out += [h for h, _ in sections]
        out.append("</article>")
        return "\n".join(out), stats
