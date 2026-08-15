import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("parse_actas.py")
SPEC = importlib.util.spec_from_file_location("parse_actas", MODULE_PATH)
assert SPEC and SPEC.loader
parse_actas = importlib.util.module_from_spec(SPEC)
sys.modules["parse_actas"] = parse_actas
SPEC.loader.exec_module(parse_actas)


ROOT = Path(__file__).parent / "resources" / "2025-2026" / "tercera nacional" / "G1"


class ParseActasTests(unittest.TestCase):
    def test_parse_real_jornada_extracts_matches_and_fields(self):
        records = parse_actas.parse_file(ROOT / "jornada_1.html")
        self.assertEqual(len(records), 6)
        first = records[0]
        self.assertEqual(first["temporada"], "2025/2026")
        self.assertEqual(first["competicion"], "TERCERA DIVISIÓ MASCULINA GRUP 1")
        self.assertEqual(first["grupo"], 1)
        self.assertEqual(first["jornada"], 1)
        self.assertEqual(first["fecha"], "2025-09-27")
        self.assertEqual(first["hora"], "17:00")
        self.assertEqual(first["equipos"]["local"]["nombre"], "MIRÓ GANXETS REUS")
        self.assertEqual(first["equipos"]["local"]["id"], "98")
        self.assertEqual(first["resultado_final"]["marcador_partidos"], {"local": 3, "visitante": 4})
        self.assertEqual(first["partidos"][0]["tipo"], "individual")
        self.assertEqual(first["partidos"][0]["sets"][0], {"set": 1, "local": 11, "visitante": 2})
        self.assertEqual(first["partidos"][6]["tipo"], "dobles")
        self.assertIsNotNone(first["dobles"])

    def test_empty_jornada_produces_no_records(self):
        empty = ROOT / ".." / "G2" / "jornada_14.html"
        self.assertEqual(parse_actas.parse_file(empty), [])

    def test_parse_all_writes_one_json_per_match_and_same_hierarchy(self):
        with tempfile.TemporaryDirectory() as directory:
            input_root = Path(directory) / "html"
            input_root.mkdir()
            shutil.copy2(ROOT / "jornada_1.html", input_root / "jornada_1.html")
            output = Path(directory) / "json"
            count = parse_actas.parse_all(input_root, output)
            files = sorted(output.rglob("*.json"))
            self.assertEqual(count, 6)
            self.assertEqual(len(files), 6)
            self.assertEqual(files[0].parent.relative_to(output).parts[:3], ("2025-2026", "tercera nacional", "G1"))
            saved = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertNotIn("_id", saved)
            self.assertEqual(set(saved), {
                "federacion", "temporada", "competicion", "grupo", "jornada", "fecha", "hora",
                "lugar", "equipos", "abc_es_local", "arbitros", "alineaciones", "dobles", "partidos",
                "resultado_final", "acta_protestada",
            })


if __name__ == "__main__":
    unittest.main()


