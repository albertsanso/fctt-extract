import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("download_actas.py")
SPEC = importlib.util.spec_from_file_location("download_actas", MODULE_PATH)
assert SPEC and SPEC.loader
download_actas = importlib.util.module_from_spec(SPEC)
sys.modules["download_actas"] = download_actas
SPEC.loader.exec_module(download_actas)
League = download_actas.League

INDEX_HTML = """<html><body>
<nav><a href="https://fctt.cat/lligues/altres/">Menú</a></nav>
<h2>TDM</h2>
<h3>TDM G1</h3><a class="btn" href="https://fctt.cat/lligues/grup-1/"><span>Veure</span></a>
<h3>TDM G2</h3><a class="btn" href="https://fctt.cat/lligues/grup-2-2/"></a>
<h4>Altres temporades</h4><p>Temporada 2025/2026</p>
<h3>TDM G1</h3><a href="https://fctt.cat/lligues/grup-1-2/"></a>
<h3>TDM G2</h3><a href="https://fctt.cat/lligues/grup-2/"></a>
<h2>Copa catalana femenina</h2>
<h3>1a Divisi&oacute;</h3><a href="https://fctt.cat/lligues/1a-divisio-2/"></a>
<h3>2a Divisió</h3><a href="https://fctt.cat/lligues/2a-divisio-2/"></a>
<h4>Altres temporades</h4><p>Temporada 2025/2026</p>
<h3>1a Divisió</h3><a href="https://fctt.cat/lligues/1a-divisio/"></a>
<h2>Lligues estatals (grups catalans)</h2>
<h3>1a Divisió</h3><a href="https://fctt.cat/lligues/altra-1a/"></a>
</body></html>"""

MALE = League("2026-2027", "male", "tercera-nacional", "G1", "https://fctt.cat/lligues/grup-1/")
FEMALE = League("2025-2026", "female", "copa-catalana-femenina-1a", None, "https://fctt.cat/lligues/1a-divisio/")


def page(*jornadas, body="<div class='match-container'></div>"):
    buttons = "".join(f'<button class="jornada-btn" data-jornada="{n}">{n}</button>' for n in jornadas)
    return f"<html><body>Temporada 2026/2027{buttons}{body}</body></html>".encode("utf-8")


class DiscoverLeaguesTests(unittest.TestCase):
    def test_discovers_current_and_previous_seasons_for_both_genders(self):
        leagues = download_actas.discover_leagues(INDEX_HTML)
        self.assertEqual([(l.season, l.gender, l.category, l.group, l.url) for l in leagues], [
            ("2026-2027", "male", "tercera-nacional", "G1", "https://fctt.cat/lligues/grup-1/"),
            ("2026-2027", "male", "tercera-nacional", "G2", "https://fctt.cat/lligues/grup-2-2/"),
            ("2025-2026", "male", "tercera-nacional", "G1", "https://fctt.cat/lligues/grup-1-2/"),
            ("2025-2026", "male", "tercera-nacional", "G2", "https://fctt.cat/lligues/grup-2/"),
            ("2026-2027", "female", "copa-catalana-femenina-1a", None, "https://fctt.cat/lligues/1a-divisio-2/"),
            ("2026-2027", "female", "copa-catalana-femenina-2a", None, "https://fctt.cat/lligues/2a-divisio-2/"),
            ("2025-2026", "female", "copa-catalana-femenina-1a", None, "https://fctt.cat/lligues/1a-divisio/"),
        ])

    def test_missing_sections_raise(self):
        with self.assertRaisesRegex(RuntimeError, "No s'han trobat"):
            download_actas.discover_leagues("<html><body>Res</body></html>")

    def test_destination_layout(self):
        root = Path("out")
        self.assertEqual(MALE.destination(root, 3), root / "2026-2027" / "male" / "tercera-nacional" / "G1" / "jornada-3.html")
        self.assertEqual(FEMALE.destination(root, 2), root / "2025-2026" / "female" / "copa-catalana-femenina-1a" / "jornada-2.html")

    def test_jornada_numbers_come_from_selector(self):
        self.assertEqual(download_actas.jornada_numbers(page(3, 1, 2).decode()), (1, 2, 3))


class DownloadActasTests(unittest.TestCase):
    def run_download(self, directory, fetched, **options):
        with patch(f"{MODULE_PATH.stem}.fetch", side_effect=fetched) as mocked, patch(f"{MODULE_PATH.stem}.time.sleep"):
            count = download_actas.download_actas(output_root=Path(directory), retries=1, request_delay=0,
                                                  empty_retry_delay=0, **options)
        return count, mocked

    def test_downloads_every_jornada_listed_by_the_first_page(self):
        with tempfile.TemporaryDirectory() as directory:
            pages = [page(1, 2, 3), page(1, 2, 3), page(1, 2, 3)]
            count, mocked = self.run_download(directory, pages, leagues=[FEMALE])
            self.assertEqual(count, 3)
            self.assertEqual([call.args[0] for call in mocked.call_args_list], [
                "https://fctt.cat/lligues/1a-divisio/?jornada=1",
                "https://fctt.cat/lligues/1a-divisio/?jornada=2",
                "https://fctt.cat/lligues/1a-divisio/?jornada=3",
            ])
            self.assertEqual(FEMALE.destination(Path(directory), 3).read_bytes(), pages[2])

    def test_discovers_leagues_from_index_and_applies_filters(self):
        with tempfile.TemporaryDirectory() as directory:
            count, mocked = self.run_download(directory, [INDEX_HTML.encode(), page(1)],
                                              seasons=["2025-2026"], genders=["male"], groups=["G2"])
            self.assertEqual(count, 1)
            self.assertEqual(mocked.call_args_list[1].args[0], "https://fctt.cat/lligues/grup-2/?jornada=1")
            self.assertTrue((Path(directory) / "2025-2026" / "male" / "tercera-nacional" / "G2" / "jornada-1.html").exists())

    def test_existing_complete_pages_are_skipped_without_fetching(self):
        with tempfile.TemporaryDirectory() as directory:
            for jornada in (1, 2):
                path = MALE.destination(Path(directory), jornada)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(page(1, 2))
            count, mocked = self.run_download(directory, [], leagues=[MALE])
            self.assertEqual(count, 0)
            mocked.assert_not_called()

    def test_empty_page_is_retried_and_replaces_previous_empty_file(self):
        empty = page(1, 2, body="No s'han trobat resultats")
        with tempfile.TemporaryDirectory() as directory:
            for jornada in (1, 2):
                path = MALE.destination(Path(directory), jornada)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(page(1, 2) if jornada == 1 else empty)
            complete = page(1, 2)
            count, mocked = self.run_download(directory, [empty, complete], leagues=[MALE], empty_retries=1)
            self.assertEqual(count, 1)
            self.assertEqual(mocked.call_count, 2)
            self.assertEqual(MALE.destination(Path(directory), 2).read_bytes(), complete)

    def test_failed_jornada_is_logged_and_does_not_abort_remaining_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "failures.jsonl"
            count, _ = self.run_download(directory, [page(1, 2, 3), RuntimeError("timeout"), page(1, 2, 3)],
                                         leagues=[MALE], failure_log=log)
            self.assertEqual(count, 2)
            entry = log.read_text(encoding="utf-8")
            self.assertIn('"jornada": 2', entry)
            self.assertIn('"gender": "male"', entry)
            self.assertTrue(MALE.destination(Path(directory), 3).exists())

    def test_jornadas_option_limits_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            count, mocked = self.run_download(directory, [page(1, 2, 3), page(1, 2, 3)], leagues=[MALE], jornadas=[3])
            self.assertEqual(count, 1)
            self.assertFalse(MALE.destination(Path(directory), 1).exists())
            self.assertTrue(MALE.destination(Path(directory), 3).exists())

    def test_validate_page_rejects_empty_and_access_denied_responses(self):
        with self.assertRaisesRegex(RuntimeError, "no és HTML"):
            download_actas.validate_page(b"", "https://fctt.cat/test")
        with self.assertRaisesRegex(RuntimeError, "bloqueig"):
            download_actas.validate_page(b"<html><body>Access denied</body></html>", "https://fctt.cat/test")


if __name__ == "__main__":
    unittest.main()
