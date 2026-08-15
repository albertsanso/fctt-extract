# Summary

Create a Python script that crawls [http://fctt.cat/lligues/](https://fctt.cat/lligues/) and downloads the HTML source of each league match-day page.

# Description

The Python script downloads the HTML source returned by the FCTT league pages.
It must not follow links such as `https://control.fctt.cat/partido/{id}/imprimir/acta`, because those links can return PDF files. The downloaded content must be the HTML behind URLs such as `https://fctt.cat/lligues/grup-1/?jornada=2`.
The script should navigate through the website's structure, identify the available seasons, categories, groups, and phases, and download the corresponding match-day pages in HTML format.

The navigation is based in giving different values to this parameterized URL:
```url
https://fctt.cat/lligues/{group}/?jornada={match day number}
```
where **match day number** is a number from 1 to 22, and **group** is one of the following values: "G1", "G2", "G3". If the documented `/lligues/G1/` route is unavailable, the script should support the current `/lligues/grup-1/` route and equivalent routes for the other groups.

The script must download the HTML files and save them in a structured directory format based on season, category, and group.
For this project, the season is always `2025-2026`. If the season cannot be extracted from the page HTML, the script must still use `2025-2026`; it must never create a `desconeguda` season directory.

## Reliable and respectful downloading

The downloader must be resilient to temporary network failures while respecting the FCTT website's access controls. It must **not** attempt to bypass firewall, bot-protection, authentication, or rate-limit rules.

- Reuse a normal HTTP session with cookies and use one transparent, descriptive User-Agent. Do not rotate User-Agents or use proxies to evade controls.
- Apply a configurable minimum delay between requests; the default should be conservative (at least five seconds).
- Retry only transient failures (timeouts, `408`, `425`, `429`, and appropriate `5xx` responses) using exponential backoff with jitter.
- Respect the `Retry-After` response header whenever it is present.
- On `403` or an apparent HTML block/access-denied page, stop retrying that request and clearly report the error.
- Validate that each saved response is HTML; do not save empty, PDF, or apparent block/error pages as a jornada HTML file.
- A page containing `No s'han trobat resultats.` is valid HTML and may be saved, but must be logged as a jornada without published results. It may be checked again a small, configurable number of times after a longer delay; it must not be retried aggressively.
- When an existing saved page has `No s'han trobat resultats.` and a later respectful refresh contains results, replace the empty page even without the general overwrite option.
- Continue with other jornadas after an individual failure and append group, jornada, timestamp, and error details to a JSONL failure log so failed jornadas can be retried later.
- Preserve valid existing files by default; use an explicit overwrite option to refresh them.

**Folder structure for downloaded HTML files:**
```text
/resources/{temporada}/{categoria}/{grup}/jornada_{N}.html
```

Where:
- `{temporada}`: always `2025-2026`
- `{categoria}`: always "tercera nacional"
- `{grup}`: just 3 groups only "G1", "G2", "G3"
- `{N}`: match day number from 1 to 22

# Desired Goal

A Python script in `/src/actas-html/` directory with the filename `download_actas.py` that downloads the match-day pages in HTML format from the FCTT website and saves them in the specified folder structure. Each requested jornada must produce a file named `jornada_{N}.html` containing the page HTML, not a PDF downloaded from an acta link.
