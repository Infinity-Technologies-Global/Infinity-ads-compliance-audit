**Language / Ngôn ngữ / भाषा:** [English](README.md) | [Tiếng Việt](README.vi.md) | [हिन्दी](README.hi.md)

# Infinity Ads Compliance Audit

An agent skill for **Claude Code** and **Codex** that audits an Android app's
Infinity ads integration against the base project and the app's own contract
documents. The audit reads the project; it never modifies source.

Install it once, then ask the AI to check any Android project.

## Install

```bash
git clone https://github.com/Infinity-Technologies-Global/Infinity-ads-compliance-audit.git
cd Infinity-ads-compliance-audit
./install.sh          # macOS / Linux
.\install.ps1         # Windows PowerShell
```

The installer detects which agents are on the machine and copies the skill into
each one it finds:

| Host | Location | Invoke with |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `/infinity-ads-compliance-audit` |
| Codex CLI | `$CODEX_HOME/skills/` (default `~/.codex/skills/`) | `$infinity-ads-compliance-audit` |
| Antigravity / Gemini | `~/.gemini/antigravity/skills/` | ask in plain language |

Codex reads skills from `$CODEX_HOME/skills`, **not** `~/.agents/skills`. The
installer writes to both, so an older Codex keeps working.

To install into one repository instead of the whole machine, clone into
`<project>/.claude/skills/infinity-ads-compliance-audit/` (or `.agents/skills/`).
Restart the agent afterwards so it picks up the new skill.

Requires Python 3.9+ and `curl`. No Python packages to install — standard
library only.

## Use

From the Android project root.

**Claude Code** — start `claude`, then:

```text
/infinity-ads-compliance-audit

Audit this project. Documents:
  ADS SCRIPTS:  https://docs.google.com/spreadsheets/d/.../edit#gid=0
  Checklist:    https://docs.google.com/document/d/.../edit
Do not modify source. Reply in Vietnamese.
```

**Codex CLI** — start `codex`, then use the `$` sigil:

```text
$infinity-ads-compliance-audit

Audit this project. Documents:
  ADS SCRIPTS:  https://docs.google.com/spreadsheets/d/.../edit#gid=0
  Checklist:    https://docs.google.com/document/d/.../edit
Do not modify source. Reply in Vietnamese.
```

Both hosts also select the skill on their own when you simply describe the task
("kiểm tra tuân thủ ads cho project này"). The explicit sigil just guarantees it.

If the two CSV files already sit in the project, drop the Documents block —
they are discovered automatically.

The agent runs the bundled auditor, reads the generated reports, checks each
finding against the code, and sends the sanitized report to Discord unless you
ask for a local-only run.

### The two documents

| Document | Carries |
| --- | --- |
| **ADS SCRIPTS** | placement key, ad type, ad-unit ID, AdMob APP ID |
| **working checklist** | app name, package, Firebase project, Adjust/Facebook/TikTok tokens |

Each may be a local CSV or a **Google Sheets / Google Docs link**. Sheets are
exported as CSV; Docs are read as `label: value` lines. Share the link as
anyone-with-the-link viewer, otherwise the download returns a sign-in page and
the audit stops with a sharing error.

If both documents are already CSV files inside the project, they are discovered
automatically — one filename containing `ADS SCRIPTS`, one containing `working`
or `work file`. Discovery never guesses when it finds zero or several matches.

Partner spreadsheets do not need a fixed layout. The parser handles comma,
semicolon, tab and pipe delimiters, English and Vietnamese column labels, title
rows before the real header, and common aliases. When headers are unfamiliar it
infers columns from recognisable values — package names, Firebase URLs, ad
formats, ad-unit IDs. Explicit aliases always win, and if two columns are
equally plausible the audit **stops and reports** rather than auditing the wrong
data.

### How the documents are requested

The skill never audits without both documents, and it never guesses. It works
down three tiers:

| Tier | Situation | What happens |
| --- | --- | --- |
| **1** | Both CSVs already in the project | Discovered automatically. You are asked nothing. |
| **2** | Missing, and no link given | The agent asks you for both documents — link or file — **before** running anything. |
| **3** | Link given but access denied | The audit stops and offers two fixes: change link sharing, or download the file and pass its path. |

If a document is still unavailable after tier 3, the audit **stops and says so**.
It will not produce a partial report, invent ad-unit IDs, or fall back to the
base project's values — a half-audit that reads like a verdict is worse than no
audit.

Discovery also refuses to guess between candidates: zero matches or several
matches both drop to tier 2 rather than picking one.

## What gets checked

The report covers five areas of the ads journey. Each is `Done` or `Error`.

| Area | Covers |
| --- | --- |
| **Init** | `GlobalApp` init order, DevConfig version fields, `ERainAdConfig` fields, AppOpen exclusions, the 35-second interstitial interval, lifecycle observer registration |
| **Splash** | RemoteConfig load and apply, `inter_splash`, `banner_splash`, `open_resume`, and the native-language preload from the splash interstitial's `onAdLoaded` |
| **Language** | DevSetting on the title, native click load, onboarding page-1 preload, the `removeObservers` swap between the two native observers, render and hide-on-null |
| **Onboarding** | Preload of native page 4, native full and `inter_onboarding`, page LiveData mapping, `viewLifecycleOwner` observation, and the interstitial before Home |
| **Config** | Release `ad_config.json` keys and IDs against ADS SCRIPTS, the AdMob app id from the **release** `manifestPlaceholders`, and coverage against the base's own 24 keys |

An area turns `Error` only when a check outright fails. `NEEDS_MAPPING` and
`NEEDS_RUNTIME_PROOF` never turn an area red — they mean static analysis could
not settle the claim, not that the app is wrong.

Everything else the audit still checks — Welcome/Resume, Banner, service tokens,
Firebase, app name and package, direct SDK calls — is summarised in one Note
line. Those failures still set the exit code to `2`.

Pass `--base-project /path/to/base` to read the 24 key list from a base checkout
instead of the copy bundled with this skill.

## Output

Written to `ads-audit-output/` inside the audited project:

- `ads-audit-summary.md` — the five-area table, then each failure with `file:line`.
- `ads-audit-findings.json` — every finding, for deep debugging.

The command exits `0` with no failures, `2` when any check fails, and `1` for
invalid input.

Reports redact Adjust, Facebook client, and TikTok values. They never include
`app-ads.txt` checks.

## Custom placements

If a placement returns `NEEDS_MAPPING`, copy `templates/ads-audit-overrides.yaml`
into the app and add the approved class and call mapping, keeping the contract
key and ID exactly. Some placements — `native_home`, `native_permission`,
`native_onboarding_fullscreen_*_4`, `reward_example` — exist in
`AdsManager` but are not wired to a screen in the base, so they land here by
design.

## Discord webhook

One short message per audit, no attachment:

```
🚨 Ads Audit — My App
`com.example.app`

Init       → Done
Splash     → Done
Language   → Error: thiếu removeObservers
Onboarding → Done
Config     → Error: thiếu 3 key

Khác: banner chưa dùng BaseActivityWithBanner
```

Discord delivery is opt-in. Configure the endpoint with `--webhook-url` or the
`ADS_AUDIT_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` environment variables. Without
one, the audit keeps only the local reports. Use `--no-webhook` to ignore an
inherited environment configuration.

## Audit spreadsheet

Each audit appends one row:

`STT | Package | App name | Ngày | Init | Splash | Language | Onboarding | Config | Note`

The rows arrive through a Google Apps Script Web App bound to the spreadsheet;
`templates/apps-script-sheet.gs` is the script to paste into it.

The endpoint is embedded in the skill. **The shared secret is not** — this skill
gets packaged into partner repositories, so the secret would travel with it. Set
it yourself. In Apps Script, open **Project Settings > Script Properties** and
add the required `ADS_AUDIT_SHEET_TOKEN` property. Then give the auditor the
same value:

```bash
export ADS_AUDIT_SHEET_TOKEN=<the secret configured in the Apps Script>
```

Without it the push is skipped with a note on stderr and the audit still
succeeds. Disable it outright with `--no-sheet`, or point somewhere else with
`--sheet-url` / `ADS_AUDIT_SHEET_URL`.

## Running the auditor directly

Useful for CI or debugging; the AI path above is the intended one.

```bash
python3 scripts/run_audit.py --project /path/to/app --no-webhook
python3 scripts/run_audit.py --project . \
  --ads-script "https://docs.google.com/spreadsheets/d/<id>/edit#gid=0" \
  --working-file "./working file.csv"
```

## Package for a partner repo

```bash
python3 scripts/package_skill.py --skill-root . --output infinity-ads-audit.zip
```

## Reference

- `references/base-code-reference.md` — the base implementation in code:
  Gradle, `GlobalApp`, `AdsManager`, every screen, gates, config schema.
- `references/base-integration-rules.md` — the same rules as a checklist.
- `references/placement-rule-map.yaml` — approved evidence per placement.
