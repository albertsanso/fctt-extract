"""Package acta JSON files and a manifest into a ZIP archive."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPOSITORY_ROOT / "resources" / "actas-json"
DEFAULT_OUTPUT_FILE = REPOSITORY_ROOT / "resources" / "actas-json.zip"
MANIFEST_NAME = "manifest.json"
ARCHIVE_PREFIX = "actas-json"
SEASON_PATTERN = re.compile(r"\d{4}-\d{4}\Z")


def parse_seasons(value: str | None) -> tuple[str, ...] | None:
    """Parse and validate a comma-separated season selection."""
    if value is None:
        return None

    seasons = tuple(dict.fromkeys(item.strip() for item in value.split(",")))
    if not seasons or "" in seasons:
        raise argparse.ArgumentTypeError("--season debe contener temporadas con formato YYYY-YYYY")
    invalid = [season for season in seasons if not SEASON_PATTERN.fullmatch(season)]
    if invalid:
        raise argparse.ArgumentTypeError(
            "Temporadas no válidas: " + ", ".join(invalid) + " (formato esperado: YYYY-YYYY)"
        )
    return seasons


def collect_json_files(input_dir: Path, seasons: tuple[str, ...] | None) -> list[tuple[Path, str]]:
    """Return selected JSON files and their POSIX archive names."""
    files: list[tuple[Path, str]] = []
    selected = set(seasons) if seasons is not None else None
    for path in input_dir.rglob("*.json"):
        if not path.is_file():
            continue
        relative = path.relative_to(input_dir)
        if relative.as_posix() == MANIFEST_NAME:
            continue
        if selected is not None and (not relative.parts or relative.parts[0] not in selected):
            continue
        files.append((path, f"{ARCHIVE_PREFIX}/{relative.as_posix()}"))
    return sorted(files, key=lambda item: item[1])


def build_manifest(archive_names: list[str]) -> dict[str, object]:
    """Build the manifest for the supplied archive paths."""
    seasons = sorted(
        {
            parts[1]
            for name in archive_names
            if (parts := name.split("/"))
            and len(parts) > 1
            and parts[0] == ARCHIVE_PREFIX
            and SEASON_PATTERN.fullmatch(parts[1])
        }
    )
    return {
        "source": "FCTT",
        "seasons": seasons,
        "assets": {"ACTAS": {"files": archive_names}},
    }


def package_actas(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_file: Path | None = None,
    force: bool = False,
    seasons: tuple[str, ...] | None = None,
) -> int:
    """Create an actas ZIP and return the number of JSON files included."""
    if not input_dir.is_dir():
        raise FileNotFoundError(f"El directorio de entrada no existe: {input_dir}")
    if output_file is None:
        if seasons:
            season_suffix = ",".join(seasons)
            output_file = output_file_for_seasons(season_suffix)
        else:
            output_file = DEFAULT_OUTPUT_FILE
    if output_file.exists() and not force:
        raise FileExistsError(f"El fichero de salida ya existe: {output_file} (usa --force)")

    selected_files = collect_json_files(input_dir, seasons)
    archive_names = [archive_name for _, archive_name in selected_files]
    manifest = json.dumps(
        build_manifest(archive_names), ensure_ascii=False, indent=2, sort_keys=False
    ) + "\n"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, archive_name in selected_files:
            archive.write(path, archive_name)
        archive.writestr(MANIFEST_NAME, manifest.encode("utf-8"))
    return len(selected_files)


def output_file_for_seasons(season_suffix: str) -> Path:
    """Return the default output path for a normalized season suffix."""
    return REPOSITORY_ROOT / "resources" / f"actas-json-{season_suffix}.zip"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--season", help="Una o varias temporadas separadas por comas")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        seasons = parse_seasons(args.season)
        package_actas(
            input_dir=args.input_dir,
            output_file=args.output_file,
            force=args.force,
            seasons=seasons,
        )
    except (FileExistsError, FileNotFoundError, ValueError, OSError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())



