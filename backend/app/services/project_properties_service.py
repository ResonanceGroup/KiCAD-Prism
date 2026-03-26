from copy import deepcopy
import math
import re
from pathlib import Path
from typing import Callable, Optional


_STRING_PATTERN = r'"((?:[^"\\]|\\.)*)"'
_FILE_METADATA_CACHE_MAX_ENTRIES = 128
_file_metadata_cache: dict[tuple[str, str], dict[str, object]] = {}


def _unescape_kicad_string(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r"\"", '"')


def _extract_sexpr_block(text: str, token: str) -> Optional[str]:
    start = text.find(f"({token}")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def _extract_sexpr_blocks(text: str, token: str) -> list[str]:
    blocks: list[str] = []
    start = 0

    while True:
        match_index = text.find(f"({token}", start)
        if match_index == -1:
            break

        block = _extract_sexpr_block(text[match_index:], token)
        if not block:
            break

        blocks.append(block)
        start = match_index + len(block)

    return blocks


def _extract_string_value(block: str, key: str) -> Optional[str]:
    match = re.search(rf"\({re.escape(key)}\s+{_STRING_PATTERN}\)", block)
    if not match:
        return None
    return _unescape_kicad_string(match.group(1))


def _extract_number_value(block: str, key: str) -> Optional[float]:
    match = re.search(rf"\({re.escape(key)}\s+([-+]?\d+(?:\.\d+)?)\)", block)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_int_value(block: str, key: str) -> Optional[int]:
    value = _extract_number_value(block, key)
    if value is None:
        return None
    return int(value)


def _extract_point(block: str, key: str) -> Optional[tuple[float, float]]:
    match = re.search(rf"\({re.escape(key)}\s+([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\)", block)
    if not match:
        return None

    try:
        return float(match.group(1)), float(match.group(2))
    except ValueError:
        return None


def _extract_xy_points(block: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for left, right in re.findall(r"\(xy\s+([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\)", block):
        try:
            points.append((float(left), float(right)))
        except ValueError:
            continue
    return points


def _round_dimension(value: float) -> float:
    return round(value, 2)


def _extract_pcb_dimensions(text: str) -> Optional[dict]:
    points: list[tuple[float, float]] = []

    for token in ("gr_line", "gr_rect", "gr_arc", "gr_curve", "gr_poly", "gr_circle"):
        for block in _extract_sexpr_blocks(text, token):
            if '(layer "Edge.Cuts")' not in block:
                continue

            token_points = [
                point
                for point in (
                    _extract_point(block, "start"),
                    _extract_point(block, "end"),
                    _extract_point(block, "mid"),
                    _extract_point(block, "center"),
                )
                if point is not None
            ]
            token_points.extend(_extract_xy_points(block))

            if token == "gr_circle":
                center = _extract_point(block, "center")
                edge = _extract_point(block, "end")
                if center and edge:
                    radius = math.dist(center, edge)
                    token_points.extend(
                        [
                            (center[0] - radius, center[1]),
                            (center[0] + radius, center[1]),
                            (center[0], center[1] - radius),
                            (center[0], center[1] + radius),
                        ]
                    )

            points.extend(token_points)

    if len(points) < 2:
        return None

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)

    if width <= 0 or height <= 0:
        return None

    return {
        "width_mm": _round_dimension(width),
        "height_mm": _round_dimension(height),
    }


def _relative_to_project(project_path: str, file_path: str) -> str:
    return Path(file_path).resolve().relative_to(Path(project_path).resolve()).as_posix()


def _parse_title_block(text: str) -> Optional[dict]:
    block = _extract_sexpr_block(text, "title_block")
    if not block:
        return None

    comments = {
        index: _unescape_kicad_string(value)
        for index, value in re.findall(rf"\(comment\s+(\d+)\s+{_STRING_PATTERN}\)", block)
    }

    return {
        "title": _extract_string_value(block, "title") or "",
        "date": _extract_string_value(block, "date") or "",
        "rev": _extract_string_value(block, "rev") or "",
        "company": _extract_string_value(block, "company") or "",
        "comments": comments,
    }


def invalidate_project_properties_cache(project_path: Optional[str] = None) -> None:
    global _file_metadata_cache

    if project_path is None:
        _file_metadata_cache = {}
        return

    resolved_project = str(Path(project_path).resolve())
    _file_metadata_cache = {
        key: value
        for key, value in _file_metadata_cache.items()
        if key[0] != resolved_project
    }


def _trim_file_metadata_cache() -> None:
    while len(_file_metadata_cache) > _FILE_METADATA_CACHE_MAX_ENTRIES:
        oldest_key = next(iter(_file_metadata_cache))
        _file_metadata_cache.pop(oldest_key, None)


def _load_cached_file_metadata(
    project_path: str,
    file_path: Optional[str],
    parser: Callable[[str, str, str], dict],
) -> Optional[dict]:
    if not file_path:
        return None

    path = Path(file_path)
    try:
        stat = path.stat()
    except OSError:
        return None

    resolved_project = str(Path(project_path).resolve())
    resolved_file = str(path.resolve())
    cache_key = (resolved_project, resolved_file)
    cached = _file_metadata_cache.get(cache_key)

    if (
        cached
        and cached.get("mtime_ns") == stat.st_mtime_ns
        and cached.get("size") == stat.st_size
    ):
        metadata = cached.get("metadata")
        return deepcopy(metadata) if isinstance(metadata, dict) else None

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        relative_path = _relative_to_project(project_path, str(path))
    except ValueError:
        relative_path = path.name

    metadata = parser(text, relative_path, path.name)
    _file_metadata_cache[cache_key] = {
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "metadata": deepcopy(metadata),
    }
    _trim_file_metadata_cache()
    return metadata


def extract_schematic_metadata(project_path: str, file_path: Optional[str]) -> Optional[dict]:
    return _load_cached_file_metadata(
        project_path,
        file_path,
        lambda text, relative_path, filename: {
            "path": relative_path,
            "filename": filename,
            "version": _extract_int_value(text, "version"),
            "generator": _extract_string_value(text, "generator"),
            "generator_version": _extract_string_value(text, "generator_version"),
            "paper": _extract_string_value(text, "paper"),
            "uuid": _extract_string_value(text, "uuid"),
            "title_block": _parse_title_block(text),
        },
    )


def extract_pcb_metadata(project_path: str, file_path: Optional[str]) -> Optional[dict]:
    return _load_cached_file_metadata(
        project_path,
        file_path,
        lambda text, relative_path, filename: {
            "path": relative_path,
            "filename": filename,
            "version": _extract_int_value(text, "version"),
            "generator": _extract_string_value(text, "generator"),
            "generator_version": _extract_string_value(text, "generator_version"),
            "paper": _extract_string_value(text, "paper"),
            "dimensions_mm": _extract_pcb_dimensions(text),
            "thickness_mm": _extract_number_value(_extract_sexpr_block(text, "general") or "", "thickness"),
            "title_block": _parse_title_block(text),
        },
    )


# ---------------------------------------------------------------------------
# BOM generation from .kicad_sch files
# ---------------------------------------------------------------------------

_BOM_SKIP_FIELDS = frozenset({
    "ki_fp_filters", "ki_locked", "ki_keywords",
    "ki_description", "ki_description_text",
})


def _natural_sort_key(s: str) -> list:
    """Split a string into alternating text/numeric segments for natural sort."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", s)]


def parse_bom_from_schematic(text: str) -> list[dict]:
    """
    Extract component instances from KiCAD schematic text.

    Returns a list of property dicts with at minimum ``Reference``, ``Value``,
    ``Footprint``, ``Datasheet``, and ``Description`` keys plus any custom fields.
    Power / virtual symbols (``in_bom no``, or references starting with ``#``)
    are excluded.
    """
    # Skip the lib_symbols block – it contains symbol *definitions*, not instances.
    lib_symbols_end = 0
    lib_start = text.find("(lib_symbols")
    if lib_start != -1:
        lib_block = _extract_sexpr_block(text[lib_start:], "lib_symbols")
        if lib_block:
            lib_symbols_end = lib_start + len(lib_block)

    components: list[dict] = []
    search_text = text[lib_symbols_end:]

    for block in _extract_sexpr_blocks(search_text, "symbol"):
        if "(in_bom yes)" not in block:
            continue

        props: dict[str, str] = {}
        for prop_block in _extract_sexpr_blocks(block, "property"):
            m = re.match(
                r"\(property\s+" + _STRING_PATTERN + r"\s+" + _STRING_PATTERN,
                prop_block,
            )
            if m:
                key = _unescape_kicad_string(m.group(1))
                val = _unescape_kicad_string(m.group(2))
                props[key] = val

        ref = props.get("Reference", "")
        # Exclude virtual / power flags whose reference starts with '#'
        if not ref or ref.startswith("#"):
            continue

        components.append(props)

    return components


def build_bom(components: list[dict]) -> list[dict]:
    """
    Group components by Value and return sorted BOM rows.

    Each row contains:
    ``value``, ``quantity``, ``references``, ``footprints``, ``datasheet``,
    ``description``, ``extra_fields``.
    Rows are sorted by natural order of their first reference designator.
    """
    groups: dict[str, list[dict]] = {}
    for comp in components:
        key = comp.get("Value", "").lower()
        groups.setdefault(key, []).append(comp)

    rows: list[dict] = []
    for comps in groups.values():
        refs = sorted(
            (c.get("Reference", "") for c in comps),
            key=_natural_sort_key,
        )

        # Unique footprints preserving first-appearance order
        footprints: list[str] = []
        seen_fps: set[str] = set()
        for c in comps:
            fp = c.get("Footprint", "").strip()
            if fp and fp not in seen_fps:
                footprints.append(fp)
                seen_fps.add(fp)

        first = comps[0]
        datasheet = first.get("Datasheet", "")
        if datasheet in ("~", ""):
            datasheet = ""

        # Collect extra / custom fields, skipping internal KiCAD keys
        extra: dict[str, str] = {}
        for c in comps:
            for k, v in c.items():
                if k in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
                    continue
                if k.startswith("ki_") or k in _BOM_SKIP_FIELDS:
                    continue
                v = v.strip()
                if v and k not in extra:
                    extra[k] = v

        rows.append({
            "value": first.get("Value", ""),
            "quantity": len(refs),
            "references": refs,
            "footprints": footprints,
            "datasheet": datasheet,
            "description": first.get("Description", ""),
            "extra_fields": extra,
        })

    rows.sort(key=lambda r: _natural_sort_key(r["references"][0]) if r["references"] else [])
    return rows
