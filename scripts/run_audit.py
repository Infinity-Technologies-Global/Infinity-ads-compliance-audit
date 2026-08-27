#!/usr/bin/env python3
"""Run the Infinity ads static audit without modifying the target project."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ads_audit_lib import Finding, findings_payload, inspect_project, parse_ads_script, parse_working_file, render_summary
from area_rollup import area_rollup
from doc_sources import DocumentError, is_url, resolve_document
from sheet_push import build_row, post_row


# Discord delivery is opt-in. Configure the endpoint per run or via the environment.
# The Apps Script Web App bound to the Infinity audit spreadsheet. Safe to embed:
# the script rejects any request without the matching shared secret, which is
# deliberately NOT stored here — package_skill.py ships this file to partners.
DEFAULT_SHEET_URL = "https://script.google.com/macros/s/AKfycbyKxCaMNLKZPlQRGr37QcWbcut-EkkKvazqqsFeKrOstcygchWBjMmNu3uy2ckJNUUyJg/exec"
CSV_SKIP_DIRS = {".git", ".gradle", ".idea", ".agents", ".codex", "ads-audit-output", "build", "node_modules", "out"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit an Android partner ads integration against Infinity CSV contracts.")
    parser.add_argument("--project", default=".", help="Android project root (default: current directory)")
    parser.add_argument("--ads-script", help="ADS SCRIPTS CSV: local path or Google Sheets/Docs link (auto-discovered when omitted)")
    parser.add_argument("--working-file", help="Working checklist: local path or Google Sheets/Docs link (auto-discovered when omitted)")
    parser.add_argument("--output-dir", default="ads-audit-output", help="Directory for report files")
    parser.add_argument("--overrides", help="Optional approved ads-audit-overrides.yaml path")
    parser.add_argument("--base-project", help="Infinity base checkout to read the placement key list from (default: the list bundled with this skill)")
    parser.add_argument("--webhook-url", help="Discord webhook endpoint for the sanitized report")
    parser.add_argument("--webhook-token", help="Optional bearer token; never written to output")
    parser.add_argument("--no-webhook", action="store_true", help="Create local reports only; do not send a webhook")
    parser.add_argument("--sheet-url", help="Apps Script Web App endpoint for the audit spreadsheet")
    parser.add_argument("--sheet-token", help="Shared secret for the Apps Script endpoint; never written to output")
    parser.add_argument("--no-sheet", action="store_true", help="Do not append a row to the audit spreadsheet")
    return parser


def _normalized_filename(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "", path.name.casefold())


def discover_csv(project: Path, kind: str) -> Path:
    project = project.resolve()
    matches: list[Path] = []
    for candidate in project.rglob("*.csv"):
        relative = candidate.relative_to(project)
        if any(part in CSV_SKIP_DIRS for part in relative.parts):
            continue
        normalized = _normalized_filename(candidate)
        matched = "adsscripts" in normalized if kind == "ads" else "working" in normalized or "workfile" in normalized
        if matched:
            matches.append(candidate.resolve())
    matches.sort()
    flag = "--ads-script" if kind == "ads" else "--working-file"
    label = "ADS SCRIPTS" if kind == "ads" else "working-file"
    if not matches:
        raise ValueError(
            f"Could not find the {label} document under {project}.\n"
            f"Supply it with {flag}, as either:\n"
            f"  - a Google Sheets/Docs share link (set to Anyone with the link, Viewer), or\n"
            f"  - a path to a CSV downloaded from that document.\n"
            f"If you do not have it, ask the partner for the {label} document before "
            f"auditing. Do not audit without it and do not substitute base values."
        )
    if len(matches) > 1:
        listed = "\n".join(f"  - {candidate.relative_to(project)}" for candidate in matches)
        raise ValueError(
            f"Found several {label} candidates, so discovery will not choose one.\n{listed}\n"
            f"Pass the right one with {flag}. If it is not obvious which is current, "
            f"ask the partner before auditing — auditing the wrong revision is worse "
            f"than asking."
        )
    return matches[0]


def resolve_csv_input(project: Path, supplied: str | None, kind: str, cache_dir: Path | None = None) -> Path:
    if supplied is None:
        return discover_csv(project, kind)
    if not supplied.strip():
        flag = "--ads-script" if kind == "ads" else "--working-file"
        raise ValueError(f"{flag} cannot be empty.")
    if is_url(supplied):
        # A Google Sheets/Docs share link, or any URL serving CSV.
        return resolve_document(supplied.strip(), "ads-script" if kind == "ads" else "working-file", cache_dir)
    candidate = Path(supplied).expanduser()
    if not candidate.is_absolute():
        candidate = project / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        flag = "--ads-script" if kind == "ads" else "--working-file"
        raise ValueError(f"File supplied to {flag} was not found: {candidate}")
    return candidate


def post_webhook(url: str, token: str | None, payload: dict, attachment_path: Path | None = None) -> str | None:
    separator = "&" if "?" in url else "?"
    wait_url = f"{url}{separator}wait=true"
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--max-time",
        "10",
        "--request",
        "POST",
    ]
    if token:
        command.extend(["--header", f"Authorization: Bearer {token}"])
    input_bytes: bytes | None = None
    if attachment_path:
        command.extend([
            "--form-string",
            f"payload_json={json.dumps(payload, ensure_ascii=False)}",
            "--form",
            f"files[0]=@{attachment_path};filename={attachment_path.name}",
            wait_url,
        ])
    else:
        command.extend([
            "--header",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
            wait_url,
        ])
        input_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        completed = subprocess.run(
            command,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        return "curl is not installed"
    except subprocess.TimeoutExpired:
        return "curl timed out"
    if completed.returncode != 0:
        return f"curl exited with code {completed.returncode}"
    status_text = completed.stdout.decode("ascii", errors="ignore").strip()
    if not status_text.isdigit():
        return "curl returned an invalid HTTP status"
    status = int(status_text)
    return None if 200 <= status < 300 else f"HTTP {status}"


def discord_message(area_report) -> dict:
    """Render the whole audit as one short Discord message.

    Five areas, one line each. The summary file stays on disk rather than being
    attached, because the areas are what people act on.
    """
    icon = "✅" if area_report.overall == "Done" else "🚨"
    width = max(len(area.name) for area in area_report.areas)
    identity_limit = 400
    app_name = area_report.app_name[: identity_limit - 1] + "…" if len(area_report.app_name) > identity_limit else area_report.app_name
    package_name = area_report.package_name[: identity_limit - 1] + "…" if len(area_report.package_name) > identity_limit else area_report.package_name
    lines = [
        f"{icon} **Ads Audit — {app_name}**",
        f"`{package_name}`",
        "",
    ]
    for area in area_report.areas:
        suffix = f": {area.reason}" if area.status == "Error" and area.reason else ""
        lines.append(f"{area.name.ljust(width)} → {area.status}{suffix}")
    if area_report.note:
        lines.extend(["", f"Khác: {area_report.note}"])
    return {"content": "\n".join(lines), "allowed_mentions": {"parse": []}}


def checklist_name(report) -> str:
    return report.checklist.app_name or Path(report.project_root).name


def checklist_package(report) -> str:
    return report.checklist.package_name or "<chưa tìm thấy>"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = Path(args.project).resolve()
    raw_output = Path(args.output_dir)
    output_dir = (project / raw_output).resolve() if not raw_output.is_absolute() else raw_output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        doc_cache = output_dir / "source-documents"
        ads_script = resolve_csv_input(project, args.ads_script, "ads", doc_cache)
        working_file = resolve_csv_input(project, args.working_file, "working", doc_cache)
        report = inspect_project(project, parse_ads_script(ads_script), parse_working_file(working_file), args.overrides, args.base_project)
    except (OSError, ValueError, DocumentError, json.JSONDecodeError) as error:
        print(f"Audit setup error: {error}", file=sys.stderr)
        return 1
    area_report = area_rollup(report.findings, checklist_name(report), checklist_package(report))
    summary_path = output_dir / "ads-audit-summary.md"
    findings_path = output_dir / "ads-audit-findings.json"
    summary_path.write_text(render_summary(report, area_report), encoding="utf-8")
    findings_path.write_text(json.dumps(findings_payload(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    webhook_url = None if args.no_webhook else (
        args.webhook_url
        or os.environ.get("ADS_AUDIT_WEBHOOK_URL")
        or os.environ.get("DISCORD_WEBHOOK_URL")
    )
    if webhook_url:
        error = post_webhook(webhook_url, args.webhook_token, discord_message(area_report))
        if error:
            report.findings.append(Finding.needs_runtime("WEBHOOK_DELIVERY", "successful webhook delivery", error, "Check the configured Discord webhook, TLS, authorization and network, then rerun the audit."))
            area_report = area_rollup(report.findings, checklist_name(report), checklist_package(report))
            summary_path.write_text(render_summary(report, area_report), encoding="utf-8")
            findings_path.write_text(json.dumps(findings_payload(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sheet_token = args.sheet_token or os.environ.get("ADS_AUDIT_SHEET_TOKEN")
    sheet_url = None if args.no_sheet else (args.sheet_url or os.environ.get("ADS_AUDIT_SHEET_URL") or DEFAULT_SHEET_URL)
    if sheet_url and not sheet_token:
        # A partner running this skill has no business writing to Infinity's
        # sheet, so a missing secret is a skip, not a failure.
        print("Sheet push skipped: set ADS_AUDIT_SHEET_TOKEN or pass --sheet-token.", file=sys.stderr)
    elif sheet_url:
        error = post_row(sheet_url, build_row(area_report, sheet_token))
        if error:
            report.findings.append(Finding.needs_runtime("SHEET_DELIVERY", "successful Google Sheet row append", error, "Check the Apps Script deployment, its shared secret, and network access, then rerun the audit."))
            area_report = area_rollup(report.findings, checklist_name(report), checklist_package(report))
            summary_path.write_text(render_summary(report, area_report), encoding="utf-8")
            findings_path.write_text(json.dumps(findings_payload(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Summary: {summary_path}")
    print(f"Findings: {findings_path}")
    return 2 if report.readiness() == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
