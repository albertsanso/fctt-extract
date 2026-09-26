"""Parse FCTT jornada HTML pages into JSON acta files.

Each downloaded jornada page contains several encounters.  This script emits
one JSON object per encounter so every output file follows model-definition.json.
Input pages live at ``{season}/{male|female}/{category}/[G{n}/]jornada-{n}.html`` and
the JSON files mirror that hierarchy as ``.../jornada-{n}-partido-{id}.json``.
It intentionally uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse


DEFAULT_INPUT = Path(__file__).resolve().parents[2] / "resources" / "actas-html"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "resources" / "actas-json"
FEDERATION = "Federació Catalana de Tennis Taula"
GENDERS = {"male": "masculino", "female": "femenino"}
MALE_CATEGORY = "tercera-nacional"
FEMALE_CATEGORY_PREFIX = "copa-catalana-femenina"
SEASON_PATTERN = re.compile(r"\d{4}-\d{4}")
GROUP_PATTERN = re.compile(r"G(\d+)", re.I)
LOGGER = logging.getLogger("fctt-parser")


@dataclass
class Node:
    tag: str = "root"
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)

    def text(self) -> str:
        return " ".join(
            part for child in self.children
            for part in ([child] if isinstance(child, str) else [child.text()])
            if part.strip()
        ).strip()

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def find_all(self, *, tag: str | None = None, class_name: str | None = None) -> list["Node"]:
        result: list[Node] = []
        for child in self.children:
            if not isinstance(child, Node):
                continue
            if (tag is None or child.tag == tag) and (class_name is None or child.has_class(class_name)):
                result.append(child)
            result.extend(child.find_all(tag=tag, class_name=class_name))
        return result

    def find_first(self, *, tag: str | None = None, class_name: str | None = None) -> "Node | None":
        matches = self.find_all(tag=tag, class_name=class_name)
        return matches[0] if matches else None


@dataclass(frozen=True)
class Location:
    """Position of a jornada page inside the ``{season}/{gender}/{category}/[G{n}]`` tree."""

    season: str | None = None
    gender: str | None = None
    category: str | None = None
    group: str | None = None


def source_location(source: Path) -> Location:
    parts = source.resolve().parent.parts
    for index in range(len(parts) - 1, -1, -1):
        if SEASON_PATTERN.fullmatch(parts[index]):
            rest = list(parts[index + 1:])
            gender = rest.pop(0) if rest and rest[0] in GENDERS else None
            category = rest.pop(0) if rest and not GROUP_PATTERN.fullmatch(rest[0]) else None
            group = rest[0] if rest and GROUP_PATTERN.fullmatch(rest[0]) else None
            return Location(parts[index], gender, category, group)
    group = parts[-1] if parts and GROUP_PATTERN.fullmatch(parts[-1]) else None
    return Location(group=group)


def gender_from_competition(competition: str | None) -> str:
    return "female" if competition and re.search(r"FEMEN", competition, re.I) else "male"


def default_category(gender: str, competition: str | None) -> str:
    if gender == "male":
        return MALE_CATEGORY
    division = re.search(r"\b(\d+)\s*[aª]\b", competition or "", re.I)
    return f"{FEMALE_CATEGORY_PREFIX}-{division.group(1)}a" if division else FEMALE_CATEGORY_PREFIX


class DocumentParser(HTMLParser):
    """Build a small tolerant DOM suitable for the known FCTT markup."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if node.tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(Node(tag.lower(), {key: value or "" for key, value in attrs}))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_document(html: str) -> Node:
    parser = DocumentParser()
    parser.feed(html)
    parser.close()
    return parser.root


def class_text(node: Node | None, class_name: str) -> str:
    return clean(node.find_first(class_name=class_name).text()) if node and node.find_first(class_name=class_name) else ""


def first_attr(node: Node | None, tag: str, attr: str) -> str | None:
    if not node:
        return None
    match = node.find_first(tag=tag)
    return match.attrs.get(attr) if match else None


def query_value(href: str | None, key: str) -> str | None:
    if not href:
        return None
    values = parse_qs(urlparse(href).query).get(key)
    return str(values[0]) if values else None


def participant_from_cell(cell: Node | None) -> list[dict[str, object]]:
    if not cell:
        return []
    players: list[dict[str, object]] = []
    for link in cell.find_all(tag="a"):
        name = clean(link.text())
        identifier = query_value(link.attrs.get("href"), "codi_jugador")
        if not name:
            continue
        player: dict[str, object] = {"nombre": name, "licencia": identifier or "0"}
        if identifier:
            player["id"] = identifier
        players.append(player)
    if not players and clean(cell.text()):
        players.append({"nombre": clean(cell.text()), "licencia": "0"})
    return players


def nullable_person() -> None:
    return None


def team_from_cell(cell: Node | None) -> dict[str, object]:
    name = clean(cell.text()) if cell else None
    href = first_attr_node(cell, "a", "href").attrs.get("href") if first_attr_node(cell, "a", "href") else None
    return {
        "id": query_value(href, "team_name_id"),
        "nombre": name or None,
        "delegado": nullable_person(),
        "entrenador": nullable_person(),
    }


def first_attr_node(node: Node | None, tag: str, attr: str) -> Node | None:
    if not node:
        return None
    return node.find_first(tag=tag)


def parse_score(value: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\s*-\s*(\d+)", clean(value))
    return (int(match.group(1)), int(match.group(2))) if match else None


def parse_date_time(value: str) -> tuple[str | None, str | None]:
    parts = [clean(part) for part in re.split(r"\s+", value) if clean(part)]
    date_value = next((part for part in parts if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", part)), None)
    time_value = next((part for part in parts if re.fullmatch(r"\d{1,2}:\d{2}", part)), None)
    parsed_date = None
    if date_value:
        try:
            parsed_date = datetime.strptime(date_value, "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    return parsed_date, time_value


def parse_season_title(root: Node) -> tuple[str | None, str | None, int | None]:
    title_node = root.find_first(class_name="br-apic-league-title")
    title = clean(title_node.text()) if title_node else ""
    season_match = re.search(r"Temporada\s+(\d{4})\s*/\s*(\d{4})", title, re.I)
    group_match = re.search(r"GRUP\s+(\d+)", title, re.I)
    competition = re.sub(r"\s*-?\s*Temporada\s+\d{4}\s*/\s*\d{4}.*$", "", title, flags=re.I).strip(" -") or None
    return (f"{season_match.group(1)}/{season_match.group(2)}" if season_match else None, competition, int(group_match.group(1)) if group_match else None)


def extract_jornada(root: Node, source: Path) -> int:
    heading = root.find_first(class_name="jornada-results-title")
    match = re.search(r"Jornada\s+(\d+)", heading.text() if heading else "", re.I)
    if match:
        return int(match.group(1))
    match = re.search(r"jornada[_-](\d+)", source.name, re.I)
    if match:
        return int(match.group(1))
    raise ValueError(f"No s'ha pogut determinar la jornada de {source}")


def parse_match(match_node: Node, *, common: dict[str, object], number: int) -> dict[str, object]:
    datetime_node = match_node.find_first(class_name="match-datetime")
    date, hour = parse_date_time(datetime_node.text() if datetime_node else "")
    home_node = match_node.find_first(class_name="team-home")
    away_node = match_node.find_first(class_name="team-away")
    score_text = class_text(match_node, "match-score")
    final_score = parse_score(score_text)
    table = match_node.find_first(class_name="match-results-table")
    rows = table.find_all(tag="tr") if table else []
    data_rows = [row for row in rows if row.find_first(class_name="position")]
    lineups: dict[str, dict[str, object]] = {"local": {}, "visitante": {}}
    doubles: dict[str, list[dict[str, object]]] | None = None
    matches: list[dict[str, object]] = []

    for index, row in enumerate(data_rows, start=1):
        positions = row.find_all(class_name="position")
        infos = row.find_all(class_name="player-info")
        games = [clean(cell.text()) for cell in row.find_all(class_name="game")]
        result = parse_score(class_text(row, "result"))
        accumulated = parse_score(class_text(row, "global"))
        local_letter = clean(positions[0].text()) if positions else ""
        visitor_letter = clean(positions[1].text()) if len(positions) > 1 else ""
        local_players = participant_from_cell(infos[0] if infos else None)
        visitor_players = participant_from_cell(infos[1] if len(infos) > 1 else None)
        is_doubles = local_letter.casefold() == "db" or visitor_letter.casefold() == "db"
        if is_doubles:
            doubles = {"local": local_players, "visitante": visitor_players}
        else:
            if local_letter and local_players:
                lineups["local"][local_letter] = local_players[0]
            if visitor_letter and visitor_players:
                lineups["visitante"][visitor_letter] = visitor_players[0]
        sets = []
        for set_number, game in enumerate(games, start=1):
            set_score = parse_score(game)
            if set_score:
                sets.append({"set": set_number, "local": set_score[0], "visitante": set_score[1]})
        participant_local: dict[str, object] = {"letra": local_letter}
        participant_visitor: dict[str, object] = {"letra": visitor_letter}
        if is_doubles:
            participant_local["jugadores"] = local_players
            participant_visitor["jugadores"] = visitor_players
        elif local_players:
            participant_local.update(local_players[0])
        elif local_letter:
            participant_local["nombre"] = None
        if visitor_players:
            participant_visitor.update(visitor_players[0])
        elif visitor_letter:
            participant_visitor["nombre"] = None
        winner = None if not result or result == (0, 0) else ("local" if result[0] > result[1] else "visitante")
        partido: dict[str, object] = {
            "numero": index,
            "tipo": "dobles" if is_doubles else "individual",
            "cruce": f"{local_letter} vs {visitor_letter}",
            "local": participant_local,
            "visitante": participant_visitor,
            "sets": sets,
            "resultado_juegos": {"local": result[0], "visitante": result[1]} if result else None,
            "ganador": winner,
            "marcador_acumulado": {"local": accumulated[0], "visitante": accumulated[1]} if accumulated else {"local": 0, "visitante": 0},
        }
        if not result:
            partido["no_disputado"] = True
            partido["motivo"] = "Resultado no disponible"
        matches.append(partido)

    # The results table always lists the A/B/C column first; it belongs to the away team when the
    # last running score mirrors the final score.
    abc_is_home = True
    last_accumulated = matches[-1]["marcador_acumulado"] if matches else None
    if (final_score and final_score[0] != final_score[1] and last_accumulated
            and (last_accumulated["local"], last_accumulated["visitante"]) == (final_score[1], final_score[0])):
        abc_is_home = False
        lineups = {"local": lineups["visitante"], "visitante": lineups["local"]}
        if doubles:
            doubles = {"local": doubles["visitante"], "visitante": doubles["local"]}
        matches = [swap_sides(partido) for partido in matches]

    field = class_text(match_node, "field-info")
    referee = class_text(match_node, "referee-info")
    referee = re.sub(r"^[^:]+:\s*", "", referee).strip() or None
    winner = None
    if final_score and final_score[0] != final_score[1]:
        winner = clean(home_node.text()) if final_score[0] > final_score[1] and home_node else clean(away_node.text()) if away_node else None
    acta_link = match_node.find_first(class_name="acta-link")
    acta_id_match = re.search(r"/partido/(\d+)/", acta_link.attrs.get("href", "")) if acta_link else None
    acta_id = acta_id_match.group(1) if acta_id_match else str(number)
    return {
        **common,
        "jornada": common["jornada"],
        "fecha": date,
        "hora": hour,
        "lugar": {"ciudad": None, "recinto": re.sub(r"^[^:]+:\s*", "", field).strip() or None},
        "equipos": {"local": team_from_cell(home_node), "visitante": team_from_cell(away_node)},
        "abc_es_local": abc_is_home,
        "arbitros": {"principal": {"nombre": referee, "licencia": None} if referee else None, "asistente": None},
        "alineaciones": lineups,
        "dobles": doubles,
        "partidos": matches,
        "resultado_final": {
            "ganador": winner,
            "marcador_partidos": {"local": final_score[0], "visitante": final_score[1]} if final_score else None,
            "marcador_juegos": None,
        },
        "acta_protestada": False,
        "_id": acta_id,
    }


def swap_score(score: dict[str, object] | None) -> dict[str, object] | None:
    return {"local": score["visitante"], "visitante": score["local"]} if score else score


def swap_sides(partido: dict[str, object]) -> dict[str, object]:
    swapped = dict(partido)
    swapped["local"], swapped["visitante"] = partido["visitante"], partido["local"]
    swapped["sets"] = [{"set": item["set"], **swap_score(item)} for item in partido["sets"]]
    swapped["resultado_juegos"] = swap_score(partido["resultado_juegos"])
    swapped["marcador_acumulado"] = swap_score(partido["marcador_acumulado"])
    if partido["ganador"]:
        swapped["ganador"] = "visitante" if partido["ganador"] == "local" else "local"
    return swapped


def parse_file(source: Path) -> list[dict[str, object]]:
    root = parse_document(source.read_text(encoding="utf-8", errors="replace"))
    season, competition, title_group = parse_season_title(root)
    location = source_location(source)
    group_match = GROUP_PATTERN.fullmatch(location.group or "")
    group = title_group or (int(group_match.group(1)) if group_match else 0)
    gender = location.gender or gender_from_competition(competition)
    if not season and location.season:
        season = location.season.replace("-", "/")
    common = {
        "federacion": FEDERATION, "temporada": season, "genero": GENDERS[gender], "competicion": competition,
        "grupo": group, "jornada": extract_jornada(root, source),
    }
    return [parse_match(node, common=common, number=index) for index, node in enumerate(root.find_all(class_name="match-container"), start=1)]


def output_path(output_root: Path, source: Path, data: dict[str, object]) -> Path:
    location = source_location(source)
    season = location.season or str(data["temporada"] or "").replace("/", "-")
    if not SEASON_PATTERN.fullmatch(season):
        raise ValueError(f"No s'ha pogut determinar la temporada de {source}")
    gender = next(key for key, value in GENDERS.items() if value == data["genero"])
    category = location.category or default_category(gender, data["competicion"])
    folder = output_root / season / gender / category
    if location.group:
        folder /= location.group
    elif gender == "male" and data["grupo"]:
        folder /= f"G{data['grupo']}"
    return folder / f"jornada-{data['jornada']}-partido-{data['_id']}.json"


def parse_all(
    input_root: Path,
    output_root: Path,
    *,
    overwrite: bool = False,
    seasons: Iterable[str] | None = None,
    genders: Iterable[str] | None = None,
) -> int:
    written = 0
    seasons = set(seasons) if seasons is not None else None
    genders = set(genders) if genders is not None else None
    sources = [input_root] if input_root.is_file() else sorted(input_root.rglob("*.html"))
    for source in sources:
        location = source_location(source)
        if seasons is not None and location.season not in seasons:
            continue
        if genders is not None and location.gender not in genders:
            continue
        try:
            records = parse_file(source)
        except (OSError, ValueError) as error:
            LOGGER.error("%s: %s", source, error)
            continue
        if not records:
            LOGGER.warning("Sense partits a %s; no es generarà cap JSON", source)
            continue
        for record in records:
            try:
                destination = output_path(output_root, source, record)
            except ValueError as error:
                LOGGER.error("%s", error)
                continue
            record.pop("_id", None)
            if destination.exists() and not overwrite:
                LOGGER.info("Ja existeix: %s", destination)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written += 1
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seasons", nargs="+", metavar="YYYY-YYYY", help="Temporades a processar (per defecte, totes)")
    parser.add_argument("--genders", nargs="+", choices=sorted(GENDERS), help="male i/o female (per defecte, tots dos)")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s: %(message)s")
    if not args.input.exists():
        parser.error(f"No existeix el directori d'entrada: {args.input}")
    count = parse_all(args.input, args.output, overwrite=args.overwrite, seasons=args.seasons, genders=args.genders)
    LOGGER.warning("JSON nous: %s", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
