"""Download FCTT match reports (actas) as HTML files.

The FCTT site has used both ``/lligues/G1/`` and ``/lligues/grup-1/``
routes.  The downloader tries the documented route first and falls back to
the current route when necessary.
"""

from __future__ import annotations

import argparse
import email.utils
import json
import logging
import random
import re
import sys
import time
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = "https://fctt.cat"
GROUPS = ("G1", "G2", "G3")
MATCH_DAYS = tuple(range(1, 23))
DEFAULT_SEASON = "2025-2026"
DEFAULT_CATEGORY = "tercera nacional"
USER_AGENT = "fctt-actas-downloader/1.0 (+https://fctt.cat/lligues/)"
LOGGER = logging.getLogger("fctt-actas")
TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
BLOCK_PAGE_MARKERS = ("access denied", "forbidden", "captcha", "cloudflare", "request blocked")

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "resources" / "actas-html"

class RequestPacer:
    """Enforce a minimum interval between requests to the remote site."""

    def __init__(self, delay: float) -> None:
        self.delay = max(0.0, delay)
        self.next_request_at = 0.0

    def wait(self) -> None:
        remaining = self.next_request_at - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self.next_request_at = time.monotonic() + self.delay


def create_opener():
    """Create a cookie-preserving opener for a normal browsing session."""
    return build_opener(HTTPCookieProcessor(CookieJar()))


def retry_after_seconds(value: str | None) -> float | None:
    """Parse a Retry-After value expressed as seconds or an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, email.utils.parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def retry_delay(attempt: int, retry_after: str | None = None) -> float:
    """Use server guidance first, otherwise an exponential backoff with jitter."""
    return retry_after_seconds(retry_after) or min(60.0, 2 ** (attempt - 1) + random.uniform(0, 1))


def fetch(url: str, *, timeout: float = 30, retries: int = 4, opener=None, pacer: RequestPacer | None = None) -> bytes:
    """Fetch a URL with polite retries for transient failures and rate limits."""
    last_error: Exception | None = None
    opener = opener or create_opener()
    for attempt in range(1, retries + 1):
        try:
            if pacer:
                pacer.wait()
            request = Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ca,es;q=0.9,en;q=0.8",
            })
            with opener.open(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as error:
            last_error = error
            if error.code not in TRANSIENT_STATUS_CODES:
                raise
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
        if attempt < retries:
            header = last_error.headers.get("Retry-After") if isinstance(last_error, HTTPError) else None
            delay = retry_delay(attempt, header)
            LOGGER.warning("Intent %s/%s falló para %s (%s); esperando %.1f s", attempt, retries, url, last_error, delay)
            time.sleep(delay)
    raise RuntimeError(f"No s'ha pogut descarregar {url}: {last_error}") from last_error


def group_urls(group: str, jornada: int) -> tuple[str, ...]:
    """Return documented and current FCTT URL forms for a group/jornada."""
    number = group[1:]
    query = f"?jornada={jornada}"
    return (
        f"{BASE_URL}/lligues/{group}/{query}",
        f"{BASE_URL}/lligues/grup-{number}/{query}",
    )


def extract_metadata(html: str, group: str) -> tuple[str, str]:
    """Return season and fixed category from a league page."""
    season_match = re.search(r"Temporada\s+(\d{4})\s*[/\-]\s*(\d{4})", html, re.I)
    season = f"{season_match.group(1)}-{season_match.group(2)}" if season_match else DEFAULT_SEASON
    return season, DEFAULT_CATEGORY


def fetch_group_page(group: str, jornada: int, *, timeout: float, retries: int, opener, pacer: RequestPacer) -> bytes:
    """Fetch the jornada page, supporting both historical FCTT URL forms."""
    documented_url, current_url = group_urls(group, jornada)
    try:
        return fetch(documented_url, timeout=timeout, retries=retries, opener=opener, pacer=pacer)
    except HTTPError as error:
        if error.code != 404:
            raise
        return fetch(current_url, timeout=timeout, retries=retries, opener=opener, pacer=pacer)


def validate_page(page: bytes, url: str) -> str:
    """Reject obvious non-HTML access/error pages but allow valid empty jornadas."""
    text = page.decode("utf-8", "replace")
    normalized = text.casefold()
    if not page or "<html" not in normalized:
        raise RuntimeError(f"La resposta de {url} no és HTML vàlid")
    if any(marker in normalized for marker in BLOCK_PAGE_MARKERS):
        raise RuntimeError(f"La resposta de {url} sembla una pàgina de bloqueig o accés denegat")
    return text


def has_no_results(text: str) -> bool:
    """Return whether FCTT explicitly reports that a jornada has no results."""
    return "no s'han trobat resultats" in text.casefold()


def fetch_checked_group_page(
    group: str,
    jornada: int,
    *,
    timeout: float,
    retries: int,
    empty_retries: int,
    empty_retry_delay: float,
    opener,
    pacer: RequestPacer,
) -> tuple[bytes, str]:
    """Fetch a valid jornada page and cautiously recheck an empty result page."""
    for empty_attempt in range(empty_retries + 1):
        page = fetch_group_page(group, jornada, timeout=timeout, retries=retries, opener=opener, pacer=pacer)
        text = validate_page(page, group_urls(group, jornada)[-1])
        if not has_no_results(text) or empty_attempt == empty_retries:
            return page, text
        delay = empty_retry_delay * (empty_attempt + 1)
        LOGGER.warning("%s jornada %s no conté resultats; es tornarà a consultar en %.1f s", group, jornada, delay)
        time.sleep(delay)
    raise RuntimeError(f"No s'ha pogut validar {group} jornada {jornada}")


def append_failure(failure_log: Path, *, group: str, jornada: int, error: Exception) -> None:
    failure_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {"group": group, "jornada": jornada, "error": str(error), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with failure_log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def download_actas(
    *,
    output_root: Path,
    groups: Iterable[str] = GROUPS,
    jornadas: Iterable[int] = MATCH_DAYS,
    timeout: float = 30,
    retries: int = 4,
    request_delay: float = 5.0,
    empty_retries: int = 1,
    empty_retry_delay: float = 30.0,
    overwrite: bool = False,
    dry_run: bool = False,
    failure_log: Path | None = None,
) -> int:
    """Save each selected FCTT jornada page as HTML and return new file count."""
    if retries < 1 or empty_retries < 0 or request_delay < 0 or empty_retry_delay < 0:
        raise ValueError("Els reintents i les esperes han de ser valors no negatius; retries ha de ser almenys 1")
    saved = 0
    opener = create_opener()
    pacer = RequestPacer(request_delay)
    for group in groups:
        if group not in GROUPS:
            raise ValueError(f"Grup no vàlid: {group}")
        for jornada in jornadas:
            if jornada not in MATCH_DAYS:
                raise ValueError(f"Jornada no vàlida: {jornada}")
            page, text = b"", ""
            try:
                page, text = fetch_checked_group_page(
                    group, jornada, timeout=timeout, retries=retries, empty_retries=empty_retries,
                    empty_retry_delay=empty_retry_delay, opener=opener, pacer=pacer,
                )
            except (HTTPError, URLError, RuntimeError, OSError) as error:
                LOGGER.error("No s'ha descarregat %s jornada %s: %s", group, jornada, error)
                if failure_log and not dry_run:
                    append_failure(failure_log, group=group, jornada=jornada, error=error)
                continue
            season, category = extract_metadata(text, group)
            destination = output_root / season / category / group / f"jornada_{jornada}.html"
            existing_is_empty = destination.exists() and has_no_results(destination.read_text(encoding="utf-8", errors="replace"))
            replace_empty = existing_is_empty and not has_no_results(text)
            if destination.exists() and not overwrite and not replace_empty:
                LOGGER.info("Ja existeix: %s", destination)
                continue
            if replace_empty:
                LOGGER.info("Substituint la jornada buida publicada anteriorment: %s", destination)
            LOGGER.info("Descarregant jornada %s -> %s", jornada, destination)
            if has_no_results(text):
                LOGGER.warning("%s jornada %s no conté resultats encara", group, jornada)
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(page)
            saved += 1
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directori arrel de sortida")
    parser.add_argument("--groups", nargs="+", choices=GROUPS, default=list(GROUPS))
    parser.add_argument("--jornadas", nargs="+", type=int, default=list(MATCH_DAYS), metavar="N")
    parser.add_argument("--overwrite", action="store_true", help="Tornar a descarregar fitxers existents")
    parser.add_argument("--dry-run", action="store_true", help="No escriure fitxers; només mostrar què es trobaria")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--request-delay", type=float, default=5.0, help="Segons mínims entre peticions; respecta el servidor")
    parser.add_argument("--empty-retries", type=int, default=1, help="Reintents limitats per a una jornada sense resultats")
    parser.add_argument("--empty-retry-delay", type=float, default=30.0, help="Espera inicial entre consultes d'una jornada sense resultats")
    parser.add_argument("--failure-log", type=Path, default=Path("resources") / "download_failures.jsonl", help="Registre JSONL de jornades fallides")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.retries < 1 or args.empty_retries < 0 or args.request_delay < 0 or args.empty_retry_delay < 0:
        parser.error("Els reintents i les esperes han de ser valors no negatius; --retries ha de ser almenys 1")
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        count = download_actas(output_root=args.output, groups=args.groups, jornadas=args.jornadas,
                               timeout=args.timeout, retries=args.retries, overwrite=args.overwrite,
                               dry_run=args.dry_run, request_delay=args.request_delay, empty_retries=args.empty_retries,
                               empty_retry_delay=args.empty_retry_delay, failure_log=args.failure_log)
    except (HTTPError, URLError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    LOGGER.warning("Actas noves: %s", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
