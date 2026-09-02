# Summary
Build a packager that creates a ZIP file containing JSON files with information about the actas.

# Description
Create a Python script that packages the contents of the `/resources/actas-json/` directory into a ZIP file named `actas-json.zip`. 
The script should be saved in the `/src/packager/` directory with the filename `package_actas.py`.

The package zip file should contain:
- All the JSON files present in the `/resources/actas-json/` directory, preserving the directory structure.
- When `--season` is provided, only JSON files below the selected season directories are included; multiple seasons are supplied as comma-separated `YYYY-YYYY` values (for example, `2023-2024,2024-2025`).
- `model-definition.json` at the input root is always included, regardless of the selected seasons.
- A manifest file named `manifest.json` that lists all the JSON files included in the ZIP by their relative paths.

## Manifest format

`manifest.json` must be a UTF-8 JSON object with this exact structure:

```json
{
  "source": "FCTT",
  "files": [
    "2025/G1/acta.json",
    "model-definition.json"
  ]
}
```

Manifest requirements:
- `source` is the literal string `"FCTT"`.
- `files` is an array containing one string for every JSON file written to the ZIP; it may be empty.
- Each string is the file path relative to `input-dir`, uses `/` as the separator on every operating system, and must match the path stored in the ZIP.
- Include files with the `.json` extension case-insensitively, preserve their relative directory structure, and sort the path strings in `files` alphabetically.

# Usage and input parameters:
The script should accept the following optional parameters:
- `--input-dir`: The input directory containing the JSON files to be packaged. Default is `/resources/actas-json/`.
- `--output-file`: The output ZIP file name.
- `--force`: Optional flag to force re-creation of the ZIP file if it already exists.
- `--season`: Optional comma-separated season filter. Each value must use the `YYYY-YYYY` format; the ZIP may contain any number of selected seasons.

```text
python src/packager/package_actas.py --input-dir <input_dir> --output-file <output_file> --season 2023-2024,2024-2025 --force
```