"""Static checks for the Vyadeshwar library: rendering, links, images, navigation.

Run with:  python3 -m unittest discover -s tests -v     (or `make test`)
Set CHECK_EXTERNAL=1 to also HEAD-request the external links (needs internet).
"""
import base64
import os
import re
import unittest
import urllib.request
from urllib.parse import urlsplit

from helpers import (ROOT, all_html, page, reading_order, readme_verse_counts,
                     resolve, sarga_dirs, verses)

PAGES = all_html()
VERSE_PAGES = reading_order()
EXPECTED_SARGAS = 14
ALLOWED_EXTERNAL_HOSTS = {"www.google.com"}


def sarga_num(rel):
    return int(re.search(r"sarga-(\d+)", rel).group(1))


class LibraryShape(unittest.TestCase):
    def test_fourteen_sargas_each_with_index(self):
        self.assertEqual(len(sarga_dirs()), EXPECTED_SARGAS)
        for s in sarga_dirs():
            self.assertTrue((ROOT / s / "index.html").is_file(), s)

    def test_root_and_intro_pages_exist(self):
        self.assertTrue((ROOT / "index.html").is_file())
        self.assertTrue((ROOT / "intro-verses" / "index.html").is_file())
        self.assertTrue((ROOT / ".nojekyll").is_file(), "needed for GitHub Pages")

    def test_verse_numbers_are_contiguous_from_one(self):
        for s in sarga_dirs():
            nums = verses(s)
            self.assertEqual(nums, list(range(1, len(nums) + 1)), s)

    def test_verse_counts_match_readme_table(self):
        table = readme_verse_counts()
        self.assertEqual(len(table), EXPECTED_SARGAS, "README contents table not parsed")
        for s in sarga_dirs():
            self.assertEqual(len(verses(s)), table[int(s.split("-")[1])], s)
        total = sum(table.values())
        self.assertEqual(len(VERSE_PAGES), total)
        self.assertIn(f"**{total} verses**", (ROOT / "README.md").read_text(encoding="utf-8"))


class PageRendering(unittest.TestCase):
    def test_every_page_is_well_formed(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                p = page(rel)
                self.assertEqual((p.doctype or "").lower(), "doctype html")
                self.assertTrue(p.lang, "missing <html lang>")
                self.assertTrue(p.title.strip(), "missing <title>")
                self.assertIn("viewport", p.meta)
                self.assertEqual(p.errors, [])

    def test_charset_declared(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                head = (ROOT / rel).read_text(encoding="utf-8")[:2000].lower()
                self.assertIn('charset="utf-8"', head)

    def test_self_contained_styles_and_scripts(self):
        """CSS/JS are inline; nothing external should be needed to render."""
        for rel in PAGES:
            with self.subTest(page=rel):
                p = page(rel)
                self.assertEqual(p.counts.get("style"), 1)
                self.assertEqual(p.counts.get("script"), 1)
                self.assertNotIn("link", p.counts, "unexpected <link> (stylesheet/font)")
                self.assertGreater(len(p.style_text), 500)

    def test_long_words_wrap_on_narrow_screens(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                self.assertIn(".wrap{overflow-wrap:anywhere}", page(rel).style_text)

    def test_verse_pages_have_one_h1_and_a_verse_block(self):
        for rel in VERSE_PAGES:
            with self.subTest(page=rel):
                p = page(rel)
                self.assertEqual(p.counts.get("h1"), 1)
                self.assertIn('class="verse-block"', (ROOT / rel).read_text(encoding="utf-8"))

    def test_language_toggle_wired_up(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                p = page(rel)
                text = (ROOT / rel).read_text(encoding="utf-8")
                for lang in ("en", "both", "mr"):
                    self.assertIn(f'data-setlang="{lang}"', text)
                self.assertIn("vyadeshwar-lang", p.script_text)
                self.assertIn('data-lang="mr"] .lang-en{display:none}', p.style_text)
                self.assertIn('data-lang="en"] .lang-mr{display:none}', p.style_text)
                self.assertIn('<body data-lang="both">', text)

    def test_ids_unique_within_page(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                ids = re.findall(r'\sid="([^"]+)"', re.sub(r"base64,[A-Za-z0-9+/=]+", "", (ROOT / rel).read_text(encoding="utf-8")))
                self.assertEqual(len(ids), len(set(ids)))


class Links(unittest.TestCase):
    def test_relative_links_resolve(self):
        checked = 0
        for rel in PAGES:
            for tag, attr, value, _ in page(rel).links:
                if value.startswith(("data:", "mailto:", "javascript:")):
                    continue
                target = resolve(rel, value)
                if target is None:
                    continue
                with self.subTest(page=rel, link=value):
                    path, frag = target
                    self.assertFalse(value.startswith("/"), "root-absolute link breaks GitHub project pages")
                    self.assertTrue(path.is_file(), f"{value} -> missing {path}")
                    self.assertTrue(str(path).startswith(str(ROOT)), "link escapes repo")
                    if frag and path.suffix == ".html":
                        rel_t = path.relative_to(ROOT).as_posix()
                        self.assertIn(frag, page(rel_t).ids, f"#{frag} not found in {rel_t}")
                    checked += 1
        self.assertGreater(checked, 4000)

    def test_link_targets_use_exact_case(self):
        """Filesystems here may be case-insensitive; GitHub Pages is not."""
        files = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("**/*")
                 if p.is_file() and ".git" not in p.parts}
        for rel in PAGES:
            for _, _, value, _ in page(rel).links:
                t = resolve(rel, value)
                if t and t[0].is_file():
                    with self.subTest(page=rel, link=value):
                        self.assertIn(t[0].relative_to(ROOT).as_posix(), files)

    def test_external_links_are_safe(self):
        count = 0
        for rel in PAGES:
            for tag, attr, value, attrs in page(rel).links:
                parts = urlsplit(value)
                if not parts.scheme or parts.scheme == "data":
                    continue
                count += 1
                with self.subTest(page=rel, link=value):
                    self.assertEqual(parts.scheme, "https")
                    self.assertIn(parts.hostname, ALLOWED_EXTERNAL_HOSTS)
                    self.assertEqual(attr, "href", "external resources must not be loaded")
                    if attrs.get("target") == "_blank":
                        self.assertIn("noopener", attrs.get("rel", ""))
        self.assertGreater(count, 0)

    @unittest.skipUnless(os.environ.get("CHECK_EXTERNAL"), "set CHECK_EXTERNAL=1 to hit the network")
    def test_external_links_reachable(self):
        seen = set()
        for rel in PAGES:
            for tag, attr, value, _ in page(rel).links:
                if value.startswith("https://") and value not in seen:
                    seen.add(value)
                    with self.subTest(link=value):
                        req = urllib.request.Request(value, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=20) as r:
                            self.assertLess(r.status, 400)


class Navigation(unittest.TestCase):
    def test_root_links_to_every_section(self):
        hrefs = set(page("index.html").hrefs())
        self.assertIn("intro-verses/index.html", hrefs)
        for s in sarga_dirs():
            self.assertIn(f"{s}/index.html", hrefs)

    def test_section_index_breadcrumbs(self):
        for s in sarga_dirs() + ["intro-verses"]:
            rel = f"{s}/index.html"
            with self.subTest(page=rel):
                p = page(rel)
                self.assertIn("../index.html", p.hrefs("brand"))
                self.assertIn("../index.html", p.hrefs("crumb"))

    def test_verse_breadcrumbs(self):
        for rel in VERSE_PAGES:
            with self.subTest(page=rel):
                p = page(rel)
                self.assertEqual(p.hrefs("brand"), ["../index.html"])
                self.assertEqual(p.hrefs("crumb"), ["../index.html", "index.html"])

    def test_sarga_index_lists_every_verse_in_order(self):
        for s in sarga_dirs():
            with self.subTest(sarga=s):
                listed = [h for h in page(f"{s}/index.html").hrefs("verse-link")]
                self.assertEqual(listed, [f"verse-{n}.html" for n in verses(s)])

    def test_prev_next_chain_follows_reading_order(self):
        order = VERSE_PAGES
        for i, rel in enumerate(order):
            with self.subTest(page=rel):
                p = page(rel)
                prev = [a["href"] for a in p.anchors if "href" in a and a.get("class") is None
                        and re.fullmatch(r"(\.\./sarga-\d+/)?verse-\d+\.html|(\.\./)?[\w-]+/?index\.html|index\.html", a["href"])
                        and a["href"] not in ("index.html", "../index.html")]
                nxt = [a["href"] for a in p.anchors if "next" in (a.get("class") or "").split()]
                self.assertEqual(len(nxt), 1)
                got_next = resolve(rel, nxt[0])[0]
                if i + 1 < len(order):
                    self.assertEqual(got_next, (ROOT / order[i + 1]).resolve())
                else:
                    self.assertEqual(got_next, (ROOT / sarga_dirs()[-1] / "index.html").resolve())
                if i > 0:
                    self.assertIn(
                        os.path.relpath(ROOT / order[i - 1], (ROOT / rel).parent).replace(os.sep, "/"),
                        prev)

    def test_page_numbers_match_filenames(self):
        for rel in VERSE_PAGES:
            n = re.search(r"verse-(\d+)", rel).group(1)
            with self.subTest(page=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertRegex(text, rf'<span class="here">Verse {n}</span>')
                self.assertIn(f"Sarga {sarga_num(rel)}", page(rel).title + text[:20000])


class Images(unittest.TestCase):
    MAGIC = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}

    def test_images_are_embedded_valid_and_described(self):
        total = 0
        for rel in PAGES:
            for img in page(rel).images:
                total += 1
                with self.subTest(page=rel, alt=img.get("alt")):
                    src = img.get("src", "")
                    m = re.fullmatch(r"data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=\s]+)", src)
                    self.assertTrue(m, "image must be an embedded png/jpeg data URI")
                    raw = base64.b64decode(m.group(2), validate=False)
                    self.assertTrue(raw.startswith(self.MAGIC[m.group(1)]), "data does not match mime type")
                    self.assertGreater(len(raw), 1000, "image looks truncated")
                    self.assertTrue((img.get("alt") or "").strip(), "image needs alt text")
        self.assertGreaterEqual(total, 22)

    def test_place_cards_link_to_maps_and_gallery(self):
        """Verses in sargas 11-12 that name a shrine carry a 'Place' card."""
        cards = [r for r in VERSE_PAGES if 'class="place-card"' in (ROOT / r).read_text(encoding="utf-8")]
        self.assertGreaterEqual(len(cards), 14)
        for rel in cards:
            with self.subTest(page=rel):
                self.assertIn(sarga_num(rel), (11, 12))
                p = page(rel)
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertRegex(text, r'href="https://www\.google\.com/maps/search/\?api=1&amp;query=-?\d+\.\d+,-?\d+\.\d+"')
                self.assertIn("../intro-verses/index.html", p.hrefs())
                self.assertGreaterEqual(len(p.images), 1)
                self.assertIn(".place-card{", p.style_text)

    def test_page_size_reasonable(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                self.assertLess((ROOT / rel).stat().st_size, 16 * 1024 * 1024)


class ContentHygiene(unittest.TestCase):
    """Guards against regressions of issues fixed earlier."""

    @staticmethod
    def visible(rel):
        s = (ROOT / rel).read_text(encoding="utf-8")
        s = re.sub(r"base64,[A-Za-z0-9+/=]+", "", s)
        return re.sub(r"<style.*?</style>|<script.*?</script>", "", s, flags=re.S)

    def test_no_markdown_leftovers(self):
        pat = re.compile(r"(?<![\w*\\])\*\*?[^*<>\s][^*<>]*?\*\*?(?![\w*])")
        for rel in PAGES:
            with self.subTest(page=rel):
                self.assertIsNone(pat.search(self.visible(rel)))
                self.assertNotRegex(self.visible(rel), r"`[^`]+`|\]\([^)]+\)")

    def test_proper_double_danda(self):
        for rel in PAGES + ["README.md"]:
            with self.subTest(page=rel):
                text = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("।।", text, "use the single double-danda character ॥")

    def test_known_spellings(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                text = self.visible(rel)
                self.assertNotRegex(text, r"Vyāḍi(?!nā)")
                self.assertNotIn("Sakurana", text)

    def test_closing_dedication(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                self.assertIn("॥ श्रीव्याडेश्वरार्पणमस्तु ॥", self.visible(rel))

    def test_no_replacement_characters(self):
        for rel in PAGES:
            with self.subTest(page=rel):
                self.assertNotIn("�", (ROOT / rel).read_text(encoding="utf-8"), "encoding damage")


if __name__ == "__main__":
    unittest.main()
