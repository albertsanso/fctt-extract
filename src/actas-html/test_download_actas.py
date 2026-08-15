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


class DownloadActasTests(unittest.TestCase):
    def test_download_saves_jornada_html_not_acta_pdf(self):
        html = """<!doctype html><html><body>
        <h2>TERCERA DIVISIÓ MASCULINA - Temporada 2024/2025</h2>
        <a href="https://control.fctt.cat/partido/123/imprimir/acta">PDF acta</a>
        </body></html>"""
        with tempfile.TemporaryDirectory() as directory, patch(
            f"{MODULE_PATH.stem}.fetch", return_value=html.encode("utf-8")
        ) as mocked_fetch:
            count = download_actas.download_actas(
                output_root=Path(directory), groups=("G1",), jornadas=(2,), retries=1
            )
            output = Path(directory) / "2024-2025" / "tercera nacional" / "G1" / "jornada_2.html"
            self.assertEqual(count, 1)
            self.assertEqual(output.read_text(encoding="utf-8"), html)
            mocked_fetch.assert_called_once()
            self.assertNotIn("control.fctt.cat", mocked_fetch.call_args.args[0])

    def test_validate_page_rejects_empty_and_access_denied_responses(self):
        with self.assertRaisesRegex(RuntimeError, "no és HTML"):
            download_actas.validate_page(b"", "https://fctt.cat/test")
        with self.assertRaisesRegex(RuntimeError, "bloqueig"):
            download_actas.validate_page(b"<html><body>Access denied</body></html>", "https://fctt.cat/test")

    def test_failed_jornada_is_logged_and_does_not_abort_remaining_downloads(self):
        html = b"<html><body>Temporada 2025/2026</body></html>"
        with tempfile.TemporaryDirectory() as directory, patch(
            f"{MODULE_PATH.stem}.fetch", side_effect=[RuntimeError("timeout"), html]
        ):
            log = Path(directory) / "failures.jsonl"
            count = download_actas.download_actas(
                output_root=Path(directory), groups=("G1",), jornadas=(1, 2), retries=1, failure_log=log
            )
            self.assertEqual(count, 1)
            self.assertIn('"jornada": 1', log.read_text(encoding="utf-8"))
            self.assertTrue((Path(directory) / "2025-2026" / "tercera nacional" / "G1" / "jornada_2.html").exists())

    def test_empty_page_is_retried_and_replaced_when_results_arrive(self):
        empty = b"<html><body>No s'han trobat resultats. Temporada 2025/2026</body></html>"
        complete = b"<html><body>Temporada 2025/2026<div class='match-container'></div></body></html>"
        with tempfile.TemporaryDirectory() as directory, patch(
            f"{MODULE_PATH.stem}.fetch", side_effect=[empty, complete]
        ) as mocked_fetch, patch(f"{MODULE_PATH.stem}.time.sleep"):
            output = Path(directory)
            count = download_actas.download_actas(
                output_root=output, groups=("G1",), jornadas=(2,), retries=1,
                request_delay=0, empty_retries=1, empty_retry_delay=0,
            )
            page = output / "2025-2026" / "tercera nacional" / "G1" / "jornada_2.html"
            self.assertEqual(count, 1)
            self.assertEqual(mocked_fetch.call_count, 2)
            self.assertEqual(page.read_bytes(), complete)

    def test_metadata_normalizes_season_without_sex(self):
        self.assertEqual(
            download_actas.extract_metadata("<h1>FEMENÍ - Temporada 2024/2025</h1>", "G1"),
            ("2024-2025", "tercera nacional"),
        )
        self.assertEqual(
            download_actas.extract_metadata("<h1>Temporada 2025-2026</h1>", "G2"),
            ("2025-2026", "tercera nacional"),
        )
        self.assertEqual(
            download_actas.extract_metadata("<html><body>Resultats</body></html>", "G1"),
            ("2025-2026", "tercera nacional"),
        )

    def test_group_urls_support_documented_and_current_routes(self):
        self.assertEqual(
            download_actas.group_urls("G3", 22),
            (
                "https://fctt.cat/lligues/G3/?jornada=22",
                "https://fctt.cat/lligues/grup-3/?jornada=22",
            ),
        )


if __name__ == "__main__":
    unittest.main()

