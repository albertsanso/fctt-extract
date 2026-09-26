"""Download FCTT league jornada pages (male TDM groups and female Copa Catalana) as HTML files.

Leagues are discovered from https://fctt.cat/competicions-estatals/, where the
current season is listed first and previous seasons under "Altres temporades".
Pages are stored as ``{season}/{male|female}/{category}/[G{n}/]jornada-{n}.html``.
"""

from __future__ import annotations

import argparse
import email.utils
import html as html_lib
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = "https://fctt.cat"
INDEX_URL = f"{BASE_URL}/competicions-estatals/"
GENDERS = ("male", "female")
MALE_CATEGORY = "tercera-nacional"
FEMALE_CATEGORY_PREFIX = "copa-catalana-femenina"
USER_AGENT = "fctt-actas-downloader/1.0 (+https://fctt.cat/lligues/)"
LOGGER = logging.getLogger("fctt-actas")
TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
BLOCK_PAGE_MARKERS = ("access denied", "forbidden", "captcha", "cloudflare", "request blocked")

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "resources" / "actas-html"


@dataclass(frozen=True)
class League:
    season: str
    gender: str
    category: str
    group: str | None
    url: str

    @property
    def label(self) -> str:
        return " ".join(part for part in (self.season, self.gender, self.category, self.group) if part)

    def page_url(self, jornada: int) -> str:
        return f"{self.url}?jornada={jornada}"

    def destination(self, output_root: Path, jornada: int) -> Path:
        folder = output_root / self.season / self.gender / self.category
        if self.group:
            folder = folder / self.group
        return folder / f"jornada-{jornada}.html"


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


def html_tokens(page: str) -> Iterable[tuple[str, str]]:
    """Yield ("text", value) and ("link", href) tokens in document order."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    for match in re.finditer(r"<a\b[^>]*\bhref=\"([^\"]+)\"[^>]*>|<[^>]+>|([^<]+)", page, re.I):
        if match.group(1):
            yield "link", html_lib.unescape(match.group(1))
        elif match.group(2):
            text = re.sub(r"\s+", " ", html_lib.unescape(match.group(2))).strip()
            if text:
                yield "text", text


def next_season(season: str) -> str:
    start, end = (int(part) for part in season.split("-"))
    return f"{start + 1}-{end + 1}"


def discover_leagues(index_html: str) -> list[League]:
    """Parse the TDM and Copa Catalana Femenina blocks of the competitions page."""
    found: list[tuple[str | None, str, str, str | None, str]] = []
    gender = None
    season: str | None = None
    label = ""
    for kind, value in html_tokens(index_html):
        if kind == "text":
            if value.casefold().startswith("lligues estatals"):
                break
            if value == "TDM":
                gender, season = "male", None
            elif value.casefold() == "copa catalana femenina":
                gender, season = "female", None
            elif match := re.fullmatch(r"Temporada\s+(\d{4})\s*/\s*(\d{4})", value, re.I):
                season = f"{match.group(1)}-{match.group(2)}"
            label = value
            continue
        if "/lligues/" not in value or gender is None:
            continue
        url = value if value.endswith("/") else value + "/"
        if gender == "male" and (match := re.fullmatch(r"TDM\s+G(\d+)", label, re.I)):
            found.append((season, "male", MALE_CATEGORY, f"G{match.group(1)}", url))
        elif gender == "female" and (match := re.fullmatch(r"(\d+)a\s+Divisi.*", label, re.I)):
            found.append((season, "female", f"{FEMALE_CATEGORY_PREFIX}-{match.group(1)}a", None, url))
    listed = sorted({entry[0] for entry in found if entry[0]})
    if not found or not listed:
        raise RuntimeError(f"No s'han trobat lligues TDM/Copa Catalana Femenina a {INDEX_URL}")
    current = next_season(listed[-1])
    return [League(season or current, gender, category, group, url) for season, gender, category, group, url in found]


def jornada_numbers(text: str) -> tuple[int, ...]:
    """Return the jornadas offered by a league page's jornada selector."""
    return tuple(sorted({int(number) for number in re.findall(r"data-jornada=\"(\d+)\"", text)}))


def page_season(text: str) -> str | None:
    match = re.search(r"Temporada\s+(\d{4})\s*[/\-]\s*(\d{4})", text, re.I)
    return f"{match.group(1)}-{match.group(2)}" if match else None


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


def fetch_checked_page(
    league: League,
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
    url = league.page_url(jornada)
    for empty_attempt in range(empty_retries + 1):
        page = fetch(url, timeout=timeout, retries=retries, opener=opener, pacer=pacer)
        text = validate_page(page, url)
        if not has_no_results(text) or empty_attempt == empty_retries:
            return page, text
        delay = empty_retry_delay * (empty_attempt + 1)
        LOGGER.warning("%s jornada %s no conté resultats; es tornarà a consultar en %.1f s", league.label, jornada, delay)
        time.sleep(delay)
    raise RuntimeError(f"No s'ha pogut validar {league.label} jornada {jornada}")


def append_failure(failure_log: Path, *, league: League, jornada: int, error: Exception) -> None:
    failure_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "season": league.season, "gender": league.gender, "category": league.category, "group": league.group,
        "jornada": jornada, "url": league.page_url(jornada), "error": str(error),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with failure_log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def is_complete(path: Path) -> bool:
    return path.exists() and not has_no_results(path.read_text(encoding="utf-8", errors="replace"))


def download_actas(
    *,
    output_root: Path,
    leagues: Iterable[League] | None = None,
    seasons: Iterable[str] | None = None,
    genders: Iterable[str] | None = None,
    groups: Iterable[str] | None = None,
    jornadas: Iterable[int] | None = None,
    timeout: float = 30,
    retries: int = 4,
    request_delay: float = 5.0,
    empty_retries: int = 1,
    empty_retry_delay: float = 30.0,
    overwrite: bool = False,
    dry_run: bool = False,
    failure_log: Path | None = None,
) -> int:
    """Save each selected FCTT jornada page as HTML and return the number of files written."""
    if retries < 1 or empty_retries < 0 or request_delay < 0 or empty_retry_delay < 0:
        raise ValueError("Els reintents i les esperes han de ser valors no negatius; retries ha de ser almenys 1")
    opener = create_opener()
    pacer = RequestPacer(request_delay)
    fetch_options = dict(timeout=timeout, retries=retries, empty_retries=empty_retries,
                         empty_retry_delay=empty_retry_delay, opener=opener, pacer=pacer)
    if leagues is None:
        index = validate_page(fetch(INDEX_URL, timeout=timeout, retries=retries, opener=opener, pacer=pacer), INDEX_URL)
        leagues = discover_leagues(index)
    selected = [
        league for league in leagues
        if (seasons is None or league.season in seasons)
        and (genders is None or league.gender in genders)
        and (groups is None or league.group in groups or league.category in groups)
    ]
    if not selected:
        raise ValueError("Cap lliga coincideix amb els filtres indicats")

    saved = 0
    for league in selected:
        LOGGER.info("Lliga %s -> %s", league.label, league.url)
        first = league.destination(output_root, 1)
        cached: dict[int, tuple[bytes, str]] = {}
        if first.exists() and not overwrite:
            available = jornada_numbers(first.read_text(encoding="utf-8", errors="replace"))
        else:
            try:
                cached[1] = fetch_checked_page(league, 1, **fetch_options)
            except (HTTPError, URLError, RuntimeError, OSError) as error:
                LOGGER.error("No s'ha pogut consultar %s: %s", league.label, error)
                if failure_log and not dry_run:
                    append_failure(failure_log, league=league, jornada=1, error=error)
                continue
            available = jornada_numbers(cached[1][1])
            season = page_season(cached[1][1])
            if season and season != league.season:
                LOGGER.warning("%s mostra la temporada %s a la pàgina", league.label, season)
        if not available:
            LOGGER.warning("%s no mostra el selector de jornades; només es desarà la jornada 1", league.label)
            available = (1,)
        wanted = [jornada for jornada in available if jornadas is None or jornada in jornadas]

        for jornada in wanted:
            destination = league.destination(output_root, jornada)
            if not overwrite and is_complete(destination):
                LOGGER.info("Ja existeix: %s", destination)
                continue
            try:
                page, text = cached.get(jornada) or fetch_checked_page(league, jornada, **fetch_options)
            except (HTTPError, URLError, RuntimeError, OSError) as error:
                LOGGER.error("No s'ha descarregat %s jornada %s: %s", league.label, jornada, error)
                if failure_log and not dry_run:
                    append_failure(failure_log, league=league, jornada=jornada, error=error)
                continue
            if destination.exists() and not overwrite and has_no_results(text):
                LOGGER.info("Encara sense resultats: %s", destination)
                continue
            if destination.exists() and not overwrite:
                LOGGER.info("Substituint la jornada buida publicada anteriorment: %s", destination)
            LOGGER.info("Descarregant %s jornada %s -> %s", league.label, jornada, destination)
            if has_no_results(text):
                LOGGER.warning("%s jornada %s no conté resultats encara", league.label, jornada)
            if not dry_run:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(page)
            saved += 1
    return saved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directori arrel de sortida")
    parser.add_argument("--seasons", nargs="+", metavar="YYYY-YYYY", help="Temporades a descarregar (per defecte, totes les llistades)")
    parser.add_argument("--genders", nargs="+", choices=GENDERS, help="male i/o female (per defecte, tots dos)")
    parser.add_argument("--groups", nargs="+", metavar="GRUP",
                        help="Grups masculins (G1, G2...) o categories femenines (copa-catalana-femenina-1a...)")
    parser.add_argument("--jornadas", nargs="+", type=int, metavar="N", help="Jornades concretes (per defecte, les que mostra la web)")
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
        count = download_actas(output_root=args.output, seasons=args.seasons, genders=args.genders, groups=args.groups,
                               jornadas=args.jornadas, timeout=args.timeout, retries=args.retries,
                               overwrite=args.overwrite, dry_run=args.dry_run, request_delay=args.request_delay,
                               empty_retries=args.empty_retries, empty_retry_delay=args.empty_retry_delay,
                               failure_log=args.failure_log)
    except (HTTPError, URLError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    LOGGER.warning("Actas noves: %s", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
