import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("package_actas.py")
SPEC = importlib.util.spec_from_file_location("package_actas", MODULE_PATH)
assert SPEC and SPEC.loader
package_actas = importlib.util.module_from_spec(SPEC)
sys.modules["package_actas"] = package_actas
SPEC.loader.exec_module(package_actas)


class PackageActasTests(unittest.TestCase):
    def test_packages_json_files_and_manifest_with_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "input"
            (root / "2025" / "G1").mkdir(parents=True)
            (root / "2025" / "G1" / "acta.json").write_text('{"id": 1}', encoding="utf-8")
            (root / "model-definition.json").write_text("{}", encoding="utf-8")
            (root / "notes.txt").write_text("not JSON", encoding="utf-8")
            output = Path(directory) / "actas-json.zip"

            count = package_actas.package_actas(root, output)

            self.assertEqual(count, 2)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"2025/G1/acta.json", "model-definition.json", "manifest.json"},
                )
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(
                    manifest["files"],
                    [
                        "2025/G1/acta.json",
                        "model-definition.json",
                    ],
                )

    def test_packages_selected_seasons_and_model_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "input"
            for season in ("2023-2024", "2024-2025", "2025-2026"):
                path = root / season / "tercera nacional" / "G1" / "acta.json"
                path.parent.mkdir(parents=True)
                path.write_text(season, encoding="utf-8")
            (root / "model-definition.json").write_text("{}", encoding="utf-8")
            output = Path(directory) / "selected.zip"

            count = package_actas.package_actas(
                root,
                output,
                seasons=package_actas.parse_seasons("2023-2024, 2024-2025"),
            )

            self.assertEqual(count, 3)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "2023-2024/tercera nacional/G1/acta.json",
                        "2024-2025/tercera nacional/G1/acta.json",
                        "model-definition.json",
                        "manifest.json",
                    },
                )

    def test_parse_seasons_rejects_invalid_values_and_removes_duplicates(self):
        self.assertEqual(
            package_actas.parse_seasons("2023-2024, 2023-2024"),
            ("2023-2024",),
        )
        with self.assertRaises(package_actas.argparse.ArgumentTypeError):
            package_actas.parse_seasons("2023/2024")
        with self.assertRaises(package_actas.argparse.ArgumentTypeError):
            package_actas.parse_seasons("2023-2024,")

    def test_existing_output_requires_force(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "input"
            root.mkdir()
            output = Path(directory) / "output.zip"
            output.write_bytes(b"original")

            with self.assertRaises(FileExistsError):
                package_actas.package_actas(root, output)
            self.assertEqual(output.read_bytes(), b"original")
            self.assertEqual(package_actas.package_actas(root, output, force=True), 0)

    def test_missing_input_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                package_actas.package_actas(Path(directory) / "missing", Path(directory) / "out.zip")


if __name__ == "__main__":
    unittest.main()
