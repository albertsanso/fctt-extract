---
name: update-downloader-2026-2027
description: Add female teams and restructure resources folder to fit male and female in downloader.
---

# Summary

This command modifies the script `src/actas-html/download_actas.py` in order to update to new 2026-2027 season and add female teams data. 
It also restructures the resources folder to accommodate both male and female teams.

# Description
Modify the script `src/actas-html/download_actas.py` for:

Adds female teams to the existing male teams data and restructures the resources folder to accommodate both male and female teams.
It ensures that the downloaded HTML data is organized in a way that allows for easy access and management of both types of teams.

Currently, the resources folder contains only male teams data. This command will add female teams data and restructure the folder to have separate directories for male and female teams.

The target website for league data starts from `https://fctt.cat/competicions-estatals/`

## Male groups and matchdays HTML files
- Male groups accesses are placed between `TDM` section and `Altres temporades` section before `COPA CATALANA FEMENINA` section. 
- There is 1 URL for each group. Typically the URL is `https://fctt.cat/lligues/grup-1/`, `https://fctt.cat/lligues/grup-2/`, etc.
- Each group has a number of jornadas (matchdays) with their respective HTML files. Typically the URL is `https://fctt.cat/lligues/grup-1/?jornada=1`, `https://fctt.cat/lligues/grup-1/?jornada=2`, etc.

## Female groups and matchdays HTML files
- Female groups accesses are placed after `COPA CATALANA FEMENINA` section.
- There is 1 URL for each group. Typically the URL is `https://fctt.cat/lligues/1a-divisio/`, `https://fctt.cat/lligues/2a-divisio/`, etc.
- Each group has a number of jornadas (matchdays) with their respective HTML files. Typically the URL is `https://fctt.cat/lligues/1a-divisio/?jornada=1`, `https://fctt.cat/lligues/1a-divisio/?jornada=2`, etc.

# Output folder structure

The folder structure will be as follows:

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
│   ├── 2026-2027/
│   │    ├── male/
│   │    │   ├── tercera-nacional
...
│   │    ├── female/
...
```
