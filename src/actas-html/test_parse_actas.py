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
UPCOMING = REAL_INPUT.parents[2] / "2026-2027" / "male" / "tercera-nacional"


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

    def test_published_acta_has_identifier_and_phase(self):
        first = parse_actas.parse_file(ROOT / "jornada-1.html")[0]
        self.assertTrue(first["acta_publicada"])
        self.assertEqual(first["fase"], "1a Fase")
        self.assertEqual(first["id_partido"], "2025-2026_tercera-nacional_G1_1aFase_98-{}_1".format(first["equipos"]["visitante"]["id"]))

    def test_unplayed_match_is_emitted_as_unpublished_acta(self):
        records = parse_actas.parse_file(UPCOMING / "G1" / "jornada-5.html")
        first = records[0]
        self.assertFalse(first["acta_publicada"])
        self.assertIsNone(first["abc_es_local"])
        self.assertEqual(first["partidos"], [])
        self.assertEqual(first["alineaciones"], {"local": {}, "visitante": {}})
        self.assertIsNone(first["dobles"])
        self.assertIsNone(first["resultado_final"]["marcador_partidos"])
        self.assertEqual((first["fecha"], first["hora"]), ("2026-10-31", "17:30"))
        self.assertEqual(first["id_partido"], "2026-2027_tercera-nacional_G1_1aFase_123-149_5")
        self.assertEqual(first["_id"], "123-149")

    def test_played_match_without_published_acta_keeps_final_score(self):
        records = parse_actas.parse_file(REAL_INPUT / "G3" / "jornada-10.html")
        record = next(r for r in records if r["equipos"]["local"]["nombre"] == "CTT BARCELONA")
        self.assertFalse(record["acta_publicada"])
        self.assertEqual(record["partidos"], [])
        self.assertEqual(record["resultado_final"]["marcador_partidos"], {"local": 6, "visitante": 0})
        self.assertEqual(record["resultado_final"]["ganador"], "CTT BARCELONA")

    def test_published_acta_replaces_unpublished_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            input_root = Path(directory) / "html" / "2025-2026" / "male" / "tercera-nacional" / "G1"
            input_root.mkdir(parents=True)
            shutil.copy2(ROOT / "jornada-1.html", input_root / "jornada-1.html")
            output = Path(directory) / "json"
            record = parse_actas.parse_file(input_root / "jornada-1.html")[0]
            folder = output / "2025-2026" / "male" / "tercera-nacional" / "G1"
            folder.mkdir(parents=True)
            placeholder = folder / "jornada-1-partido-{}.json".format(parse_actas.placeholder_id(record["equipos"]))
            placeholder.write_text("{}", encoding="utf-8")
            parse_actas.parse_all(Path(directory) / "html", output)
            self.assertFalse(placeholder.exists())
            self.assertTrue((folder / "jornada-1-partido-{}.json".format(record["_id"])).exists())

    def test_other_group_folder_has_null_group(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "2026-2027" / "male" / "tercera-nacional" / "Other"
            folder.mkdir(parents=True)
            shutil.copy2(UPCOMING / "G1" / "jornada-5.html", folder / "jornada-5.html")
            record = parse_actas.parse_file(folder / "jornada-5.html")[0]
            self.assertIsNone(record["grupo"])
            self.assertIn("_Other_", record["id_partido"])
            self.assertEqual(parse_actas.output_path(Path("out"), folder / "jornada-5.html", record).parent.name, "Other")

    def test_empty_jornada_produces_no_records(self):
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "jornada-14.html"
            empty.write_text("<html><body><h2>Temporada 2025/2026</h2><p>No s'han trobat resultats</p></body></html>", encoding="utf-8")
            self.assertEqual(parse_actas.parse_file(empty), [])

    def test_unlinked_doubles_pair_is_split_into_two_players(self):
        cell = parse_actas.parse_document('<td class="player-info">ROCABERT FONTANET, AINA<br>ROCABERT FONTANET, JUDIT</td>').find_first(tag="td")
        self.assertEqual(parse_actas.participant_from_cell(cell), [
            {"nombre": "ROCABERT FONTANET, AINA", "licencia": "0"},
            {"nombre": "ROCABERT FONTANET, JUDIT", "licencia": "0"},
        ])

    def test_empty_female_jornada_produces_pending_record(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "2026-2027" / "female" / "copa-catalana-femenina-2a"
            folder.mkdir(parents=True)
            (folder / "jornada-3.html").write_text(
                "<html><body><h1 class=\"entry-title\">2a Divisió</h1><p>No s'han trobat resultats.</p>"
                "<p>No s'han trobat partits.</p></body></html>", encoding="utf-8")
            [record] = parse_actas.parse_file(folder / "jornada-3.html")
            self.assertFalse(record["acta_publicada"])
            self.assertEqual(record["id_partido"], "2026-2027_copa-catalana-femenina-2a_1aFase_pendiente_3")
            self.assertEqual((record["temporada"], record["genero"], record["competicion"], record["jornada"]),
                             ("2026/2027", "femenino", "2a Divisió", 3))
            self.assertEqual(record["partidos"], [])
            self.assertEqual(record["alineaciones"], {"local": {}, "visitante": {}})
            self.assertEqual(parse_actas.output_path(Path("out"), folder / "jornada-3.html", record),
                             Path("out") / "2026-2027" / "female" / "copa-catalana-femenina-2a" / "jornada-3-partido-pendiente.json")

    def test_female_jornada_with_matches_replaces_pending_record(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "html" / "2026-2027" / "female" / "copa-catalana-femenina-1a"
            folder.mkdir(parents=True)
            source = folder / "jornada-1.html"
            source.write_text("<html><body><h1 class=\"entry-title\">1a Divisió</h1></body></html>", encoding="utf-8")
            output = Path(directory) / "json"
            self.assertEqual(parse_actas.parse_all(Path(directory) / "html", output), 1)
            pending = output / "2026-2027" / "female" / "copa-catalana-femenina-1a" / "jornada-1-partido-pendiente.json"
            self.assertTrue(pending.exists())
            shutil.copy2(ROOT / "jornada-1.html", source)
            self.assertEqual(parse_actas.parse_all(Path(directory) / "html", output), 6)
            self.assertFalse(pending.exists())

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
                "id_partido", "acta_publicada", "federacion", "temporada", "genero", "competicion", "fase",
                "grupo", "jornada", "fecha", "hora",
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
            female_record = json.loads(female_files[0].read_text(encoding="utf-8"))
            self.assertEqual(female_record["genero"], "femenino")
            self.assertRegex(female_record["id_partido"], r"^2026-2027_copa-catalana-femenina-1a_1aFase_\d+-\d+_1$")
            self.assertRegex(json.loads(male_files[0].read_text(encoding="utf-8"))["id_partido"],
                             r"^2026-2027_tercera-nacional_G1_1aFase_\d+-\d+_1$")

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


