"""Read-only static checks for Infinity Android ads integrations."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:  # avoids a circular import at runtime; area_rollup imports Finding
    from area_rollup import AreaReport


SECRET_LABELS = {"Adjust token", "Facebook Client token", "Tiktok token"}
SKIP_DIRS = {".git", ".gradle", "build", ".idea", ".worktrees", "out"}
SOURCE_SUFFIXES = {".kt", ".java"}

# Captures the owner argument of every observe(...) call, tolerating the line
# wrapping and spacing that ktlint produces.
_OBSERVE_OWNER = re.compile(r"\.observe\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)")

_HEADER_ALIASES = {
    "id": {
        "id",
        "adid",
        "adunit",
        "adunitid",
        "adunitidentifier",
        "placementid",
        "placementidentifier",
        "maad",
        "maid",
    },
    "name": {
        "name",
        "adname",
        "placement",
        "placementname",
        "slot",
        "slotname",
        "ten",
        "tenvitri",
    },
    "Ads type": {
        "adstype",
        "adtype",
        "adformat",
        "format",
        "type",
        "loaiquangcao",
        "loaiads",
    },
    "Mô tả": {"mota", "description", "desc", "des", "note", "ghichu"},
    "Task Detail": {
        "taskdetail",
        "congviec",
        "chitietcongviec",
        "content",
        "noidung",
        "field",
        "fieldname",
        "tentruong",
        "key",
        "muc",
        "hangmuc",
    },
    "Document": {
        "document",
        "doc",
        "link",
        "tailieu",
        "detail",
        "chitiet",
        "value",
        "giatri",
        "data",
        "dulieu",
    },
}

_KIND_HEADER_ALIASES = {
    "ads": {
        "id": {"unitcode", "adcode", "adsid", "adunitcode", "macode", "madonvi"},
        "name": {"adskey", "adkey", "configkey", "placementkey", "adplacement", "keyquangcao"},
        "Ads type": {"adcategory", "adscategory", "category", "loaiformat"},
        "Mô tả": {"notes", "details", "content", "noidung"},
    },
    "working": {
        "Task Detail": {
            "content",
            "taskcontent",
            "item",
            "field",
            "key",
            "noidung",
            "hangmuc",
            "truongthongtin",
        },
        "Document": {
            "detail",
            "details",
            "value",
            "data",
            "result",
            "chitiet",
            "giatri",
            "dulieu",
        },
    },
}

_WORKING_KEY_ALIASES = {
    "App name": {"appname", "applicationname", "applicationtitle", "apptitle", "tenapp", "tenungdung"},
    "Package name": {
        "packagename",
        "package",
        "packageid",
        "applicationid",
        "bundleid",
        "bundleidentifier",
        "tenpackage",
    },
    "Firebase": {"firebase", "firebaseproject", "firebaseurl", "projectfirebase", "duanfirebase"},
    "Adjust token": {"adjusttoken", "adjustapptoken"},
    "Facebook App ID": {"facebookappid", "fbappid"},
    "Facebook Client token": {"facebookclienttoken", "fbclienttoken"},
    "Tiktok token": {"tiktoktoken", "tiktokapptoken"},
}

_KNOWN_AD_TYPES = {
    "app",
    "appopen",
    "banner",
    "collapsiblebanner",
    "inter",
    "interstitial",
    "mrec",
    "native",
    "open",
    "reward",
    "rewarded",
    "rewardedinterstitial",
}


# The 24 placement keys defined by the Infinity base project TestSill
# (com.itg.template), verified against its app/src/main/assets/ad_config.json
# on 2026-08-26. Pass --base-project to read the list from a base checkout
# instead, which is what tracks a base that has moved on.
BASE_PLACEMENT_KEYS = (
    "inter_splash",
    "banner_splash",
    "open_resume",
    "native_language_1",
    "native_language_1_click",
    "native_language_2",
    "native_language_2_click",
    "native_onboarding_1_1",
    "native_onboarding_2_1",
    "native_onboarding_1_4",
    "native_onboarding_2_4",
    "native_onboarding_fullscreen_1_3",
    "native_onboarding_fullscreen_2_3",
    "native_onboarding_fullscreen_1_4",
    "native_onboarding_fullscreen_2_4",
    "native_permission",
    "native_home",
    "inter_onboarding",
    "banner_home",
    "native_survey",
    "native_confirm_uninstall",
    "native_welcome",
    "inter_welcome",
    "reward_example",
)


def base_placement_keys(base_project: str | Path | None = None) -> tuple[str, ...]:
    """Return the base placement keys, from a base checkout when one is given."""
    if base_project is None:
        return BASE_PLACEMENT_KEYS
    config_path = Path(base_project) / "app" / "src" / "main" / "assets" / "ad_config.json"
    if not config_path.is_file():
        raise ValueError(
            f"Base project has no ad_config.json at {config_path}. "
            f"Point --base-project at the root of the Infinity base checkout, "
            f"or omit it to use the {len(BASE_PLACEMENT_KEYS)} keys bundled with this skill."
        )
    config = _config_data(config_path)
    if not config:
        raise ValueError(f"Base project ad_config.json is empty or not valid JSON: {config_path}")
    return tuple(config)


@dataclass(frozen=True)
class Placement:
    name: str
    ad_type: str
    ad_unit_id: str
    description: str
    row: int


@dataclass(frozen=True)
class AuditContract:
    placements: dict[str, Placement]
    admob_app_id: str | None
    source: str


@dataclass(frozen=True)
class ProjectChecklist:
    app_name: str | None
    package_name: str | None
    firebase_project: str | None
    required_values: dict[str, str]
    source: str


@dataclass
class Finding:
    rule_id: str
    category: str
    status: str
    expected: str
    observed: str
    recommendation: str
    location: str | None = None

    @classmethod
    def pass_(cls, rule_id: str, category: str, expected: str, observed: str, location: str | None = None) -> "Finding":
        return cls(rule_id, category, "PASS", expected, observed, "No action required.", location)

    @classmethod
    def fail(cls, rule_id: str, category: str, expected: str, observed: str, recommendation: str, location: str | None = None) -> "Finding":
        return cls(rule_id, category, "FAIL", expected, observed, recommendation, location)

    @classmethod
    def needs_mapping(cls, rule_id: str, expected: str, observed: str, recommendation: str, location: str | None = None) -> "Finding":
        return cls(rule_id, "placement_flow", "NEEDS_MAPPING", expected, observed, recommendation, location)

    @classmethod
    def needs_runtime(cls, rule_id: str, expected: str, observed: str, recommendation: str, location: str | None = None) -> "Finding":
        return cls(rule_id, "runtime", "NEEDS_RUNTIME_PROOF", expected, observed, recommendation, location)


@dataclass
class AuditReport:
    project_root: str
    contract: AuditContract
    checklist: ProjectChecklist
    findings: list[Finding] = field(default_factory=list)

    def finding(self, rule_id: str) -> Finding:
        return next(finding for finding in self.findings if finding.rule_id == rule_id)

    def counts(self) -> dict[str, int]:
        return dict(Counter(finding.status.lower() for finding in self.findings))

    def readiness(self) -> str:
        return "BLOCKED" if any(finding.status == "FAIL" for finding in self.findings) else "REVIEW_REQUIRED"


def _value(row: dict[str, str], *names: str) -> str:
    normalized = {str(key).strip().lower(): str(value or "").strip() for key, value in row.items()}
    for name in names:
        result = normalized.get(name.strip().lower(), "")
        if result:
            return result
    return ""


def _normalize_header(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", "", without_marks.casefold())


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:80])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {delimiter: sample.count(delimiter) for delimiter in (",", ";", "\t", "|")}
        return max(counts, key=counts.get) if any(counts.values()) else ","


def _read_table(path: Path) -> tuple[str, list[list[str]]]:
    text = path.read_text(encoding="utf-8-sig")
    delimiter = _detect_delimiter(text)
    return delimiter, list(csv.reader(io.StringIO(text), delimiter=delimiter))


def _semantic_header(value: str | None, kind: str | None = None) -> str | None:
    normalized = _normalize_header(value)
    if kind:
        for semantic, aliases in _KIND_HEADER_ALIASES[kind].items():
            if normalized in aliases:
                return semantic
    for semantic, aliases in _HEADER_ALIASES.items():
        if normalized in aliases:
            return semantic
    return None


def _canonical_working_key(value: str | None) -> str | None:
    normalized = _normalize_header(value)
    for canonical, aliases in _WORKING_KEY_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _looks_like_ad_unit_id(value: str) -> bool:
    value = value.strip()
    lowered = value.casefold()
    if not value or any(character.isspace() for character in value):
        return False
    if "/" in value or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f-]{27,}", lowered):
        return True
    return lowered.startswith(("ca-app-", "admob", "pub-", "g-"))


def _infer_id_column(headers: list[str], data_rows: list[list[str]]) -> int | None:
    if any(_semantic_header(header, "ads") == "id" for header in headers):
        return None

    candidates: list[tuple[float, int]] = []
    for column_index, header in enumerate(headers):
        if _semantic_header(header, "ads") is not None:
            continue
        values = [row[column_index].strip() for row in data_rows if column_index < len(row) and row[column_index].strip()]
        if not values:
            continue
        id_like_ratio = sum(_looks_like_ad_unit_id(value) for value in values) / len(values)
        if id_like_ratio < 0.6:
            continue
        unique_ratio = len(set(values)) / len(values)
        score = (id_like_ratio * 10) + unique_ratio
        candidates.append((score, column_index))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 1:
        return None
    return candidates[0][1]


def _unique_best_column(scores: list[tuple[float, int]], minimum: float) -> int | None:
    eligible = [(score, index) for score, index in scores if score >= minimum]
    if not eligible:
        return None
    eligible.sort(reverse=True)
    if len(eligible) > 1 and abs(eligible[0][0] - eligible[1][0]) < 0.001:
        return None
    return eligible[0][1]


def _working_value_score(key: str, value: str) -> float:
    value = value.strip()
    if not value:
        return 0
    score = 1.0
    if key == "Package name" and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*){1,}", value):
        score += 5
    elif key == "Firebase" and ("firebase" in value.casefold() or "/project/" in value):
        score += 5
    elif key == "App name" and not _looks_like_ad_unit_id(value) and "://" not in value:
        score += 1
    elif key in SECRET_LABELS | {"Facebook App ID"} and len(value) >= 6:
        score += 1
    return score


def _infer_working_columns(canonical: list[str], data_rows: list[list[str]]) -> None:
    key_index = canonical.index("Task Detail") if "Task Detail" in canonical else None
    if key_index is None:
        key_scores = []
        for index in range(len(canonical)):
            count = sum(
                _canonical_working_key(row[index]) is not None
                for row in data_rows
                if index < len(row) and row[index].strip()
            )
            key_scores.append((float(count), index))
        key_index = _unique_best_column(key_scores, minimum=2)
        if key_index is not None:
            canonical[key_index] = "Task Detail"

    if key_index is None or "Document" in canonical:
        return
    value_scores: list[tuple[float, int]] = []
    for index in range(len(canonical)):
        if index == key_index or canonical[index] in {"Task Detail", "Document"}:
            continue
        score = 0.0
        for row in data_rows:
            if key_index >= len(row) or index >= len(row):
                continue
            key = _canonical_working_key(row[key_index])
            if key:
                score += _working_value_score(key, row[index])
        value_scores.append((score, index))
    value_index = _unique_best_column(value_scores, minimum=2)
    if value_index is not None:
        canonical[value_index] = "Document"


def _looks_like_ad_type(value: str) -> bool:
    return _normalize_header(value) in _KNOWN_AD_TYPES


def _looks_like_placement_name(value: str) -> bool:
    value = value.strip()
    if value.upper() == "APP ID":
        return True
    lowered = value.casefold()
    return bool(re.fullmatch(r"[a-z][a-z0-9_.-]+", lowered)) and (
        "_" in lowered or lowered.startswith(("banner", "inter", "native", "open", "reward"))
    )


def _infer_ads_column(canonical: list[str], data_rows: list[list[str]], semantic: str, predicate: Any) -> None:
    if semantic in canonical:
        return
    scores: list[tuple[float, int]] = []
    for index in range(len(canonical)):
        if canonical[index] in {"id", "name", "Ads type", "Mô tả"}:
            continue
        values = [row[index].strip() for row in data_rows if index < len(row) and row[index].strip()]
        if not values:
            continue
        ratio = sum(bool(predicate(value)) for value in values) / len(values)
        scores.append((ratio, index))
    inferred = _unique_best_column(scores, minimum=0.6)
    if inferred is not None:
        canonical[inferred] = semantic


def _canonical_headers(headers: list[str], data_rows: list[list[str]], kind: str) -> list[str]:
    canonical: list[str] = []
    for index, header in enumerate(headers):
        semantic = _semantic_header(header, kind)
        if semantic is not None:
            canonical.append(semantic if semantic not in canonical else f"{semantic}_{index}")
        else:
            normalized = _normalize_header(header)
            canonical.append(normalized or f"column_{index}")

    if kind == "ads":
        inferred_index = _infer_id_column(headers, data_rows)
        if inferred_index is not None:
            canonical[inferred_index] = "id"
        _infer_ads_column(canonical, data_rows, "Ads type", _looks_like_ad_type)
        _infer_ads_column(canonical, data_rows, "name", _looks_like_placement_name)
    else:
        _infer_working_columns(canonical, data_rows)
    return canonical


def _required_headers(kind: str) -> tuple[str, ...]:
    return ("name", "Ads type", "id") if kind == "ads" else ("Task Detail", "Document")


def _find_header_mapping(rows: list[list[str]], kind: str) -> tuple[int, list[str]] | None:
    required = _required_headers(kind)
    for index, row in enumerate(rows[:50]):
        semantics = {_semantic_header(value, kind) for value in row}
        if all(field in semantics for field in required):
            return index, _canonical_headers(row, rows[index + 1 :], kind)
    for index, row in enumerate(rows[:50]):
        if sum(bool(value.strip()) for value in row) < 2:
            continue
        canonical = _canonical_headers(row, rows[index + 1 :], kind)
        if all(field in canonical for field in required):
            return index, canonical
    return None


def _rows(path: Path, kind: str) -> Iterable[tuple[int, dict[str, str]]]:
    delimiter, rows = _read_table(path)
    if not rows:
        return
    mapping = _find_header_mapping(rows, kind)
    if mapping is None:
        nonempty = [row for row in rows[:50] if any(value.strip() for value in row)]
        headers = max(nonempty, key=lambda row: sum(bool(value.strip()) for value in row), default=[])
        displayed = ", ".join(header.strip() or "<unnamed>" for header in headers) or "<none>"
        required = ", ".join(_required_headers(kind))
        raise ValueError(
            f"Could not map required {kind} CSV columns in {path}. "
            f"Detected delimiter {delimiter!r} and headers: {displayed}. Required semantics: {required}."
        )
    header_index, canonical = mapping
    data_rows = rows[header_index + 1 :]
    for row_number, values in enumerate(data_rows, start=header_index + 2):
        if not any(value.strip() for value in values):
            continue
        padded = values + [""] * max(0, len(canonical) - len(values))
        yield row_number, {header: padded[index] for index, header in enumerate(canonical)}


def _layout_hint(path: Path, kind: str) -> str:
    try:
        delimiter, rows = _read_table(path)
        mapping = _find_header_mapping(rows, kind)
        header_index = mapping[0] if mapping else 0
        headers = rows[header_index] if rows and header_index < len(rows) else []
        displayed = ", ".join(header.strip() or "<unnamed>" for header in headers)
        return f" Detected delimiter {delimiter!r} and headers: {displayed or '<none>'}."
    except (OSError, UnicodeError, csv.Error):
        return " Could not inspect the CSV layout."


def parse_ads_script(path: str | Path) -> AuditContract:
    path = Path(path)
    placements: dict[str, Placement] = {}
    app_id: str | None = None
    for row_number, row in _rows(path, "ads"):
        name = _value(row, "Name")
        identifier = _value(row, "ID")
        if name.upper() == "APP ID":
            app_id = identifier or None
        elif name and identifier and _value(row, "Ads type"):
            placements[name] = Placement(name, _value(row, "Ads type"), identifier, _value(row, "Mô tả", "Des", "Description"), row_number)
    if not placements:
        raise ValueError(
            f"No placement rows found in ADS Script: {path}. "
            "Expected recognizable columns for Name, Ads type, and an ad-unit ID; "
            "the file may use an unsupported layout or have no populated placement rows."
            f"{_layout_hint(path, 'ads')}"
        )
    return AuditContract(placements=placements, admob_app_id=app_id, source=str(path))


def parse_working_file(path: str | Path) -> ProjectChecklist:
    path = Path(path)
    values: dict[str, str] = {}
    for _, row in _rows(path, "working"):
        key = _value(row, "Task Detail")
        value = _value(row, "Document")
        if key and value:
            values[_canonical_working_key(key) or key] = value
    return ProjectChecklist(
        app_name=values.get("App name"),
        package_name=values.get("Package name"),
        firebase_project=_firebase_project(values.get("Firebase", "")),
        required_values={key: value for key, value in values.items() if key in SECRET_LABELS or key == "Facebook App ID"},
        source=str(path),
    )


def _firebase_project(value: str) -> str | None:
    match = re.search(r"/project/([^/?]+)", value)
    return match.group(1) if match else None


def redact_value(value: str | None) -> str:
    if not value:
        return "<missing>"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"<redacted:sha256:{digest}>"


def _files(root: Path, suffixes: set[str] | None = None) -> list[Path]:
    return [
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and not any(part in SKIP_DIRS for part in candidate.relative_to(root).parts) and (suffixes is None or candidate.suffix in suffixes)
    ]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _line_ref(root: Path, path: Path, token: str) -> str | None:
    for number, line in enumerate(_read(path).splitlines(), start=1):
        if token in line:
            return f"{path.relative_to(root)}:{number}"
    return str(path.relative_to(root))


def _location(root: Path, path: Path | None, token: str | None = None) -> str | None:
    if path is None:
        return None
    return _line_ref(root, path, token) if token else str(path.relative_to(root))


def _missing_tokens(text: str, tokens: Iterable[str]) -> list[str]:
    return [token for token in tokens if token not in text]


def _tokens_in_order(text: str, tokens: Iterable[str]) -> bool:
    offset = -1
    for token in tokens:
        found = text.find(token, offset + 1)
        if found < 0:
            return False
        offset = found
    return True


def _check_tokens(
    report: AuditReport,
    root: Path,
    rule_id: str,
    category: str,
    expected: str,
    text: str,
    tokens: Iterable[str],
    recommendation: str,
    path: Path | None = None,
) -> None:
    tokens = list(tokens)
    missing = _missing_tokens(text, tokens)
    if missing:
        report.findings.append(Finding.fail(rule_id, category, expected, f"missing: {', '.join(missing)}", recommendation, _location(root, path)))
    else:
        report.findings.append(Finding.pass_(rule_id, category, expected, "found", _location(root, path, tokens[0] if tokens else None)))


def _check_ordered_tokens(
    report: AuditReport,
    root: Path,
    rule_id: str,
    category: str,
    expected: str,
    text: str,
    tokens: Iterable[str],
    recommendation: str,
    path: Path | None = None,
) -> None:
    tokens = list(tokens)
    missing = _missing_tokens(text, tokens)
    if missing:
        report.findings.append(Finding.fail(rule_id, category, expected, f"missing: {', '.join(missing)}", recommendation, _location(root, path)))
    elif not _tokens_in_order(text, tokens):
        report.findings.append(Finding.fail(rule_id, category, expected, "tokens found but not in required order", recommendation, _location(root, path, tokens[0])))
    else:
        report.findings.append(Finding.pass_(rule_id, category, expected, "found in required order", _location(root, path, tokens[0])))


def _combined_text(paths: Iterable[Path]) -> str:
    return "\n".join(_read(path) for path in paths)


def _first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1) if match else None


def _config_data(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(_read(path))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and isinstance(parsed.get("ads"), dict):
        return parsed["ads"]
    return parsed if isinstance(parsed, dict) else None


def _check_equal(report: AuditReport, rule_id: str, category: str, expected: str | None, observed: str | None, recommendation: str, location: str | None = None, redact: bool = False) -> None:
    display_expected = redact_value(expected) if redact else (expected or "<not supplied>")
    display_observed = redact_value(observed) if redact else (observed or "<missing>")
    if expected and observed == expected:
        report.findings.append(Finding.pass_(rule_id, category, display_expected, display_observed, location))
    else:
        report.findings.append(Finding.fail(rule_id, category, display_expected, display_observed, recommendation, location))


def _release_config_path(root: Path, config_name: str = "ad_config.json") -> Path | None:
    """Resolve one release config path consistently for every config check."""
    canonical = root / "app" / "src" / "main" / "assets" / config_name
    if canonical.is_file():
        return canonical
    candidates = sorted(
        (path for path in _files(root, {".json"}) if path.name == config_name),
        key=lambda path: (len(path.relative_to(root).parts), str(path.relative_to(root))),
    )
    return candidates[0] if candidates else None


def _check_config(report: AuditReport, root: Path, contract: AuditContract, config_name: str, label: str) -> None:
    config_path = _release_config_path(root, config_name)
    if config_path is None:
        for placement in contract.placements.values():
            report.findings.append(Finding.fail(f"AD_CONFIG_{label}:{placement.name}", "ad_config", placement.ad_unit_id, "config file missing", f"Add `{config_name}` with `{placement.name}` and its contract ad unit ID."))
        return
    config = _config_data(config_path)
    if config is None:
        report.findings.append(Finding.fail(f"AD_CONFIG_{label}:FILE", "ad_config", "valid JSON", "invalid JSON", f"Fix JSON syntax in `{config_path.name}`.", str(config_path.relative_to(root))))
        return
    for placement in contract.placements.values():
        observed = config.get(placement.name)
        rule_id = f"AD_CONFIG_{label}:{placement.name}"
        if not isinstance(observed, dict):
            report.findings.append(Finding.fail(rule_id, "ad_config", placement.ad_unit_id, "key missing", f"Add `{placement.name}` using the ID from ADS Script row {placement.row}.", str(config_path.relative_to(root))))
            continue
        actual_id = str(observed.get("id", ""))
        location = _line_ref(root, config_path, f'"{placement.name}"')
        _check_equal(report, rule_id, "ad_config", placement.ad_unit_id, actual_id, f"Set `{placement.name}.id` to the exact ADS Script ID.", location)
        if "isEnable" not in observed:
            report.findings.append(Finding.fail(f"AD_CONFIG_{label}:ENABLE:{placement.name}", "ad_config", "isEnable field", "field missing", "Add explicit `isEnable` to this placement.", location))


def _load_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    """Parse the narrow, dependency-free YAML shape supplied by the template."""
    if path is None or not path.is_file():
        return {}
    placements: dict[str, dict[str, str]] = {}
    current: str | None = None
    for raw_line in _read(path).splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        placement_match = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", raw_line)
        field_match = re.match(r"^    ([A-Za-z_]+):\s*(.*?)\s*$", raw_line)
        if placement_match:
            current = placement_match.group(1)
            placements[current] = {}
        elif field_match and current:
            placements[current][field_match.group(1)] = field_match.group(2).strip("\"'")
    return placements


def _banner_evidence(source_paths: list[Path], key: str) -> tuple[Path, str] | None:
    """Find the screen that binds a specific banner placement.

    `AdsManager.loadBanner` is shared by every banner, so its presence proves
    nothing about one placement. The base binds a banner by naming the config
    key: `BannerConfig(AdRemoteConfig.banner_home, true)`. Match on the key.
    """
    patterns = (
        rf"BannerConfig\s*\([^)]*\b{re.escape(key)}\b",
        rf"loadBanner\s*\([^;]{{0,240}}?\b{re.escape(key)}\b",
        rf"\b{re.escape(key)}\b[^;\n]{{0,120}}?\bfr_banner\b",
    )
    for path in source_paths:
        text = _read(path)
        if key not in text:
            continue
        for pattern in patterns:
            if re.search(pattern, text, flags=re.S):
                return path, key
    return None


def _is_banner_placement(placement: "Placement") -> bool:
    return "banner" in placement.ad_type.casefold() or placement.name.casefold().startswith("banner")


def _check_flow(report: AuditReport, root: Path, contract: AuditContract, source_paths: list[Path], overrides: dict[str, dict[str, str]]) -> None:
    source = _combined_text(source_paths)
    # Call sites verified against the Infinity base project (see
    # references/base-code-reference.md). A placement marked optional is one the
    # base wires through AdsManager but leaves for the app to place on a screen;
    # a missing call there is NEEDS_MAPPING, not a failure.
    known = {
        "inter_splash": ("SplashActivity", "loadSplashInterstitialAds"),
        "open_resume": ("SplashActivity", "setAppResumeAdId"),
        "native_language_1": ("SplashActivity", "loadNativeLanguage"),
        "native_language_2": ("SplashActivity", "loadNativeLanguage"),
        "native_language_1_click": ("LanguageActivity", "loadNativeLanguageClick"),
        "native_language_2_click": ("LanguageActivity", "loadNativeLanguageClick"),
        "native_onboarding_1_1": ("LanguageActivity", "loadNativeOnboarding1"),
        "native_onboarding_2_1": ("LanguageActivity", "loadNativeOnboarding1"),
        "native_onboarding_1_4": ("OnBoardingActivity", "loadNativeOnboarding4"),
        "native_onboarding_2_4": ("OnBoardingActivity", "loadNativeOnboarding4"),
        "native_onboarding_fullscreen_1_3": ("OnBoardingActivity", "loadNativeOnboardingFull"),
        "native_onboarding_fullscreen_2_3": ("OnBoardingActivity", "loadNativeOnboardingFull"),
        "inter_onboarding": ("OnBoardingActivity", "showInterOnboarding"),
        "native_welcome": ("WelcomeActivity", "loadNativeWelcome"),
        "inter_welcome": ("WelcomeActivity", "showInterWelcome"),
        "inter_welcome_back": ("AppLifecycleObserver", "getShouldDisplayInterWelcomeBack"),
        "native_survey": ("SurveyActivity", "loadNativeSurvey"),
        "native_confirm_uninstall": ("ConfirmUninstallActivity", "loadNativeConfirmUninstall"),
        "banner_home": ("MainActivity", "banner_home"),
    }
    # Provided by AdsManager in the base; the screen that shows them is app-specific.
    optional_screen = {
        "native_home": ("MainActivity", "loadNativeHome"),
        "native_permission": ("AdsManager", "loadNativePermission"),
        "native_onboarding_fullscreen_1_4": ("AdsManager", "loadNativeOnboardingFull2"),
        "native_onboarding_fullscreen_2_4": ("AdsManager", "loadNativeOnboardingFull2"),
        "reward_example": ("AdsManager", "loadAndShowReward"),
    }
    for placement in contract.placements.values():
        rule_id = f"PLACEMENT_FLOW:{placement.name}"
        if _is_banner_placement(placement) and placement.name not in overrides:
            found = _banner_evidence(source_paths, placement.name)
            if found:
                path, key = found
                report.findings.append(Finding.pass_(rule_id, "placement_flow", f"a screen binds `{key}` to its banner container", f"found `{key}` bound in {path.name}", _line_ref(root, path, key)))
            else:
                report.findings.append(Finding.needs_mapping(rule_id, placement.description or f"a screen shows `{placement.name}`", f"`{placement.name}` is never bound to a banner container", f"Bind it on the screen that shows it — extend `BaseActivityWithBanner` and override `bannerConfig = BannerConfig(AdRemoteConfig.{placement.name}, ...)` with an `fr_banner` container — or map it in `ads-audit-overrides.yaml`."))
            continue
        mapping = known.get(placement.name)
        is_optional = False
        if mapping is None and placement.name in optional_screen:
            mapping, is_optional = optional_screen[placement.name], True
        override = overrides.get(placement.name)
        if override and override.get("class") and (override.get("show_call") or override.get("load_call")):
            mapping, is_optional = (override["class"], override.get("show_call") or override["load_call"]), False
        if mapping is None:
            report.findings.append(Finding.needs_mapping(rule_id, placement.description or "project-specific placement", "no approved class/event mapping", f"Add `{placement.name}` to `ads-audit-overrides.yaml` with class and required call/event evidence."))
            continue
        class_name, call = mapping
        class_files = [path for path in source_paths if path.name == f"{class_name}.kt" or path.name == f"{class_name}.java"]
        matching = next((path for path in class_files if call in _read(path)), None)
        if matching:
            report.findings.append(Finding.pass_(rule_id, "placement_flow", f"{class_name} calls {call}", f"found {call}", _line_ref(root, matching, call)))
        elif is_optional:
            report.findings.append(Finding.needs_mapping(rule_id, f"a screen loads {call}", f"{call} is not called from {class_name}", f"Point `{placement.name}` at the screen that shows it in `ads-audit-overrides.yaml`, or wire it through `AdsManager.{call}`."))
        elif class_files:
            report.findings.append(Finding.fail(rule_id, "placement_flow", f"{class_name} calls {call}", "call not found", f"Implement this placement through `AdsManager` at the configured lifecycle/event point.", str(class_files[0].relative_to(root))))
        else:
            report.findings.append(Finding.fail(rule_id, "placement_flow", f"{class_name} calls {call}", "screen class not found", "Add an approved override mapping if the partner uses another class name; otherwise restore the required screen flow."))
        if placement.ad_type.lower().strip() == "interstitial" and placement.name != "inter_welcome_back":
            report.findings.append(Finding.needs_runtime(f"RUNTIME:{placement.name}", "show only at the configured user transition", "static source cannot prove every runtime event", f"Run the placement test case for `{placement.name}` and attach video/log proof."))


def _source_by_class(source_paths: list[Path], class_name: str) -> Path | None:
    return next((path for path in source_paths if path.name in {f"{class_name}.kt", f"{class_name}.java"}), None)


PRIMARY_SCREEN_TOKENS = ("splash", "language", "onboarding", "home", "welcome")


def _simple_class_name(value: str) -> str:
    return value.rsplit(".", 1)[-1]


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _primary_screen_for_fragment(class_name: str) -> str | None:
    simple_name = _simple_class_name(class_name)
    normalized = _normalized_name(simple_name)
    if not normalized.endswith("fragment"):
        return None
    return next((token for token in PRIMARY_SCREEN_TOKENS if token in normalized), None)


def _manifest_activity_names(manifests: list[Path]) -> set[str]:
    """Simple class names of every `<activity>` the manifests declare."""
    names: set[str] = set()
    for path in manifests:
        for class_name in re.findall(r'<activity\b[^>]*(?:android:)?name\s*=\s*["\']([^"\']+)["\']', _read(path)):
            names.add(_simple_class_name(class_name))
    return names


def _primary_activity_names(activity_names: Iterable[str]) -> list[str]:
    return sorted(
        name for name in activity_names
        if any(token in _normalized_name(name) for token in PRIMARY_SCREEN_TOKENS)
    )


def _check_screen_architecture(report: AuditReport, root: Path, manifests: list[Path]) -> None:
    """Tell a multi-Activity journey apart from a single-Activity app.

    The base gives Splash, Language, Onboarding, Home, and Welcome an Activity
    each, because every ad gate — the AppOpen exclusions, the interstitial
    interval, the per-screen native observers — is keyed to an Activity
    lifecycle. An app that routes the whole journey through one Activity breaks
    those gates even when it declares no `*Fragment` class for
    `_check_primary_screen_activities` to catch, which is the case for a
    Compose or nav-graph app whose destinations are not named after screens.
    """
    activity_names = _manifest_activity_names(manifests)
    primary = _primary_activity_names(activity_names)
    location = str(manifests[0].relative_to(root)) if manifests else None
    observed = f"{len(activity_names)} Activity declaration(s), {len(primary)} on the ads journey"
    if primary:
        observed += f": {', '.join(primary)}"
    expected = "a separate Activity per primary screen (Splash, Language, Onboarding, Home, Welcome)"
    if len(primary) >= 2:
        report.findings.append(Finding.pass_("ARCH_SCREEN_ARCHITECTURE", "architecture", expected, observed, location))
    else:
        report.findings.append(Finding.fail(
            "ARCH_SCREEN_ARCHITECTURE",
            "architecture",
            expected,
            f"single-Activity architecture: {observed}",
            "Split the ads journey into separate Activities as the Infinity base does, and declare each one in AndroidManifest.xml.",
            location,
        ))


def _check_language_single_activity(report: AuditReport, root: Path, manifests: list[Path]) -> None:
    """Language is exactly one Activity in the base, never a split screen pair.

    `LanguageActivity` owns both the language list and the language-click native
    by swapping observers between `nativeLanguageAdLive` and
    `nativeLanguageClickAdLive` — the two are mutually exclusive. Splitting that
    across two Activities loses the swap, so both natives can render and the
    click native is charged against the wrong screen.
    """
    activities = sorted(name for name in _manifest_activity_names(manifests) if "language" in _normalized_name(name))
    location = str(manifests[0].relative_to(root)) if manifests else None
    expected = "exactly one Language Activity, as in the base"
    if len(activities) == 1:
        report.findings.append(Finding.pass_("ARCH_LANGUAGE_SINGLE_ACTIVITY", "architecture", expected, activities[0], location))
    elif not activities:
        report.findings.append(Finding.fail(
            "ARCH_LANGUAGE_SINGLE_ACTIVITY",
            "architecture",
            expected,
            "no Activity for the Language screen is declared in the manifest",
            "Add a single `LanguageActivity` and declare it in AndroidManifest.xml, following the Infinity base.",
            location,
        ))
    else:
        report.findings.append(Finding.fail(
            "ARCH_LANGUAGE_SINGLE_ACTIVITY",
            "architecture",
            expected,
            f"Language is split across {len(activities)} Activities: {', '.join(activities)}",
            "Merge them into one `LanguageActivity` that swaps between the nativeLanguageAdLive and nativeLanguageClickAdLive observers, as the base does.",
            location,
        ))


def _check_primary_screen_activities(
    report: AuditReport,
    root: Path,
    manifests: list[Path],
    source_paths: list[Path],
    navigation_paths: list[Path],
) -> None:
    """Reject a single-Activity primary ad journey implemented as screen fragments."""
    fragments: dict[str, tuple[str, str | None]] = {}
    for path in source_paths:
        screen = _primary_screen_for_fragment(path.stem)
        if screen:
            fragments[_simple_class_name(path.stem)] = (screen, str(path.relative_to(root)))
    for path in navigation_paths:
        for class_name in re.findall(r'(?:android:)?name\s*=\s*["\']([^"\']+Fragment)["\']', _read(path)):
            screen = _primary_screen_for_fragment(class_name)
            if screen:
                fragments[_simple_class_name(class_name)] = (screen, str(path.relative_to(root)))

    activity_names = _manifest_activity_names(manifests)

    if not fragments:
        report.findings.append(Finding.pass_(
            "ARCH_PRIMARY_SCREENS_ACTIVITY",
            "architecture",
            "primary ads-journey screens use separate Activities",
            "no primary-screen Fragment navigation found",
        ))
        return

    missing: list[tuple[str, str | None]] = []
    for fragment_name, (screen, location) in fragments.items():
        has_matching_activity = any(
            _normalized_name(activity_name).endswith("activity") and screen in _normalized_name(activity_name)
            for activity_name in activity_names
        )
        if not has_matching_activity:
            missing.append((fragment_name, location))

    observed = ", ".join(name for name, _ in missing) if missing else ", ".join(fragments)
    locations = sorted({location for _, location in missing if location})
    if missing:
        report.findings.append(Finding.fail(
            "ARCH_PRIMARY_SCREENS_ACTIVITY",
            "architecture",
            "separate Activity classes for Splash, Language, Onboarding, Home, and Welcome primary screens",
            f"single-Activity/Fragment screen flow detected: {observed}",
            "Move the listed primary screens from Fragment navigation to separate Activities following the Infinity base flow.",
            "; ".join(locations) or None,
        ))
    else:
        report.findings.append(Finding.pass_(
            "ARCH_PRIMARY_SCREENS_ACTIVITY",
            "architecture",
            "primary ads-journey screens use separate Activities",
            f"matching Activity declarations found for: {observed}",
        ))


def _check_inter_welcome_back(report: AuditReport, root: Path, contract: AuditContract, source_paths: list[Path], manager_text: str, global_text: str, overrides: dict[str, dict[str, str]]) -> None:
    if "inter_welcome_back" not in contract.placements:
        return
    override = overrides.get("inter_welcome_back", {})
    observer_class = override.get("observer_class", "AppLifecycleObserver")
    welcome_class = override.get("welcome_class", "WelcomeActivity")
    observer_path = _source_by_class(source_paths, observer_class)
    welcome_path = _source_by_class(source_paths, welcome_class)
    observer_text = _read(observer_path) if observer_path else ""
    welcome_text = _read(welcome_path) if welcome_path else ""
    observer_tokens = (
        "ResumeAdsEntryRule.shouldShowWelcomeOnResume",
        "getShouldDisplayInterWelcomeBack",
        "startWelcomeActivity",
    )
    missing_observer = [token for token in observer_tokens if token not in observer_text]
    observer_location = str(observer_path.relative_to(root)) if observer_path else None
    if missing_observer:
        report.findings.append(Finding.fail("FLOW_INTER_WELCOME_BACK_OBSERVER", "placement_flow", "resume observer checks Welcome rule, UA gate, then routes to Welcome", f"missing: {', '.join(missing_observer)}", "Implement the resume chain: `ResumeAdsEntryRule.shouldShowWelcomeOnResume()` + `getShouldDisplayInterWelcomeBack(config.enableUaCheck)` + route to WelcomeActivity.", observer_location))
    else:
        report.findings.append(Finding.pass_("FLOW_INTER_WELCOME_BACK_OBSERVER", "placement_flow", "resume observer checks Welcome rule, UA gate, then routes to Welcome", "found", _line_ref(root, observer_path, "getShouldDisplayInterWelcomeBack")))
    welcome_tokens = ("AdsManager.loadInterWelcome", "AdsManager.showInterWelcome")
    missing_welcome = [token for token in welcome_tokens if token not in welcome_text]
    welcome_location = str(welcome_path.relative_to(root)) if welcome_path else None
    if missing_welcome:
        report.findings.append(Finding.fail("FLOW_INTER_WELCOME_BACK_LOAD_SHOW", "placement_flow", "Welcome screen loads and shows the Welcome interstitial through AdsManager", f"missing: {', '.join(missing_welcome)}", "Load `inter_welcome_back` when Welcome starts and show it only from the configured Welcome CTA; finish/continue in the close/fail callback.", welcome_location))
    else:
        report.findings.append(Finding.pass_("FLOW_INTER_WELCOME_BACK_LOAD_SHOW", "placement_flow", "Welcome screen loads and shows the Welcome interstitial through AdsManager", "found", _line_ref(root, welcome_path, "AdsManager.loadInterWelcome")))
    required_manager_tokens = ("fun loadInterWelcome", "fun showInterWelcome", ".isEnable", "AppPurchase.getInstance().isPurchased")
    missing_manager = [token for token in required_manager_tokens if token not in manager_text]
    if missing_manager:
        report.findings.append(Finding.fail("FLOW_INTER_WELCOME_BACK_MANAGER", "placement_flow", "AdsManager load/show applies config enable and purchase gates", f"missing: {', '.join(missing_manager)}", "Implement the Welcome interstitial inside AdsManager with config enable and purchase checks."))
    else:
        report.findings.append(Finding.pass_("FLOW_INTER_WELCOME_BACK_MANAGER", "placement_flow", "AdsManager load/show applies config enable and purchase gates", "found"))
    registration_token = f"addObserver({observer_class}"
    if registration_token in global_text:
        report.findings.append(Finding.pass_("FLOW_INTER_WELCOME_BACK_REGISTRATION", "placement_flow", f"Application registers {observer_class} with ProcessLifecycleOwner", "found"))
    else:
        report.findings.append(Finding.fail("FLOW_INTER_WELCOME_BACK_REGISTRATION", "placement_flow", f"Application registers {observer_class} with ProcessLifecycleOwner", "registration not found", f"Register `{observer_class}` using `ProcessLifecycleOwner.get().lifecycle.addObserver(...)` in Application.onCreate()."))
    report.findings.append(Finding.needs_runtime("RUNTIME:inter_welcome_back", "resume app from background/recents, route to Welcome, tap CTA, close/fail interstitial, return to previous screen", "static analysis cannot prove lifecycle timing, ad readiness, or no duplicate App Open ad", "Record this journey with device logs/video after static checks pass."))


def _check_global_base_rules(report: AuditReport, root: Path, global_app: Path | None, global_text: str, gradle_text: str) -> None:
    _check_ordered_tokens(
        report,
        root,
        "ARCH_GLOBAL_INIT_ORDER",
        "architecture",
        "GlobalApp initializes MobileAds, DevConfig, local AdRemoteConfig, then ERainAd in that order",
        global_text,
        ("MobileAds.initialize", "DevConfig.init", "AdRemoteConfig.initializeFromAssets", "ERainAd.getInstance().init"),
        "Keep the base order in GlobalApp.onCreate(): MobileAds.initialize -> DevConfig.init -> initAdRemoteConfig/AdRemoteConfig.initializeFromAssets -> initAds/ERainAd.init.",
        global_app,
    )
    _check_tokens(
        report,
        root,
        "ARCH_DEV_CONFIG_INIT",
        "architecture",
        "DevConfig.init receives BuildConfig ad library version fields",
        global_text,
        ("DevConfig.init", "BuildConfig.ERAIN_STUDIO_VERSION", "BuildConfig.PLAY_SERVICES_ADS_VERSION", "BuildConfig.GDPR_MODULE_VERSION"),
        "Call DevConfig.init early from GlobalApp and pass the three BuildConfig version fields.",
        global_app,
    )
    _check_tokens(
        report,
        root,
        "ARCH_DEV_CONFIG_BUILD_FIELDS",
        "architecture",
        "debug/release buildConfigField values exist for ERain Studio, Play Services Ads, and GDPR versions",
        gradle_text,
        ("ERAIN_STUDIO_VERSION", "PLAY_SERVICES_ADS_VERSION", "GDPR_MODULE_VERSION"),
        "Declare all three buildConfigField values in app/build.gradle for debug and release.",
    )
    _check_tokens(
        report,
        root,
        "ARCH_ADS_CONFIG_FIELDS",
        "architecture",
        "ERainAdConfig receives Adjust, Facebook, TikTok, interval, and resume id fields before ERainAd.init",
        global_text,
        ("AdjustConfig", "facebookClientToken", "adjustTokenTiktok", "intervalInterstitialAd", "idAdResume", "ERainAd.getInstance().init"),
        "Preserve the base GlobalApp.initAds fields before ERainAd.getInstance().init(...).",
        global_app,
    )
    _check_tokens(
        report,
        root,
        "ARCH_APP_OPEN_EXCLUSIONS",
        "architecture",
        "AppOpen resume is disabled on Splash, Language, and Onboarding primary flow screens",
        global_text,
        ("disableAppResumeWithActivity(SplashActivity::class.java", "disableAppResumeWithActivity(LanguageActivity::class.java", "disableAppResumeWithActivity(OnBoardingActivity::class.java"),
        "Disable AppOpen resume on SplashActivity, LanguageActivity, and OnBoardingActivity in GlobalApp.initAds().",
        global_app,
    )


def _check_screen_flow_rules(report: AuditReport, root: Path, source_paths: list[Path], contract: AuditContract) -> None:
    splash = _source_by_class(source_paths, "SplashActivity")
    splash_text = _read(splash) if splash else ""
    _check_tokens(
        report,
        root,
        "FLOW_SPLASH_REMOTE_CONFIG",
        "placement_flow",
        "Splash initializes RemoteConfig, applies AdRemoteConfig from RemoteConfigUtils, and falls back after timeout",
        splash_text,
        ("RemoteConfigUtils.init", "loadingRemoteConfig", "AdRemoteConfig.initialize", "RemoteConfigUtils.getAdRemoteConfig"),
        "Keep SplashActivity consent/remote-config loading and apply AdRemoteConfig.initialize(this, RemoteConfigUtils.getAdRemoteConfig()).",
        splash,
    )
    _check_tokens(
        report,
        root,
        "FLOW_SPLASH_INTER_PRELOAD_LANGUAGE",
        "placement_flow",
        "Splash gates inter_splash by config/network, loads splash interstitial, preloads native language onAdLoaded, and navigates onNextAction",
        splash_text,
        ("AdRemoteConfig.inter_splash.isEnable", "isNetwork", "loadSplashInterstitialAds", "onAdLoaded", "loadNativeLanguage", "onNextAction", "moveActivity"),
        "Preserve Splash interstitial load/show and preload native language only from the splash loaded callback.",
        splash,
    )
    _check_tokens(
        report,
        root,
        "FLOW_SPLASH_OPEN_RESUME",
        "placement_flow",
        "Splash enables or disables open_resume through ResumeAdsEntryRule and AppOpenManager",
        splash_text,
        ("ResumeAdsEntryRule.shouldEnableOpenResume", "setAppResumeAdId", "AdRemoteConfig.open_resume.id", "enableAppResume", "disableAppResume"),
        "Configure AppOpen resume in Splash after AdRemoteConfig is initialized.",
        splash,
    )

    # The base defines banner_splash but wires it to no screen. Partner apps do
    # show it, so a contract that lists the key and a Splash that never binds it
    # is a defect rather than a mapping gap.
    if "banner_splash" in contract.placements:
        expected = "SplashActivity binds `banner_splash` to its banner container"
        evidence = _banner_evidence([splash] if splash else [], "banner_splash")
        if evidence:
            path, key = evidence
            report.findings.append(Finding.pass_(
                "FLOW_SPLASH_BANNER", "placement_flow", expected, f"found `{key}` bound in {path.name}",
                _line_ref(root, path, key),
            ))
        else:
            report.findings.append(Finding.fail(
                "FLOW_SPLASH_BANNER",
                "placement_flow",
                expected,
                "`banner_splash` is never bound on SplashActivity",
                "Bind it on Splash: extend `BaseActivityWithBanner` and override `bannerConfig = BannerConfig(AdRemoteConfig.banner_splash, ...)` with an `fr_banner` container.",
                _location(root, splash),
            ))

    language = _source_by_class(source_paths, "LanguageActivity")
    language_text = _read(language) if language else ""
    _check_tokens(
        report,
        root,
        "FLOW_LANGUAGE_DEV_SETTING",
        "placement_flow",
        "Language screen exposes DevSetting through tvTitle admin ads toggle",
        language_text,
        ("tvTitle.setOnAdminAdToggleListener", "Routes.startSplashActivity"),
        "Keep mBinding.tvTitle.setOnAdminAdToggleListener() so QA can open DevConfig/ads testing.",
        language,
    )
    _check_tokens(
        report,
        root,
        "FLOW_LANGUAGE_PRELOAD_AND_RENDER",
        "placement_flow",
        "Language loads click native, preloads onboarding page 1, observes language LiveData, renders non-null ads, and hides null/offline ads",
        language_text,
        ("postDelayed", "100L", "loadNativeLanguageClick", "loadNativeOnboarding1", "nativeLanguageAdLive.observe", "nativeLanguageClickAdLive.observe", "populateNativeAdView", "flAds.goneView"),
        "Preserve Language native/click rendering and onboarding page-1 preload after the short base delay.",
        language,
    )
    _check_tokens(
        report,
        root,
        "FLOW_LANGUAGE_OBSERVER_SWAP",
        "placement_flow",
        "Language removes the other native observer when swapping between the two",
        language_text,
        ("AdsManager.nativeLanguageAdLive.removeObservers", "AdsManager.nativeLanguageClickAdLive.removeObservers"),
        "Call removeObservers on the observer you are leaving before observing the other one; both left active makes the ad container flicker between two ads.",
        language,
    )

    onboarding = _source_by_class(source_paths, "OnBoardingActivity")
    onboarding_text = _read(onboarding) if onboarding else ""
    _check_tokens(
        report,
        root,
        "FLOW_ONBOARDING_PRELOAD_AND_SHOW",
        "placement_flow",
        "Onboarding preloads native page 4, native full, inter_onboarding, widget shortcut gate, and shows inter before Main",
        onboarding_text,
        ("postDelayed", "100L", "loadNativeOnboarding4", "loadNativeOnboardingFull", "loadInterOnboarding", "getShouldDisplayWidgetUninstall", "getShouldDisplayNativeOnboardingFull1", "showInterOnboarding", "Routes.startMainActivity"),
        "Keep OnBoardingActivity preload timing, native full/widget gates, and final interstitial callback navigation.",
        onboarding,
    )

    onboarding_page = _source_by_class(source_paths, "OnboardingPageFragment")
    onboarding_page_text = _read(onboarding_page) if onboarding_page else ""
    _check_tokens(
        report,
        root,
        "FLOW_ONBOARDING_PAGE_RENDERING",
        "placement_flow",
        "Onboarding page fragment maps page flags to AdsManager LiveData and renders/hides native ads",
        onboarding_page_text,
        ("nativeOnboarding1AdLive", "nativeOnboarding4AdLive", "nativeAdOnBoardingFullLive", "observe", "renderAd", "populateNativeAdView"),
        "Keep OnboardingPageFragment LiveData mapping for page 1, page 4, and fullscreen native ads.",
        onboarding_page,
    )

    # Only meaningful once the fragment exists and observes something; a missing
    # fragment or a missing observe call is already FLOW_ONBOARDING_PAGE_RENDERING.
    owners = _OBSERVE_OWNER.findall(onboarding_page_text) if onboarding_page else []
    if owners:
        wrong = sorted({owner for owner in owners if owner != "viewLifecycleOwner"})
        if wrong:
            report.findings.append(Finding.fail(
                "FLOW_ONBOARDING_PAGE_LIFECYCLE",
                "placement_flow",
                "onboarding page observes its ad LiveData with viewLifecycleOwner",
                f"observes with: {', '.join(wrong)}",
                "Observe with `viewLifecycleOwner`; the fragment lifecycle leaks observers as ViewPager2 recycles pages.",
                _line_ref(root, onboarding_page, ".observe("),
            ))
        else:
            report.findings.append(Finding.pass_(
                "FLOW_ONBOARDING_PAGE_LIFECYCLE",
                "placement_flow",
                "onboarding page observes its ad LiveData with viewLifecycleOwner",
                "found",
                _line_ref(root, onboarding_page, "observe("),
            ))

    resume_rule = _source_by_class(source_paths, "ResumeAdsEntryRule")
    resume_rule_text = _read(resume_rule) if resume_rule else ""
    observer = _source_by_class(source_paths, "AppLifecycleObserver")
    observer_text = _read(observer) if observer else ""
    _check_tokens(
        report,
        root,
        "FLOW_RESUME_RULE",
        "placement_flow",
        "Resume rule selects open_resume or welcome mode and observer blocks disabled screens before routing Welcome",
        resume_rule_text + "\n" + observer_text,
        ("open_resume.isEnable", "native_welcome.isEnable", "inter_welcome.isEnable", "shouldEnableOpenResume", "shouldShowWelcomeOnResume", "listActivityDisableResume", "isInterstitialShowing", "getShouldDisplayInterWelcomeBack", "Routes.startWelcomeActivity"),
        "Preserve ResumeAdsEntryRule plus AppLifecycleObserver gating before WelcomeActivity routing.",
        observer or resume_rule,
    )

    welcome = _source_by_class(source_paths, "WelcomeActivity")
    welcome_text = _read(welcome) if welcome else ""
    _check_tokens(
        report,
        root,
        "FLOW_WELCOME_NATIVE_AND_INTER",
        "placement_flow",
        "Welcome loads native and inter on start, observes native LiveData, renders/hides native, and shows inter on CTA before finish",
        welcome_text,
        ("loadNativeWelcome", "loadInterWelcome", "nativeWelcomeAdLive.observe", "renderWelcomeAd", "populateNativeAdView", "showInterWelcome", "finish"),
        "Keep WelcomeActivity load/show chain through AdsManager and hide native container on null/offline state.",
        welcome,
    )

    banner = _source_by_class(source_paths, "BaseActivityWithBanner")
    banner_text = _read(banner) if banner else ""
    _check_tokens(
        report,
        root,
        "ARCH_BANNER_BASE_RELOAD",
        "architecture",
        "BaseActivityWithBanner loads banner onCreate, reloads onResume by reloadIntervalSeconds, and gates isEnable/purchase/container",
        banner_text,
        ("BannerConfig", "loadBanner", "reloadBannerIfNeeded", "reloadIntervalSeconds", "postDelayed", "shouldShowBanner", "AppPurchase.getInstance().isPurchased", "AdsManager.loadBanner"),
        "Use BaseActivityWithBanner for banner screens and preserve reloadIntervalSeconds handling.",
        banner,
    )


def _check_ads_manager_base_rules(report: AuditReport, root: Path, manager_paths: list[Path], manager_text: str, resume_text: str = "") -> None:
    manager_path = manager_paths[0] if manager_paths else None
    _check_tokens(
        report,
        root,
        "ARCH_ADS_MANAGER_NATIVE_GATES",
        "architecture",
        "Native loads use one central helper with isEnable, purchase, network, shouldDisplay, load callback, and null fallback",
        manager_text,
        ("loadNativeInternal", "config.isEnable", "AppPurchase.getInstance().isPurchased", "isNetworkAvailable", "shouldDisplay", "loadNativeAdResultCallback", "liveData.postValue(null)"),
        "Centralize native load logic in AdsManager.loadNativeInternal with enable, purchase, network, shouldDisplay, and null fallback gates.",
        manager_path,
    )
    required_ua_methods = (
        "getShouldDisplayNativeOnboardingNormal2",
        "getShouldDisplayNativeOnboardingFull1",
        "getShouldDisplayNativeHome",
        "getShouldDisplayNativeWelcomeBack",
        "getShouldDisplayInterOnboarding",
        "getShouldDisplayInterWelcomeBack",
    )
    # The base calls getShouldDisplayInterWelcomeBack from AppLifecycleObserver,
    # not from AdsManager, so the resume/observer sources count as evidence too.
    missing_ua = _missing_tokens(manager_text + "\n" + resume_text, required_ua_methods)
    hardcoded = re.findall(r"getShouldDisplay[A-Za-z0-9_]*\(\s*(?:true|false)\s*\)", manager_text + "\n" + resume_text)
    if missing_ua or hardcoded:
        observed = []
        if missing_ua:
            observed.append(f"missing: {', '.join(missing_ua)}")
        if hardcoded:
            observed.append(f"hard-coded UA args: {', '.join(sorted(set(hardcoded)))}")
        report.findings.append(Finding.fail(
            "ARCH_ADS_MANAGER_UA_GATES",
            "architecture",
            "mandatory getShouldDisplay* gates use the placement's config.enableUaCheck",
            "; ".join(observed),
            "Use the correct ERainAd.getShouldDisplay*(config.enableUaCheck) gate for each sensitive placement; do not hard-code true/false.",
            _location(root, manager_path),
        ))
    else:
        report.findings.append(Finding.pass_(
            "ARCH_ADS_MANAGER_UA_GATES",
            "architecture",
            "mandatory getShouldDisplay* gates use the placement's config.enableUaCheck",
            "found",
            _location(root, manager_path, "getShouldDisplay"),
        ))
    _check_tokens(
        report,
        root,
        "ARCH_ADS_MANAGER_INTER_GATES",
        "architecture",
        "Interstitial onboarding/welcome load/show uses config enable, purchase, SDK gate, getInterstitialAds, forceShowInterstitial, and onNextAction callback",
        manager_text,
        ("loadInterOnboarding", "showInterOnboarding", "loadInterWelcome", "showInterWelcome", "config.isEnable", "AppPurchase.getInstance().isPurchased", "getInterstitialAds", "forceShowInterstitial", "onNextAction"),
        "Keep interstitial load/show inside AdsManager with config, purchase, UA gate, ready check, and close/fail callback continuation.",
        manager_path,
    )
    _check_tokens(
        report,
        root,
        "ARCH_ADS_MANAGER_BANNER",
        "architecture",
        "Banner loads are centralized in AdsManager and support normal/collapsible variants with disabled fallback",
        manager_text,
        ("fun loadBanner", "adUnitConfig.isEnable", "loadCollapsibleBanner", "loadBanner", "frAds.goneView"),
        "Load banners only through AdsManager.loadBanner and preserve normal/collapsible disabled-state handling.",
        manager_path,
    )


def _release_config_keys(root: Path) -> tuple[set[str], str | None] | None:
    """Return the release config's placement keys and its location, or None."""
    config_path = _release_config_path(root)
    if config_path is None:
        return None
    config = _config_data(config_path)
    if config is None:
        return None
    return set(config), str(config_path.relative_to(root))


def _check_base_key_coverage(report: AuditReport, root: Path, base_keys: tuple[str, ...]) -> None:
    """Compare the app's release placement keys against the base's own key list."""
    expected = f"all {len(base_keys)} base placement keys present"
    found = _release_config_keys(root)
    if found is None:
        report.findings.append(Finding.fail(
            "BASE_KEY_COVERAGE",
            "ad_config",
            expected,
            "ad_config.json is missing or not valid JSON",
            "Add `app/src/main/assets/ad_config.json` carrying the base placement keys.",
        ))
        return
    keys, location = found
    missing = [key for key in base_keys if key not in keys]
    extra = sorted(key for key in keys if key not in base_keys)
    if missing:
        report.findings.append(Finding.fail(
            "BASE_KEY_COVERAGE",
            "ad_config",
            expected,
            f"missing {len(missing)}: {', '.join(missing)}",
            "Copy the missing keys from the base `ad_config.json` and set this app's own ad unit IDs.",
            location,
        ))
    else:
        report.findings.append(Finding.pass_("BASE_KEY_COVERAGE", "ad_config", expected, "found", location))
    if extra:
        # An extra key is not wrong on its own: partner apps legitimately add
        # placements, provided the architecture still follows the base pattern.
        report.findings.append(Finding.needs_mapping(
            "BASE_KEY_EXTRA",
            "placement keys defined by the base project",
            f"{len(extra)} extra: {', '.join(extra)}",
            "Confirm each extra placement is Infinity-approved and follows the base pattern, then map it in `ads-audit-overrides.yaml`.",
            location,
        ))


def _release_admob_app_id(gradle_text: str) -> str | None:
    """Read the AdMob app id from the release build type only.

    Debug deliberately carries Google's public test app id
    (`ca-app-pub-3940256099942544~3347511713`), so matching the first id in the
    file reports a failure against a value that is supposed to differ.
    """
    release = re.search(r"\brelease\s*\{", gradle_text)
    if release:
        depth, index = 0, release.end() - 1
        while index < len(gradle_text):
            char = gradle_text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        block = gradle_text[release.end():index]
        found = _first_match(r'app_id\s*[:=]\s*["\'](ca-app-pub-[^"\']+)', block)
        if found:
            return found
    return _first_match(r'app_id\s*[:=]\s*["\'](ca-app-pub-[^"\']+)', gradle_text)


def inspect_project(root: str | Path, contract: AuditContract, checklist: ProjectChecklist, overrides_path: str | Path | None = None, base_project: str | Path | None = None) -> AuditReport:
    root = Path(root).resolve()
    report = AuditReport(str(root), contract, checklist)
    gradle_paths = [path for path in _files(root, {".gradle", ".kts"}) if path.name.startswith("build.gradle")]
    xml_paths = _files(root, {".xml"})
    manifests = [path for path in xml_paths if path.name == "AndroidManifest.xml"]
    navigation_paths = [path for path in xml_paths if "navigation" in path.relative_to(root).parts]
    source_paths = _files(root, SOURCE_SUFFIXES)
    all_text_paths = gradle_paths + manifests + _files(root, {".xml", ".kt", ".java", ".properties"})
    gradle_text = _combined_text(gradle_paths)
    manifest_text = _combined_text(manifests)
    package = _first_match(r'applicationId\s*[=(]?\s*["\']([^"\']+)', gradle_text) or _first_match(r'namespace\s*[=(]?\s*["\']([^"\']+)', gradle_text)
    _check_equal(report, "APP_PACKAGE", "identity", checklist.package_name, package, "Set `applicationId` and `namespace` to the package name in the working checklist.")
    app_id = _release_admob_app_id(gradle_text)
    _check_equal(report, "ADMOB_APP_ID", "identity", contract.admob_app_id, app_id, "Set the AdMob manifest placeholder to the ADS Script APP ID.")
    if "com.google.android.gms.ads.APPLICATION_ID" not in manifest_text:
        report.findings.append(Finding.fail("ADMOB_MANIFEST_META", "identity", "AdMob APPLICATION_ID meta-data", "missing", "Add the Google Mobile Ads APPLICATION_ID meta-data entry to AndroidManifest.xml."))
    string_paths = [path for path in all_text_paths if path.name == "strings.xml"]
    string_paths.sort(key=lambda path: (path.parent.name != "values", str(path)))
    app_name = None
    for string_path in string_paths:
        match = re.search(r'<string\s+name=["\']app_name["\'][^>]*>([^<]+)', _read(string_path), flags=re.MULTILINE)
        if match:
            app_name = unescape(match.group(1).strip())
            break
    _check_equal(report, "APP_NAME", "identity", checklist.app_name, app_name, "Set `app_name` to the working checklist value.")
    _check_config(report, root, contract, "ad_config.json", "RELEASE")
    _check_base_key_coverage(report, root, base_placement_keys(base_project))
    searchable = _combined_text(all_text_paths)
    for key, value in checklist.required_values.items():
        _check_equal(report, f"TOKEN:{key}", "token", value, value if value and value in searchable else None, f"Add the configured {key} using the approved Android resource/build configuration.", redact=key in SECRET_LABELS)
    firebase_files = [path for path in _files(root, {".json"}) if path.name == "google-services.json"]
    firebase_text = _combined_text(firebase_files)
    firebase_found = _first_match(r'["\']project_id["\']\s*:\s*["\']([^"\']+)', firebase_text)
    _check_equal(report, "FIREBASE_PROJECT", "service", checklist.firebase_project, firebase_found, "Add the `google-services.json` for the Firebase project in the working checklist.")
    global_app = next((path for path in source_paths if path.name in {"GlobalApp.kt", "GlobalApp.java"}), None)
    global_text = _read(global_app) if global_app else ""
    _check_global_base_rules(report, root, global_app, global_text, gradle_text)
    for rule_id, token, fix in (
        ("ARCH_MOBILE_ADS_INIT", "MobileAds.initialize", "Initialize Mobile Ads early in the Application."),
        ("ARCH_REMOTE_CONFIG_INIT", "AdRemoteConfig.initializeFromAssets", "Initialize asset config before ad SDK setup."),
        ("ARCH_ERAIN_INIT", "ERainAd.getInstance().init", "Initialize ERainAd from the Application."),
    ):
        if token in global_text:
            report.findings.append(Finding.pass_(rule_id, "architecture", token, "found", _line_ref(root, global_app, token)))
        else:
            report.findings.append(Finding.fail(rule_id, "architecture", token, "not found in Application", fix, str(global_app.relative_to(root)) if global_app else None))
    manager_paths = [path for path in source_paths if path.name in {"AdsManager.kt", "AdsManager.java"}]
    if manager_paths:
        report.findings.append(Finding.pass_("ARCH_ADS_MANAGER", "architecture", "central AdsManager", "found", str(manager_paths[0].relative_to(root))))
    else:
        report.findings.append(Finding.fail("ARCH_ADS_MANAGER", "architecture", "central AdsManager", "not found", "Centralize placement load/show logic in AdsManager."))
    manager_text = _combined_text(manager_paths)
    resume_paths = [path for path in source_paths if path.name in {
        "AppLifecycleObserver.kt", "AppLifecycleObserver.java",
        "ResumeAdsEntryRule.kt", "ResumeAdsEntryRule.java",
    }]
    resume_text = _combined_text(resume_paths)
    _check_ads_manager_base_rules(report, root, manager_paths, manager_text, resume_text)
    for rule_id, token, fix in (
        ("ARCH_ENABLE_GATE", ".isEnable", "Check `config.isEnable` before each load/show."),
        ("ARCH_PURCHASE_GATE", "AppPurchase.getInstance().isPurchased", "Skip ads for purchased users in the central manager."),
        ("ARCH_NETWORK_GATE", "isNetworkAvailable", "Skip native loading without a valid network connection."),
        ("ARCH_UA_GATE", "config.enableUaCheck", "Use the placement config's `enableUaCheck` with the mapped `getShouldDisplay*` method."),
    ):
        if token in manager_text:
            report.findings.append(Finding.pass_(rule_id, "architecture", token, "found"))
        else:
            report.findings.append(Finding.fail(rule_id, "architecture", token, "not found in AdsManager", fix))
    # The Infinity base project gates showInterOnboarding/showInterWelcome on
    # `ignoreLimit`. That is the approved base pattern, not a defect, so the
    # shape of the show condition is not checked here. Whether an interstitial
    # actually appears is a runtime claim, raised by the placement rules below.
    for show_fun, rule_id in (("fun showInterOnboarding", "FLOW_INTER_ONBOARDING_SHOW"), ("fun showInterWelcome", "FLOW_INTER_WELCOME_SHOW")):
        if show_fun in manager_text:
            fallback = re.search(re.escape(show_fun) + r"[\s\S]{0,1200}?else\s*\{\s*onAction\(\)", manager_text)
            if fallback:
                report.findings.append(Finding.pass_(rule_id, "placement_flow", "show path always continues navigation when the ad is unavailable", "else branch calls onAction()"))
            else:
                report.findings.append(Finding.fail(rule_id, "placement_flow", "show path always continues navigation when the ad is unavailable", "no else branch calling onAction()", "Add an `else { onAction() }` branch so the user still advances when the interstitial is missing or not ready."))
    if re.search(r"intervalInterstitialAd\s*=\s*35\b", global_text):
        report.findings.append(Finding.pass_("ARCH_INTERSTITIAL_INTERVAL", "architecture", "35-second interstitial interval", "found", _line_ref(root, global_app, "intervalInterstitialAd")))
    else:
        report.findings.append(Finding.fail("ARCH_INTERSTITIAL_INTERVAL", "architecture", "35-second interstitial interval", "not found", "Set `mERainAdConfig.intervalInterstitialAd = 35` unless the ADS Script explicitly approves another interval."))
    bypasses = []
    direct_sdk_tokens = ("loadNativeAd", "loadBanner", "loadCollapsibleBanner", "getInterstitialAds", "forceShowInterstitial", "showRewardAds")
    for path in source_paths:
        if path.name in {"AdsManager.kt", "AdsManager.java", "SplashActivity.kt", "SplashActivity.java", "GlobalApp.kt", "GlobalApp.java"}:
            continue
        if "Activity" in path.name and "ERainAd.getInstance()" in _read(path) and any(token in _read(path) for token in direct_sdk_tokens):
            bypasses.append(_line_ref(root, path, "ERainAd.getInstance()"))
    if bypasses:
        report.findings.append(Finding.fail("ARCH_DIRECT_SDK_BYPASS", "architecture", "SDK calls centralized in AdsManager", "; ".join(bypasses), "Move direct ad load/show calls into AdsManager unless documented as an approved exception."))
    else:
        report.findings.append(Finding.pass_("ARCH_DIRECT_SDK_BYPASS", "architecture", "no unapproved direct Activity SDK calls", "none found"))
    _check_screen_architecture(report, root, manifests)
    _check_language_single_activity(report, root, manifests)
    _check_primary_screen_activities(report, root, manifests, source_paths, navigation_paths)
    _check_screen_flow_rules(report, root, source_paths, contract)
    if overrides_path is None and (root / "ads-audit-overrides.yaml").is_file():
        overrides_path = root / "ads-audit-overrides.yaml"
    overrides = _load_overrides(Path(overrides_path) if overrides_path else None)
    _check_flow(report, root, contract, source_paths, overrides)
    _check_inter_welcome_back(report, root, contract, source_paths, manager_text, global_text, overrides)
    return report


def findings_payload(report: AuditReport) -> list[dict[str, Any]]:
    """Every finding as a plain dict, for `ads-audit-findings.json`."""
    return [
        {
            "rule_id": finding.rule_id,
            "category": finding.category,
            "status": finding.status,
            "expected": finding.expected,
            "observed": finding.observed,
            "recommendation": finding.recommendation,
            "location": finding.location,
        }
        for finding in report.findings
    ]


def render_summary(report: AuditReport, area_report: "AreaReport") -> str:
    """Render the short five-area summary.

    The full finding list lives in ads-audit-findings.json; this file is the
    version a person reads, so it stays around forty lines.
    """
    counts = report.counts()
    lines = [
        "# Infinity Ads Compliance Audit",
        "",
        f"**App:** {area_report.app_name}",
        f"**Package:** `{area_report.package_name}`",
        f"**Ngày:** {area_report.audit_date}",
        f"**Kết quả:** {area_report.overall}",
        "",
        "| Vùng | Kết quả | Lý do |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {area.name} | {area.status} | {area.reason or '—'} |"
        for area in area_report.areas
    )
    lines.extend([
        "",
        f"Khác: {area_report.note}" if area_report.note else "Khác: —",
        "",
        f"Tổng: ❌ {counts.get('fail', 0)} FAIL | ⚠️ {counts.get('needs_mapping', 0)} NEEDS_MAPPING "
        f"| 🔍 {counts.get('needs_runtime_proof', 0)} NEEDS_RUNTIME_PROOF | ✅ {counts.get('pass', 0)} PASS",
        "",
    ])

    delivery_findings = [
        finding for finding in report.findings
        if finding.rule_id in {"WEBHOOK_DELIVERY", "SHEET_DELIVERY"}
    ]
    if delivery_findings:
        lines.extend(["## Giao hàng", ""])
        for finding in delivery_findings:
            lines.extend([
                f"- **{finding.rule_id}**",
                f"  Thực tế: {finding.observed}",
                f"  Sửa: {finding.recommendation}",
                "",
            ])

    failures = [finding for finding in report.findings if finding.status == "FAIL"]
    if not failures:
        lines.append("Không có lỗi tĩnh. Hoàn thành các ca kiểm thử runtime trước khi duyệt phát hành.")
        return "\n".join(lines)

    lines.extend(["## Chi tiết lỗi", ""])
    config_failures = [f for f in failures if f.rule_id.startswith("AD_CONFIG_RELEASE:")]
    if config_failures:
        names = ", ".join(f.rule_id.split(":", 1)[1] for f in config_failures)
        lines.extend([
            f"- **AD_CONFIG_RELEASE** ({len(config_failures)} key): {names}",
            "  Sửa: khớp từng key và ID với file ADS SCRIPTS.",
            "",
        ])
    for finding in failures:
        if finding in config_failures:
            continue
        location = f" ({finding.location})" if finding.location else ""
        lines.extend([
            f"- **{finding.rule_id}**{location}",
            f"  Mong đợi: {finding.expected}",
            f"  Thực tế: {finding.observed}",
            f"  Sửa: {finding.recommendation}",
            "",
        ])
    lines.append("Chi tiết đầy đủ: `ads-audit-findings.json`.")
    return "\n".join(lines)
