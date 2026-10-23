"""Shared helpers for the static-site tests (standard library only)."""
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
# Tags whose nesting must balance; a stray/missing close tag here breaks layout.
TRACKED = {"html", "head", "body", "div", "p", "span", "a", "h1", "h2", "h3",
           "article", "figure", "figcaption", "button", "script", "style", "b"}


class Page(HTMLParser):
    """Parses one HTML file and records what the tests care about."""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.rel = path.relative_to(ROOT).as_posix()
        self.doctype = None
        self.lang = None
        self.title = ""
        self.meta = {}
        self.links = []        # (tag, attr, value, attrs-dict)
        self.anchors = []      # attrs-dict of every <a>
        self.images = []       # attrs-dict of every <img>
        self.ids = set()
        self.counts = {}
        self.script_text = ""
        self.style_text = ""
        self.errors = []
        self._stack = []
        self._in = None
        self.feed(path.read_text(encoding="utf-8"))
        self.close()
        if self._stack:
            self.errors.append("unclosed: " + ",".join(t for t, _ in self._stack[-5:]))

    def handle_decl(self, decl):
        self.doctype = decl

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.counts[tag] = self.counts.get(tag, 0) + 1
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "a":
            self.anchors.append(a)
        if tag == "img":
            self.images.append(a)
        for attr in ("href", "src"):
            if attr in a and a[attr] is not None:
                self.links.append((tag, attr, a[attr], a))
        if tag in ("title", "script", "style"):
            self._in = tag
        if tag in TRACKED:
            self._stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag == self._in:
            self._in = None
        if tag not in TRACKED:
            return
        if not self._stack or self._stack[-1][0] != tag:
            self.errors.append(f"unexpected </{tag}> at line {self.getpos()[0]}")
            # resync so one mistake isn't reported repeatedly
            for i in range(len(self._stack) - 1, -1, -1):
                if self._stack[i][0] == tag:
                    del self._stack[i:]
                    break
        else:
            self._stack.pop()

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "script":
            self.script_text += data
        elif self._in == "style":
            self.style_text += data

    # -- convenience -------------------------------------------------------
    def hrefs(self, cls=None):
        out = []
        for a in self.anchors:
            if "href" not in a:
                continue
            classes = (a.get("class") or "").split()
            if cls is None or cls in classes:
                out.append(a["href"])
        return out


@lru_cache(maxsize=None)
def page(rel):
    return Page(ROOT / rel)


def all_html():
    return sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("**/*.html")
                  if ".git" not in p.parts and "node_modules" not in p.parts)


def sarga_dirs():
    return sorted(p.name for p in ROOT.glob("sarga-[0-9][0-9]") if p.is_dir())


def verses(sarga):
    nums = [int(m.group(1)) for p in (ROOT / sarga).glob("verse-*.html")
            if (m := re.fullmatch(r"verse-(\d+)\.html", p.name))]
    return sorted(nums)


def reading_order():
    """Every verse page in book order: ['sarga-01/verse-1.html', ...]."""
    return [f"{s}/verse-{n}.html" for s in sarga_dirs() for n in verses(s)]


def readme_verse_counts():
    """{sarga number: verse count} from the README 'Contents' table."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    return {int(m.group(1)): int(m.group(2))
            for m in re.finditer(r"^\|\s*(\d+)\s*\|[^|]*\|\s*(\d+)\s*\|", text, re.M)}


def resolve(from_rel, href):
    """Map a relative href on page `from_rel` to (Path, fragment), or None if external."""
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return None
    path = unquote(parts.path)
    base = (ROOT / from_rel).parent
    target = (base / path) if path else (ROOT / from_rel)
    return target.resolve(), parts.fragment
