#!/usr/bin/env python3
"""Append one audit result row to a Google Sheet via an Apps Script Web App.

Apps Script answers a POST with a 302 to a one-time googleusercontent URL that
holds the JSON reply. Following that with `curl -L` fails consistently, so the
push posts without --location, reads the redirect target, and fetches it
separately.
"""

from __future__ import annotations

import json
import subprocess


SHEET_FIELDS = ("package", "app_name", "date", "init", "splash", "language", "onboarding", "config", "note")


def build_row(area_report, token: str | None) -> dict:
    """Build the JSON body the Apps Script expects, one field per column."""
    statuses = {area.name.lower(): area.status for area in area_report.areas}
    reasons = [f"{area.name}: {area.reason}" for area in area_report.areas if area.status == "Error" and area.reason]
    if area_report.note:
        reasons.append(area_report.note)
    row = {
        "package": area_report.package_name,
        "app_name": area_report.app_name,
        "date": area_report.audit_date,
        "init": statuses.get("init", ""),
        "splash": statuses.get("splash", ""),
        "language": statuses.get("language", ""),
        "onboarding": statuses.get("onboarding", ""),
        "config": statuses.get("config", ""),
        "note": "; ".join(reasons),
    }
    if token:
        row["token"] = token
    return row


def post_row(url: str, payload: dict, timeout: int = 30) -> str | None:
    """Append the row, returning ``None`` on success or a sanitized error."""
    command = [
        "curl", "--silent", "--show-error",
        "--output", "/dev/null",
        "--write-out", "%{http_code} %{redirect_url}",
        "--max-time", str(timeout),
        "--request", "POST",
        "--header", "Content-Type: application/json",
        "--data-binary", "@-",
        url,
    ]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 5,
            check=False,
        )
    except FileNotFoundError:
        return "curl is not installed"
    except subprocess.TimeoutExpired:
        return "curl timed out"
    if completed.returncode != 0:
        return f"curl exited with code {completed.returncode}"

    parts = completed.stdout.decode("ascii", errors="ignore").split()
    status = parts[0] if parts else ""
    location = parts[1] if len(parts) > 1 else ""
    if status not in {"200", "302"}:
        return f"HTTP {status or 'unknown'}"
    if not location:
        return "Apps Script returned no result location"
    return _read_reply(location, timeout)


def _read_reply(location: str, timeout: int) -> str | None:
    try:
        completed = subprocess.run(
            ["curl", "--silent", "--show-error", "--max-time", str(timeout), location],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout + 5,
            check=False,
        )
    except FileNotFoundError:
        return "curl is not installed"
    except subprocess.TimeoutExpired:
        return "curl timed out reading the Apps Script reply"
    if completed.returncode != 0:
        return f"curl exited with code {completed.returncode} reading the reply"
    try:
        parsed = json.loads(completed.stdout.decode("utf-8", errors="replace").strip())
    except json.JSONDecodeError:
        return "Apps Script reply was not JSON"
    if parsed.get("ok") is True:
        return None
    if parsed.get("error") == "unauthorized":
        return "Apps Script rejected the row: unauthorized"
    return "Apps Script rejected the row"
