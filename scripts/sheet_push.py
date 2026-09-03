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
import time


SHEET_FIELDS = ("package", "app_name", "date", "init", "splash", "language", "onboarding", "config", "note")

# The Note cell is a glance, not a report. Keep it to one short line.
NOTE_LIMIT = 200

# A laptop on flaky Wi-Fi, a VPN coming up, or a systemd-resolved stub that has
# not warmed its cache all make curl fail before it opens the connection. One
# blip should not cost the run its audit row, so those failures are retried.
RETRY_DELAYS = (1.0, 3.0)

# curl exit codes that prove the request never reached Apps Script, so a retry
# cannot append the row twice. A timeout or a connection dropped mid-transfer is
# deliberately absent: the row may already be in the sheet.
SAFE_TO_RETRY = {5, 6, 7, 35}

CURL_MESSAGES = {
    5: "could not resolve the proxy",
    6: "could not resolve the Apps Script host (DNS)",
    7: "could not connect to the Apps Script host",
    28: "timed out",
    35: "TLS handshake failed",
    52: "got an empty reply",
    56: "lost the connection while transferring",
}


def _curl_error(code: int) -> str:
    """A readable reason that never echoes the endpoint, stderr, or the token."""
    detail = CURL_MESSAGES.get(code)
    return f"curl {detail} (exit code {code})" if detail else f"curl exited with code {code}"


def _run_curl(command: list[str], input_bytes: bytes | None, timeout: int) -> tuple[subprocess.CompletedProcess | None, str | None]:
    """Run curl, retrying only the failures that never reached the server."""
    error = "curl exited with an unknown error"
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            completed = subprocess.run(
                command,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout + 5,
                check=False,
            )
        except FileNotFoundError:
            return None, "curl is not installed"
        except subprocess.TimeoutExpired:
            return None, "curl timed out"
        if completed.returncode == 0:
            return completed, None
        error = _curl_error(completed.returncode)
        if completed.returncode not in SAFE_TO_RETRY or attempt == len(RETRY_DELAYS):
            break
        time.sleep(RETRY_DELAYS[attempt])
    return None, error


def build_row(area_report, token: str | None) -> dict:
    """Build the JSON body the Apps Script expects, one field per column."""
    statuses = {area.name.lower(): area.status for area in area_report.areas}
    reasons = [f"{area.name}: {area.reason}" for area in area_report.areas if area.status == "Error" and area.reason]
    if area_report.note:
        reasons.append(area_report.note)
    note = "; ".join(reasons)
    if len(note) > NOTE_LIMIT:
        note = note[: NOTE_LIMIT - 1] + "…"
    row = {
        "package": area_report.package_name,
        "app_name": area_report.app_name,
        "date": area_report.audit_date,
        "init": statuses.get("init", ""),
        "splash": statuses.get("splash", ""),
        "language": statuses.get("language", ""),
        "onboarding": statuses.get("onboarding", ""),
        "config": statuses.get("config", ""),
        "note": note,
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
        "--connect-timeout", "10",
        "--max-time", str(timeout),
        "--request", "POST",
        "--header", "Content-Type: application/json",
        "--data-binary", "@-",
        url,
    ]
    completed, error = _run_curl(command, json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout)
    if error:
        return error

    parts = completed.stdout.decode("ascii", errors="ignore").split()
    status = parts[0] if parts else ""
    location = parts[1] if len(parts) > 1 else ""
    if status not in {"200", "302"}:
        return f"HTTP {status or 'unknown'}"
    if not location:
        return "Apps Script returned no result location"
    return _read_reply(location, timeout)


def _read_reply(location: str, timeout: int) -> str | None:
    command = ["curl", "--silent", "--show-error", "--connect-timeout", "10", "--max-time", str(timeout), location]
    completed, error = _run_curl(command, None, timeout)
    if error:
        return f"{error} reading the Apps Script reply"
    try:
        parsed = json.loads(completed.stdout.decode("utf-8", errors="replace").strip())
    except json.JSONDecodeError:
        return "Apps Script reply was not JSON"
    if not isinstance(parsed, dict):
        return "Apps Script reply was not a JSON object"
    if parsed.get("ok") is True:
        return None
    if parsed.get("error") == "unauthorized":
        return "Apps Script rejected the row: unauthorized"
    return "Apps Script rejected the row"
