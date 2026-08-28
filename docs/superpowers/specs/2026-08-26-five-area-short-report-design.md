# Five-Area Short Report Design

**Date:** 2026-08-26
**Status:** Approved

## Problem

The audit currently emits roughly 110 findings for a 24-placement contract: 33 fixed
rules plus three findings per placement. The Markdown summary prints every non-PASS
finding as a four-line block, so the report is long enough that nobody reads it.
Marketing and QA only need to know which part of the ads journey is broken.

There is also no record of past audits. Each run overwrites the previous report, so
there is no way to see which partner apps were checked, when, or how they scored.

## Goals

1. Collapse the report to five areas of the ads journey, each reporting `Done` or `Error`.
2. Send a five-line Discord message instead of a multi-part one with an attachment.
3. Append one row per audit to a Google Sheet so results accumulate over time.
4. Verify the app's placement keys against the Infinity base project's own key list.

## Non-goals

- Removing any existing check. Every rule keeps running; only the reporting layer changes.
- Changing how the two contract documents are discovered or parsed.
- Runtime or instrumented testing. The audit stays static.

## Architecture

A new rollup layer sits between the existing engine and the three output channels.

```
inspect_project()              scripts/ads_audit_lib.py — unchanged apart from four new rules
        │
        ▼  list[Finding]
area_rollup()                  scripts/area_rollup.py — NEW
        │
        ▼  AreaReport
   ┌────┴─────┬──────────┬────────────┐
   ▼          ▼          ▼            ▼
summary.md  Discord   Google Sheet  exit code
```

`inspect_project` keeps its current signature and behaviour. The rollup consumes its
findings and produces a small value object; the three renderers consume only that
object. No renderer reads raw findings, so adding an output channel later means adding
one renderer, not touching the engine.

### `scripts/area_rollup.py`

```python
AREAS = ("init", "splash", "language", "onboarding", "config")

@dataclass(frozen=True)
class AreaResult:
    name: str          # "Splash"
    status: str        # "Done" | "Error"
    reason: str        # "" when Done; one short Vietnamese clause when Error

@dataclass(frozen=True)
class AreaReport:
    app_name: str
    package_name: str
    audit_date: str        # YYYY-MM-DD, local date of the run
    areas: list[AreaResult]
    note: str              # out-of-scope failures, semicolon-joined, capped
    overall: str           # "Done" | "Error"
```

The module owns one lookup table mapping rule id to area, plus one table mapping rule
id to its short Vietnamese reason phrase. Both are plain dicts so a reviewer can read
the whole classification in one screen.

## Area membership

| Area | Rule ids |
| --- | --- |
| **Init** | `ARCH_GLOBAL_INIT_ORDER`, `ARCH_DEV_CONFIG_INIT`, `ARCH_DEV_CONFIG_BUILD_FIELDS`, `ARCH_ADS_CONFIG_FIELDS`, `ARCH_APP_OPEN_EXCLUSIONS`, `ARCH_MOBILE_ADS_INIT`, `ARCH_REMOTE_CONFIG_INIT`, `ARCH_ERAIN_INIT`, `ARCH_INTERSTITIAL_INTERVAL`, `FLOW_INTER_WELCOME_BACK_REGISTRATION` |
| **Splash** | `FLOW_SPLASH_REMOTE_CONFIG`, `FLOW_SPLASH_INTER_PRELOAD_LANGUAGE`, `FLOW_SPLASH_OPEN_RESUME`, `FLOW_SPLASH_BANNER`, `PLACEMENT_FLOW:inter_splash`, `PLACEMENT_FLOW:open_resume`, `PLACEMENT_FLOW:banner_splash`, `PLACEMENT_FLOW:native_language_1`, `PLACEMENT_FLOW:native_language_2` |
| **Language** | `FLOW_LANGUAGE_DEV_SETTING`, `FLOW_LANGUAGE_PRELOAD_AND_RENDER`, `FLOW_LANGUAGE_OBSERVER_SWAP`, `PLACEMENT_FLOW:native_language_1_click`, `PLACEMENT_FLOW:native_language_2_click`, `PLACEMENT_FLOW:native_onboarding_1_1`, `PLACEMENT_FLOW:native_onboarding_2_1` |
| **Onboarding** | `FLOW_ONBOARDING_PRELOAD_AND_SHOW`, `FLOW_ONBOARDING_PAGE_RENDERING`, `FLOW_ONBOARDING_PAGE_LIFECYCLE`, `FLOW_INTER_ONBOARDING_SHOW`, `PLACEMENT_FLOW:native_onboarding_1_4`, `PLACEMENT_FLOW:native_onboarding_2_4`, `PLACEMENT_FLOW:native_onboarding_fullscreen_1_3`, `PLACEMENT_FLOW:native_onboarding_fullscreen_2_3`, `PLACEMENT_FLOW:native_onboarding_fullscreen_1_4`, `PLACEMENT_FLOW:native_onboarding_fullscreen_2_4`, `PLACEMENT_FLOW:inter_onboarding` |
| **Config** | every `AD_CONFIG_RELEASE:*`, `ADMOB_APP_ID`, `ADMOB_MANIFEST_META`, `BASE_KEY_COVERAGE` |

Every rule id not listed above is out of scope. Its failures go to the Note field.

Membership is by exact rule id or by documented prefix, never by substring guessing.
A rule id that reaches the rollup without a table entry is treated as out of scope and
logged to stderr once, so a newly added rule surfaces during development rather than
disappearing silently.

## Status rule

An area is `Error` when it contains at least one finding with status `FAIL`. It is
`Done` otherwise.

`NEEDS_MAPPING` and `NEEDS_RUNTIME_PROOF` never make an area `Error`. Both mean static
analysis could not settle the claim, which is not the same as the app being wrong.
Treating them as failures would mark nearly every app red, because every interstitial
placement emits a `NEEDS_RUNTIME_PROOF` finding by design.

`overall` is `Error` when any of the five areas is `Error`, otherwise `Done`.

## Reason text

Each area's `reason` is built from its failing rule ids, in the table's order, joined
with `; ` and capped at 120 characters. Every in-scope rule id has a fixed Vietnamese
phrase of at most about eight words, for example:

| Rule id | Phrase |
| --- | --- |
| `ARCH_GLOBAL_INIT_ORDER` | `sai thứ tự init` |
| `FLOW_SPLASH_REMOTE_CONFIG` | `chưa lấy RemoteConfig` |
| `FLOW_SPLASH_BANNER` | `chưa load banner splash` |
| `FLOW_LANGUAGE_OBSERVER_SWAP` | `thiếu removeObservers` |
| `FLOW_ONBOARDING_PAGE_LIFECYCLE` | `observe sai lifecycle owner` |
| `BASE_KEY_COVERAGE` | `thiếu N key` |

`AD_CONFIG_RELEASE:*` failures collapse to a single count phrase, `sai N key config`,
rather than listing key names.

The Note field uses the same mechanism over out-of-scope rules, capped at 200
characters, with a trailing `…` when truncated.

## New rules

Four rules are added to `ads_audit_lib.py`. Each follows the existing token-presence
pattern and appends a `Finding` the same way its neighbours do.

### `FLOW_LANGUAGE_OBSERVER_SWAP`

`LanguageActivity` must contain both `nativeLanguageAdLive.removeObservers` and
`nativeLanguageClickAdLive.removeObservers`. The base swaps between its two native
observers and removes the other one each time; without that, both stay active and the
ad container flickers between two ads. Verified in the base at
`LanguageActivity.kt:121` and `:128`.

Missing either token is a `FAIL`.

### `FLOW_ONBOARDING_PAGE_LIFECYCLE`

`OnboardingPageFragment` must call `observe(viewLifecycleOwner)`. Observing with the
fragment's own lifecycle inside a `ViewPager2` leaks observers across page recycling.
Verified in the base at `OnboardingPageFragment.kt:69`.

A file that observes but never names `viewLifecycleOwner` is a `FAIL`. A file with no
observe call at all is already covered by `FLOW_ONBOARDING_PAGE_RENDERING`, so this
rule stays silent there rather than double-reporting.

### `FLOW_SPLASH_BANNER`

Applies only when the ADS SCRIPTS contract lists `banner_splash`. `SplashActivity` must
bind that key to a banner container, matched with the same three patterns
`_banner_evidence` already uses for other banner placements.

The Infinity base does not load `banner_splash` on any screen — the key exists in
`ad_config.json` and `AdRemoteConfigExtensions.kt` with no call site. Partner apps do
show a splash banner, so a contract that lists the key and an app that never binds it
is a `FAIL`, not a mapping gap. When the contract omits the key, the rule emits no
finding.

### `BASE_KEY_COVERAGE`

Compares the placement keys in the app's release `ad_config.json` against the base key
list. Reports keys the base has that the app lacks, and keys the app has that the base
does not define.

A missing key is a `FAIL`. An extra key is a `NEEDS_MAPPING`, because partner apps
legitimately add placements as long as the architecture follows the base pattern.

The base list is embedded in the skill as `BASE_PLACEMENT_KEYS`, the 24 keys verified
against `TestSill` on 2026-08-26. Passing `--base-project PATH` reads
`<PATH>/app/src/main/assets/ad_config.json` instead and uses its keys, so the check
tracks a moved base without a skill release. An unreadable `--base-project` path is a
setup error that stops the audit, not a silent fallback.

## Output channels

### `ads-audit-summary.md`

Roughly 40 lines. Header with app name, package, date and overall status; the
five-area table; one section per `Error` area listing its failing rules with
`file:line`; then the Note line.

The full finding list moves to a new `ads-audit-findings.json`, one object per finding
with every field of `Finding`. Nothing is lost — a developer who needs the detail reads
that file.

`ads-audit-evidence.json` is replaced by `ads-audit-findings.json` and is no longer
written. Its old shape existed to feed the grouped Vietnamese Discord payload, which
this design removes. `references/report-schema.json` is rewritten to describe the new
`AreaReport` and the Sheet row instead.

### Discord

One message, no attachment. The `ads-audit-summary.md` file stays on disk for whoever
wants it.

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

The icon is `✅` when `overall` is `Done` and `🚨` when it is `Error`. The `Khác:` line
is omitted when the Note is empty. The message is well under the 2000-character limit
by construction, so the existing multi-part splitting code is removed.

### Google Sheet

A row is appended through a Google Apps Script Web App bound to the target sheet. The
audit POSTs JSON with `curl`, exactly as the Discord webhook already does.

```json
{
  "package": "com.example.app",
  "app_name": "My App",
  "date": "2026-08-26",
  "init": "Done",
  "splash": "Done",
  "language": "Error",
  "onboarding": "Done",
  "config": "Error",
  "note": "thiếu removeObservers; thiếu 3 key"
}
```

Columns: `STT | Package | App name | Ngày | Init | Splash | Language | Onboarding | Config | Note`.

`STT` is assigned by the Apps Script from `getLastRow()` under a script lock, not by
the auditor, so concurrent runs cannot collide on a number.

Chosen over the Sheets REST API because the skill depends on nothing beyond the Python
standard library and `curl`. A service account would require RS256 JWT signing, which
the standard library cannot do.

#### Posting: two steps, never `curl -L`

Apps Script answers a POST with a `302` to a one-time `script.googleusercontent.com`
URL that holds the JSON reply. Following that redirect with `curl -L` fails
consistently — verified against the live deployment on 2026-08-26, where three
consecutive attempts each returned a Google Drive "file not found" page instead of the
reply. The push therefore runs in two steps:

1. `POST` the payload with `--output /dev/null --write-out '%{http_code} %{redirect_url}'`
   and no `--location`.
2. `GET` the returned redirect URL and parse the JSON body.

A `302` with a redirect URL means `doPost` ran. Step 2 distinguishes `{"ok":true}` from
`{"ok":false,"error":"unauthorized"}`, which a status code alone cannot.

#### Credentials

| Value | Where it lives |
| --- | --- |
| Web App URL | `run_audit.py` `DEFAULT_SHEET_URL`, overridable with `--sheet-url` or `ADS_AUDIT_SHEET_URL` |
| Shared secret | `run_audit.py` `DEFAULT_SHEET_TOKEN`, overridable in priority order by `--sheet-token`, `ADS_AUDIT_SHEET_TOKEN`, or a gitignored `scripts/.sheet-token` file |

**Revised 2026-08-28.** The secret is now shipped alongside the URL so an installed
skill logs every run with no operator setup. It is safe enough to ship because the Apps
Script grants exactly one capability against that value — append a row to the `Audit
Log` tab — with no read, edit, or delete. Rotate by changing `DEFAULT_SHEET_TOKEN` and
`templates/apps-script-sheet.gs` together. `scripts/.sheet-token` stays gitignored and
excluded from packages so a developer can point a local run at a test sheet without
touching source.

When the secret is blanked from every source the push is skipped with a one-line notice
on stderr, and the audit still succeeds.

## Error handling

| Failure | Behaviour |
| --- | --- |
| Discord POST fails | Existing behaviour: append a `WEBHOOK_DELIVERY` finding, rewrite local reports |
| Sheet POST fails, or the reply is not `{"ok":true}` | Append a `SHEET_DELIVERY` finding the same way; local reports and Discord still succeed |
| No sheet token from any source (flag, env, `scripts/.sheet-token`) | Skip the push, one line on stderr |
| `--base-project` path unreadable | Setup error, exit 1 |
| Rule id missing from the area table | Treat as out of scope, log once to stderr |

Neither delivery failure changes the exit code.

The exit code keeps its current meaning and is **not** narrowed to the five areas:
`0` when no finding has status `FAIL`, `2` when any finding does, `1` for invalid
input. An out-of-scope failure therefore still exits `2` even though all five areas
read `Done`, which is what CI needs — the Note field is a summary for people, not a
reason to call a broken app green.

## Testing

`tests/test_run_audit.py` already carries a compliant fixture project and a negative
one. Both are extended:

- Compliant fixture gains `removeObservers` on both Language observers,
  `observe(viewLifecycleOwner)` in the onboarding page, a `banner_splash` binding in
  `SplashActivity`, and all 24 base keys in `ad_config.json`. It must roll up to five
  `Done` areas and an empty Note.
- Negative fixture drops each of the four new tokens in turn and omits three config
  keys. It must roll up to `Error` on Splash, Language, Onboarding and Config, with
  Init still `Done`.

New unit tests cover the rollup in isolation: a `NEEDS_RUNTIME_PROOF` finding leaves
its area `Done`; an unmapped rule id lands in the Note; reason text respects its cap;
and the Sheet payload carries exactly the ten documented fields.

The Apps Script is not unit tested. Its contract is the JSON shape above, which the
Python side does test.

## Files

| File | Change |
| --- | --- |
| `scripts/area_rollup.py` | Create — rollup, area tables, reason phrases |
| `scripts/sheet_push.py` | Create — build the row payload, POST it |
| `scripts/ads_audit_lib.py` | Add four rules; add `BASE_PLACEMENT_KEYS`; replace `render_summary` with the short form; drop the MKT grouping helpers the Discord path no longer uses |
| `scripts/run_audit.py` | Call the rollup; render one Discord message; call the sheet push; add `--sheet-url` and `--base-project`; write `ads-audit-findings.json` instead of `ads-audit-evidence.json` |
| `references/report-schema.json` | Rewrite for the `AreaReport` and the Sheet row |
| `tests/test_run_audit.py` | Extend both fixtures; add rollup unit tests |
| `templates/apps-script-sheet.gs` | Create — the script the operator pastes into their sheet |
| `SKILL.md`, `README*.md`, `references/base-integration-rules.md` | Document the five areas, the four new rule ids, and the sheet setup |
