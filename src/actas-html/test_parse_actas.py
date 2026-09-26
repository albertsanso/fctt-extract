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


REAL_INPUT = Path(__file__).resolve().parents[2] / "resources" / "actas-html" / "2025-2026" / "male" / "tercera-nacional"
ROOT = REAL_INPUT / "G1"


class OrientationTests(unittest.TestCase):
    def test_orients_lineups_and_games_by_real_side_when_abc_column_is_the_away_team(self):
        records = parse_actas.parse_file(REAL_INPUT / "G2" / "jornada-22.html")
        record = next(r for r in records if r["equipos"]["local"]["nombre"] == "CTT ELS AMICS TERRASSA")
        self.assertFalse(record["abc_es_local"])
        self.assertEqual(sorted(record["alineaciones"]["local"]), ["X", "Y", "Z"])
        self.assertEqual(record["alineaciones"]["visitante"]["A"]["nombre"], "LUCO PEREZ, BERNAT")
        self.assertEqual(record["dobles"]["visitante"][0]["nombre"], "LUCO PEREZ, BERNAT")
        first = record["partidos"][0]
        self.assertEqual(first["cruce"], "A vs Y")
        self.assertEqual(first["local"]["letra"], "Y")
        self.assertEqual(first["sets"][0], {"set": 1, "local": 11, "visitante": 13})
        self.assertEqual(first["resultado_juegos"], {"local": 1, "visitante": 3})
        self.assertEqual(first["ganador"], "visitante")
        self.assertEqual(record["partidos"][-1]["marcador_acumulado"], record["resultado_final"]["marcador_partidos"])

    def test_keeps_orientation_when_abc_column_is_the_home_team(self):
        records = parse_actas.parse_file(REAL_INPUT / "G2" / "jornada-22.html")
        consistent = [r for r in records if r["partidos"] and r["abc_es_local"]]
        self.assertTrue(consistent)
        for record in consistent:
            self.assertTrue(set(record["alineaciones"]["local"]) <= {"A", "B", "C"})
            self.assertEqual(record["partidos"][-1]["marcador_acumulado"], record["resultado_final"]["marcador_partidos"])


class ParseActasTests(unittest.TestCase):
    def test_parse_real_jornada_extracts_matches_and_fields(self):
        records = parse_actas.parse_file(ROOT / "jornada-1.html")
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
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "jornada-14.html"
            empty.write_text("<html><body><h2>Temporada 2025/2026</h2><p>No s'han trobat resultats</p></body></html>", encoding="utf-8")
            self.assertEqual(parse_actas.parse_file(empty), [])

    def test_parse_all_writes_one_json_per_match_and_same_hierarchy(self):
        with tempfile.TemporaryDirectory() as directory:
            input_root = Path(directory) / "html"
            input_root.mkdir()
            shutil.copy2(ROOT / "jornada-1.html", input_root / "jornada-1.html")
            output = Path(directory) / "json"
            count = parse_actas.parse_all(input_root, output)
            files = sorted(output.rglob("*.json"))
            self.assertEqual(count, 6)
            self.assertEqual(len(files), 6)
            self.assertEqual(files[0].parent.relative_to(output).parts, ("2025-2026", "male", "tercera-nacional", "G1"))
            self.assertRegex(files[0].name, r"^jornada-1-partido-\d+\.json$")
            saved = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertNotIn("_id", saved)
            self.assertEqual(saved["genero"], "masculino")
            self.assertEqual(set(saved), {
                "federacion", "temporada", "genero", "competicion", "grupo", "jornada", "fecha", "hora",
                "lugar", "equipos", "abc_es_local", "arbitros", "alineaciones", "dobles", "partidos",
                "resultado_final", "acta_protestada",
            })


    def test_parse_all_mirrors_season_gender_category_and_group_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            input_root = Path(directory) / "html"
            male = input_root / "2026-2027" / "male" / "tercera-nacional" / "G1"
            female = input_root / "2026-2027" / "female" / "copa-catalana-femenina-1a"
            male.mkdir(parents=True)
            female.mkdir(parents=True)
            shutil.copy2(ROOT / "jornada-1.html", male / "jornada-1.html")
            shutil.copy2(ROOT / "jornada-1.html", female / "jornada-1.html")
            output = Path(directory) / "json"
            self.assertEqual(parse_actas.parse_all(input_root, output), 12)
            male_files = sorted((output / "2026-2027" / "male" / "tercera-nacional" / "G1").glob("jornada-1-partido-*.json"))
            female_files = sorted((output / "2026-2027" / "female" / "copa-catalana-femenina-1a").glob("jornada-1-partido-*.json"))
            self.assertEqual((len(male_files), len(female_files)), (6, 6))
            self.assertEqual(json.loads(male_files[0].read_text(encoding="utf-8"))["genero"], "masculino")
            self.assertEqual(json.loads(female_files[0].read_text(encoding="utf-8"))["genero"], "femenino")

    def test_parse_all_filters_by_season_and_gender(self):
        with tempfile.TemporaryDirectory() as directory:
            input_root = Path(directory) / "html"
            for season in ("2025-2026", "2026-2027"):
                for gender, category in (("male", "tercera-nacional/G1"), ("female", "copa-catalana-femenina-2a")):
                    folder = input_root / season / gender / category
                    folder.mkdir(parents=True)
                    shutil.copy2(ROOT / "jornada-1.html", folder / "jornada-1.html")
            output = Path(directory) / "json"
            count = parse_actas.parse_all(input_root, output, seasons=["2026-2027"], genders=["female"])
            self.assertEqual(count, 6)
            self.assertEqual({path.parent.relative_to(output).parts for path in output.rglob("*.json")},
                             {("2026-2027", "female", "copa-catalana-femenina-2a")})


class LocationTests(unittest.TestCase):
    def test_source_location_reads_male_and_female_hierarchies(self):
        male = parse_actas.source_location(Path("x") / "2026-2027" / "male" / "tercera-nacional" / "G3" / "jornada-2.html")
        female = parse_actas.source_location(Path("x") / "2026-2027" / "female" / "copa-catalana-femenina-2a" / "jornada-2.html")
        self.assertEqual(male, parse_actas.Location("2026-2027", "male", "tercera-nacional", "G3"))
        self.assertEqual(female, parse_actas.Location("2026-2027", "female", "copa-catalana-femenina-2a", None))

    def test_gender_and_category_fall_back_to_competition_title(self):
        self.assertEqual(parse_actas.gender_from_competition("COPA CATALANA FEMENINA 2a DIVISIÓ"), "female")
        self.assertEqual(parse_actas.gender_from_competition("TERCERA DIVISIÓ MASCULINA GRUP 1"), "male")
        self.assertEqual(parse_actas.default_category("female", "COPA CATALANA FEMENINA 2a DIVISIÓ"), "copa-catalana-femenina-2a")
        self.assertEqual(parse_actas.default_category("male", "TERCERA DIVISIÓ MASCULINA GRUP 1"), "tercera-nacional")


if __name__ == "__main__":
    unittest.main()


