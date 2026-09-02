"""Package acta JSON files and a manifest into a ZIP archive."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import re
import sys
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = REPOSITORY_ROOT / "resources" / "actas-json"
DEFAULT_OUTPUT_FILE = REPOSITORY_ROOT / "resources" / "actas-json.zip"
MANIFEST_NAME = "manifest.json"
SEASON_PATTERN = re.compile(r"^\d{4}-\d{4}$")


def parse_seasons(value: str) -> tuple[str, ...]:
    """Parse and validate comma-separated season values from the CLI."""
    seasons = tuple(dict.fromkeys(season.strip() for season in value.split(",")))
    if not seasons or any(not season or not SEASON_PATTERN.fullmatch(season) for season in seasons):
        raise argparse.ArgumentTypeError(
            "season must contain comma-separated values in YYYY-YYYY format"
        )
    return seasons


def _json_files(input_dir: Path, seasons: Sequence[str] | None = None) -> list[Path]:
    """Return selected JSON files below *input_dir* in stable relative-path order."""
    selected_seasons = set(seasons) if seasons else None

    def is_selected(path: Path) -> bool:
        if selected_seasons is None:
            return True
        relative_path = path.relative_to(input_dir)
        if relative_path == Path("model-definition.json"):
            return True
        return len(relative_path.parts) > 0 and relative_path.parts[0] in selected_seasons

    return sorted(
        (
            path
            for path in input_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".json" and is_selected(path)
        ),
        key=lambda path: path.relative_to(input_dir).as_posix(),
    )


def build_manifest(input_dir: Path, files: list[Path]) -> list[str]:
    """Build relative POSIX paths for the files written to the archive."""
    return [path.relative_to(input_dir).as_posix() for path in files]


def package_actas(
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_file: Path = DEFAULT_OUTPUT_FILE,
    *,
    force: bool = False,
    seasons: Sequence[str] | None = None,
) -> int:
    """Create *output_file* and return the number of packaged JSON files."""
    input_dir = Path(input_dir).resolve()
    output_file = Path(output_file).resolve()

    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if output_file.exists() and not force:
        raise FileExistsError(
            f"Output file already exists: {output_file} (use --force to replace it)"
        )

    files = _json_files(input_dir, seasons)
    manifest = build_manifest(input_dir, files)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(input_dir).as_posix())
        archive.writestr(
            MANIFEST_NAME,
            json.dumps({"source": "FCTT", "files": manifest}, ensure_ascii=False, indent=2) + "\n",
        )

    return len(files)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package actas JSON files and a manifest into a ZIP archive."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Input directory (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Output ZIP file (default: {DEFAULT_OUTPUT_FILE})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the output file if it already exists.",
    )
    parser.add_argument(
        "--season",
        dest="season",
        type=parse_seasons,
        help="Only package these comma-separated seasons (format: YYYY-YYYY).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        count = package_actas(
            args.input_dir,
            args.output_file,
            force=args.force,
            seasons=args.season,
        )
    except (FileExistsError, FileNotFoundError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Packaged {count} JSON file(s) into {Path(args.output_file).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

