"""Optional browser smoke tests (Playwright + Chromium).

Not part of `make test`; run with `make test-e2e`.
Pages are opened from disk via file:// so no server is needed.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from helpers import sarga_dirs, verses  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

CHROMIUM = os.environ.get("CHROMIUM_PATH") or next(
    (p for p in ("/opt/pw-browsers/chromium",) if Path(p).exists()), None)


def url(rel):
    return (ROOT / rel).as_uri()


@unittest.skipIf(sync_playwright is None,
                 "playwright not installed: pip install -r requirements-e2e.txt && playwright install chromium")
class BrowserSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        kwargs = {"executable_path": CHROMIUM} if CHROMIUM else {}
        cls.browser = cls.pw.chromium.launch(**kwargs)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.ctx = self.browser.new_context(viewport={"width": 900, "height": 900})
        self.page = self.ctx.new_page()
        self.problems = []
        self.page.on("pageerror", lambda e: self.problems.append(f"js error: {e}"))
        self.page.on("console", lambda m: m.type == "error" and self.problems.append(f"console: {m.text}"))
        self.page.on("requestfailed", lambda r: self.problems.append(f"request failed: {r.url}"))

    def tearDown(self):
        self.ctx.close()

    def visible(self, selector):
        return self.page.locator(selector).first.is_visible()

    # -- loading ---------------------------------------------------------------
    def sample_pages(self):
        pages = ["index.html", "intro-verses/index.html"]
        for s in sarga_dirs():
            pages += [f"{s}/index.html", f"{s}/verse-1.html", f"{s}/verse-{verses(s)[-1]}.html"]
        return pages

    def test_pages_load_without_errors(self):
        for rel in self.sample_pages():
            with self.subTest(page=rel):
                self.problems.clear()
                self.page.goto(url(rel))
                self.assertTrue(self.page.title().strip())
                self.assertTrue(self.visible("h1"))
                self.assertEqual(self.problems, [])

    def test_no_horizontal_scroll_on_phone(self):
        self.page.set_viewport_size({"width": 375, "height": 800})
        for rel in ("index.html", "sarga-11/index.html", "sarga-05/verse-3.html"):
            with self.subTest(page=rel):
                self.page.goto(url(rel))
                overflow = self.page.evaluate(
                    "document.documentElement.scrollWidth - document.documentElement.clientWidth")
                self.assertLessEqual(overflow, 1)

    # -- language toggle -------------------------------------------------------
    def test_language_toggle_switches_and_persists(self):
        self.page.goto(url("sarga-05/verse-3.html"))
        self.assertTrue(self.visible(".lang-en"))
        self.assertTrue(self.visible(".lang-mr"))
        self.page.click('[data-setlang="en"]')
        self.assertTrue(self.visible(".lang-en"))
        self.assertFalse(self.visible(".lang-mr"))
        self.page.click('[data-setlang="mr"]')
        self.assertFalse(self.visible(".lang-en"))
        self.assertTrue(self.visible(".lang-mr"))
        # the choice survives navigation to another page
        self.page.goto(url("sarga-05/verse-4.html"))
        self.assertEqual(self.page.get_attribute("body", "data-lang"), "mr")
        self.assertFalse(self.visible(".lang-en"))
        self.assertIn("on", self.page.get_attribute('[data-setlang="mr"]', "class"))

    # -- navigation --------------------------------------------------------------
    def test_home_to_sarga_to_verse_and_back(self):
        self.page.goto(url("index.html"))
        self.page.click('a.ch-card[href="sarga-05/index.html"]')
        self.assertTrue(self.page.url.endswith("sarga-05/index.html"))
        self.page.click('a.verse-link[href="verse-3.html"]')
        self.assertTrue(self.page.url.endswith("sarga-05/verse-3.html"))
        self.page.click("a.crumb[href='index.html']")
        self.assertTrue(self.page.url.endswith("sarga-05/index.html"))
        self.page.click("a.crumb[href='../index.html']")
        self.assertTrue(self.page.url.endswith("/index.html"))
        self.assertNotIn("sarga-", self.page.url)

    def test_next_and_previous_links(self):
        self.page.goto(url("sarga-05/verse-3.html"))
        self.page.click("a.next")
        self.assertTrue(self.page.url.endswith("sarga-05/verse-4.html"))
        self.page.click('.pagenav a:not(.next)')
        self.assertTrue(self.page.url.endswith("sarga-05/verse-3.html"))

    def test_next_crosses_sarga_boundary_and_last_verse_returns_to_index(self):
        last = verses("sarga-05")[-1]
        self.page.goto(url(f"sarga-05/verse-{last}.html"))
        self.page.click("a.next")
        self.assertTrue(self.page.url.endswith("sarga-06/verse-1.html"))
        last14 = verses("sarga-14")[-1]
        self.page.goto(url(f"sarga-14/verse-{last14}.html"))
        self.page.click("a.next")
        self.assertTrue(self.page.url.endswith("sarga-14/index.html"))

    # -- images ------------------------------------------------------------------
    def test_embedded_images_render(self):
        for rel in ("index.html", "intro-verses/index.html"):
            with self.subTest(page=rel):
                self.page.goto(url(rel))
                self.page.evaluate("document.querySelectorAll('img').forEach(i => i.loading = 'eager')")
                self.page.wait_for_function(
                    "Array.from(document.images).every(i => i.complete)", timeout=15000)
                broken = self.page.evaluate(
                    "Array.from(document.images).filter(i => i.naturalWidth === 0).length")
                self.assertEqual(broken, 0)
                self.assertGreater(self.page.locator("img").count(), 0)

    def test_external_map_links_open_safely(self):
        self.page.goto(url("intro-verses/index.html"))
        links = self.page.locator('a[href^="https://www.google.com/maps"]')
        self.assertGreater(links.count(), 0)
        self.assertEqual(links.first.get_attribute("target"), "_blank")
        self.assertIn("noopener", links.first.get_attribute("rel"))


if __name__ == "__main__":
    unittest.main()
