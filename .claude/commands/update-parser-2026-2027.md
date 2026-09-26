---
name: update-parser-2026-2027
description: Update parser to handle new 2026-2027 season and female actas data.
---

# Summary

This command modifies the script `src/actas-html/parse_actas.py` to update it for the new 2026-2027 season and to handle female actas data. 
It ensures that the parser can correctly process both male and female actas HTML files and generate the corresponding JSON output.

# Description
Modify the script `src/actas-html/parse_actas.py` for:
- Update to the new 2026-2027 season.
- Add support for parsing female actas data.
- Ensure that the parser can handle the new folder structure for both male and female actas HTML files.
- Update the output JSON structure to include a field indicating whether the acta is male or female.

# Input folder structure
The input folder structure will be as follows:

```
resources/
├── actas-html/
│   ├── 2025-2026/
│   │   ├── male/
│   │   │   ├── tercera-nacional
│   │   │   │   ├── G1
│   │   │   │   │   ├── jornada-1.html
│   │   │   │   │   ├── jornada-2.html
│   │   │   │   │   ├── ...
│   │   │   │   │   ├── jornada-{N}.html
│   │   │   │   ├── G2
│   │   │   │   │   ├── jornada-1.html
│   │   │   │   │   ├── jornada-2.html
│   │   │   │   │   ├── ...
│   │   │   │   │   ├── jornada-{N}.html
│   │   │   │   ├── ...
│   │   │   │   ├── G{N}
│   │   ├── female/
│   │   │   ├── copa-catalana-femenina-1a
│   │   │   │   ├── jornada-1.html  
│   │   │   │   ├── jornada-2.html
│   │   │   │   ├── ...
│   │   │   │   ├── jornada-{N}.html
│   │   │   ├── copa-catalana-femenina-2a
│   │   │   │   ├── jornada-1.html
│   │   │   │   ├── jornada-2.html
│   │   │   │   ├── ...
│   │   │   │   ├── jornada-{N}.html
│   │   │   ├── ...
``` 

# Output folder structure
The output folder structure will be as follows:
```
resources/
├── actas-json/
│   ├── 2025-2026/
│   │   ├── male/
│   │   │   ├── tercera-nacional
│   │   │   │   ├── G1/
│   │   │   │   │   ├── jornada-1-partido-{id_partido-1}.json
│   │   │   │   │   ├── jornada-1-partido-{id_partido-2}.json
│   │   │   │   │   ├── ...
│   │   │   │   │   ├── jornada-1-partido-{id_partido-N}.json
│   │   │   │   ├── G2/
│   │   │   │   │   ├── jornada-1-partido-{id_partido-1}.json
│   │   │   │   │   ├── jornada-1-partido-{id_partido-2}.json
│   │   │   │   │   ├── ...
│   │   │   │   │   ├── jornada-1-partido-{id_partido-N}.json
│   │   │   │   ├── ...
│   │   │   │   ├── G{N}/
│   │   ├── female/
│   │   │   ├── copa-catalana-femenina-1a/
│   │   │   │   ├── jornada-1-partido-{id_partido-1}.json
│   │   │   │   ├── jornada-1-partido-{id_partido-2}.json
│   │   │   │   ├── ...
│   │   │   │   ├── jornada-1-partido-{id_partido-N}.json
│   │   │   ├── copa-catalana-femenina-2a/
│   │   │   │   ├── jornada-1-partido-{id_partido-1}.json
│   │   │   │   ├── jornada-1-partido-{id_partido-2}.json
│   │   │   │   ├── ...
│   │   │   │   ├── jornada-1-partido-{id_partido-N}.json
│   │   │   ├── ...
```
