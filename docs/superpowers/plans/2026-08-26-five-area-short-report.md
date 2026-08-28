# Five-Area Short Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the audit report to five journey areas reporting `Done` or `Error`, send a single short Discord message, and append one row per audit to a Google Sheet.

**Architecture:** A new pure module `scripts/area_rollup.py` maps the existing `Finding` list onto five areas and decides `Done`/`Error` per area. Three renderers — the Markdown summary, the Discord message, and the Sheet row — read only that rollup, never raw findings. `scripts/ads_audit_lib.py` keeps its engine and gains four rules; `scripts/sheet_push.py` handles the Apps Script transport.

**Tech Stack:** Python 3.9+, standard library only, `curl` for HTTP, `unittest`.

**Spec:** `docs/superpowers/specs/2026-08-26-five-area-short-report-design.md`

## Global Constraints

- Python standard library only. No pip installs. `curl` is the only external binary.
- Never write the Adjust token, Facebook client token, TikTok token, Discord webhook URL, or Sheet shared secret into any report, log line, or source file.
- `scripts/package_skill.py` zips the whole skill directory into partner repos. Anything placed in a source file ships to partners.
- The audit never modifies the audited app's source.
- Run tests from the repo root with `python3 -m unittest tests.test_run_audit`.
- All 51 existing tests pass before this work starts. Any test this plan does not explicitly rewrite must still pass at every commit.
- Vietnamese reason phrases are at most about eight words. Area reason caps at 120 characters, Note caps at 200 characters.
- Exit codes keep their current meaning: `0` no `FAIL`, `2` any `FAIL`, `1` invalid input.

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/area_rollup.py` | **Create.** `AreaResult`, `AreaReport`, the rule-to-area tables, the reason phrases, and `area_rollup()`. Pure: takes findings, returns a value object. No I/O. |
| `scripts/sheet_push.py` | **Create.** `build_row()` and `post_row()`. Owns the two-step Apps Script POST. No knowledge of findings. |
| `scripts/ads_audit_lib.py` | **Modify.** Add `BASE_PLACEMENT_KEYS`, `base_placement_keys()`, and four rules. Replace `render_summary` with the short form. Delete the MKT grouping helpers. |
| `scripts/run_audit.py` | **Modify.** Call the rollup, render one Discord message, push the Sheet row, add `--base-project` / `--sheet-url` / `--sheet-token`, write `ads-audit-findings.json`. |
| `tests/test_run_audit.py` | **Modify.** Extend both fixtures, add rollup and sheet unit tests, rewrite the nine tests that assert on the removed MKT payload. |
| `templates/apps-script-sheet.gs` | Already written and deployed. Not modified by this plan. |
| `references/report-schema.json` | **Rewrite** for `AreaReport` and the Sheet row. |

---

### Task 1: Repository setup and base key coverage

**Files:**
- Create: `.gitignore` (append if present)
- Modify: `scripts/ads_audit_lib.py`
- Modify: `scripts/run_audit.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ads_audit_lib.BASE_PLACEMENT_KEYS: tuple[str, ...]` — the 24 base keys.
  - `ads_audit_lib.base_placement_keys(base_project: str | Path | None = None) -> tuple[str, ...]`
  - `inspect_project(root, contract, checklist, overrides_path=None, base_project=None) -> AuditReport`
  - Rule ids `BASE_KEY_COVERAGE` (PASS/FAIL) and `BASE_KEY_EXTRA` (NEEDS_MAPPING only).

- [ ] **Step 1: Initialise the repository**

The skill directory is not a git repository, so no task in this plan can commit until it is one.

```bash
cd /home/infinity01/Skill/Infinity-ads-compliance-audit-main
git init
git add -A
git commit -m "chore: initial commit of existing skill"
```

- [ ] **Step 2: Add the ignore rules**

Create `.gitignore` at the repo root, or append these lines if the file already exists:

```gitignore
__pycache__/
*.pyc
*.pyo
ads-audit-output/
.pytest_cache/
infinity-ads-compliance-audit.zip
```

- [ ] **Step 3: Write the failing tests**

Add these four tests to `tests/test_run_audit.py` inside `class AdsAuditTest`:

```python
    def test_base_placement_keys_defaults_to_the_embedded_list(self):
        keys = ads_audit_lib.base_placement_keys()

        self.assertEqual(len(keys), 24)
        self.assertIn("inter_splash", keys)
        self.assertIn("reward_example", keys)

    def test_base_placement_keys_can_be_read_from_a_base_project(self):
        base = self.root / "base"
        assets = base / "app/src/main/assets"
        assets.mkdir(parents=True)
        (assets / "ad_config.json").write_text(
            json.dumps({"inter_splash": {"id": "x", "isEnable": True},
                        "banner_home": {"id": "y", "isEnable": True}}),
            encoding="utf-8",
        )

        self.assertEqual(ads_audit_lib.base_placement_keys(base), ("inter_splash", "banner_home"))

    def test_base_placement_keys_rejects_an_unreadable_base_project(self):
        with self.assertRaises(ValueError) as caught:
            ads_audit_lib.base_placement_keys(self.root / "no-such-base")

        self.assertIn("ad_config.json", str(caught.exception))

    def test_base_key_coverage_reports_missing_and_extra_keys(self):
        self.write_project()
        base = self.root / "base"
        assets = base / "app/src/main/assets"
        assets.mkdir(parents=True)
        (assets / "ad_config.json").write_text(
            json.dumps({"inter_splash": {}, "native_home": {}, "native_welcome": {}}),
            encoding="utf-8",
        )

        report = inspect_project(
            self.root,
            parse_ads_script(self.ads_csv),
            parse_working_file(self.working_csv),
            base_project=base,
        )

        coverage = report.finding("BASE_KEY_COVERAGE")
        self.assertEqual(coverage.status, "FAIL")
        self.assertIn("native_welcome", coverage.observed)
        self.assertNotIn("inter_splash", coverage.observed)
        self.assertFalse(any(f.rule_id == "BASE_KEY_EXTRA" for f in report.findings))
```

The project fixture writes `ad_config.json` with `inter_splash` and `native_home`, so a
base demanding `native_welcome` too must report exactly one missing key and no extras.

Add `import ads_audit_lib  # noqa: E402` to the import block at the top of the file,
below the existing `from ads_audit_lib import (...)`.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit -k base_placement -k base_key -v`
Expected: FAIL with `AttributeError: module 'ads_audit_lib' has no attribute 'base_placement_keys'`

- [ ] **Step 5: Add the base key list and reader**

In `scripts/ads_audit_lib.py`, after the `_KNOWN_AD_TYPES` block (around line 143), add:

```python
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
```

- [ ] **Step 6: Add the coverage check**

In `scripts/ads_audit_lib.py`, add these two functions immediately before
`_release_admob_app_id` (around line 1156):

```python
def _release_config_keys(root: Path) -> tuple[set[str], str | None] | None:
    """Return the release config's placement keys and its location, or None."""
    candidates = [path for path in _files(root, {".json"}) if path.name == "ad_config.json"]
    if not candidates:
        return None
    config = _config_data(candidates[0])
    if config is None:
        return None
    return set(config), str(candidates[0].relative_to(root))


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
```

- [ ] **Step 7: Wire the check into `inspect_project`**

In `scripts/ads_audit_lib.py`, change the `inspect_project` signature (line 1182) to:

```python
def inspect_project(root: str | Path, contract: AuditContract, checklist: ProjectChecklist, overrides_path: str | Path | None = None, base_project: str | Path | None = None) -> AuditReport:
```

Then, immediately after the existing `_check_config(report, root, contract, "ad_config.json", "RELEASE")` line (line 1208), add:

```python
    _check_base_key_coverage(report, root, base_placement_keys(base_project))
```

- [ ] **Step 8: Add the CLI flag**

In `scripts/run_audit.py`, add to `build_parser` after the `--overrides` argument:

```python
    parser.add_argument("--base-project", help="Infinity base checkout to read the placement key list from (default: the list bundled with this skill)")
```

Then change the `inspect_project` call inside the `try` block (line 226) to pass it:

```python
        report = inspect_project(project, parse_ads_script(ads_script), parse_working_file(working_file), args.overrides, args.base_project)
```

`base_placement_keys` raises `ValueError`, which the surrounding `except` clause already
catches and turns into an exit-1 setup error. No new error handling is needed.

- [ ] **Step 9: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 55 tests

- [ ] **Step 10: Commit**

```bash
git add scripts/ads_audit_lib.py scripts/run_audit.py tests/test_run_audit.py .gitignore
git commit -m "feat: compare app placement keys against the base key list"
```

---

### Task 2: `FLOW_LANGUAGE_OBSERVER_SWAP` rule

**Files:**
- Modify: `scripts/ads_audit_lib.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `_check_tokens`, `_source_by_class`, `_read` from `ads_audit_lib`.
- Produces: rule id `FLOW_LANGUAGE_OBSERVER_SWAP` (PASS/FAIL).

**Why this rule exists:** `LanguageActivity` swaps between two native observers and calls
`removeObservers` on the other one each time. Without that, both observers stay live and
the ad container flickers between two ads. Verified in the base at
`LanguageActivity.kt:121` and `:128`.

- [ ] **Step 1: Write the failing test**

```python
    def test_language_must_remove_the_other_native_observer_when_swapping(self):
        self.write_full_base_flow_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))
        self.assertEqual(report.finding("FLOW_LANGUAGE_OBSERVER_SWAP").status, "PASS")

        language = self.root / "app/src/main/java/com/example/LanguageActivity.kt"
        language.write_text(
            language.read_text(encoding="utf-8").replace(
                "AdsManager.nativeLanguageClickAdLive.removeObservers(this); ", ""
            ),
            encoding="utf-8",
        )
        broken = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        finding = broken.finding("FLOW_LANGUAGE_OBSERVER_SWAP")
        self.assertEqual(finding.status, "FAIL")
        self.assertIn("nativeLanguageClickAdLive.removeObservers", finding.observed)
```

The compliant fixture already contains both `removeObservers` calls, so the first
assertion passes without changing the fixture.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest tests.test_run_audit -k observer_swap -v`
Expected: FAIL with `StopIteration` from `report.finding`, because the rule does not exist yet

- [ ] **Step 3: Implement the rule**

In `scripts/ads_audit_lib.py`, inside `_check_screen_flow_rules`, immediately after the
existing `FLOW_LANGUAGE_PRELOAD_AND_RENDER` block (which ends around line 1010), add:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m unittest tests.test_run_audit -k observer_swap -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 56 tests

- [ ] **Step 6: Commit**

```bash
git add scripts/ads_audit_lib.py tests/test_run_audit.py
git commit -m "feat: require Language to remove the other native observer on swap"
```

---

### Task 3: `FLOW_ONBOARDING_PAGE_LIFECYCLE` rule

**Files:**
- Modify: `scripts/ads_audit_lib.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `_source_by_class`, `_read`, `_line_ref`, `Finding` from `ads_audit_lib`.
- Produces: rule id `FLOW_ONBOARDING_PAGE_LIFECYCLE` (PASS/FAIL, silent when the fragment does not observe at all).

**Why this rule exists:** `OnboardingPageFragment` lives inside a `ViewPager2`. Observing
with the fragment's own lifecycle instead of `viewLifecycleOwner` leaks observers across
page recycling. Verified in the base at `OnboardingPageFragment.kt:69`.

- [ ] **Step 1: Write the failing test**

```python
    def test_onboarding_page_must_observe_with_the_view_lifecycle_owner(self):
        self.write_full_base_flow_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))
        self.assertEqual(report.finding("FLOW_ONBOARDING_PAGE_LIFECYCLE").status, "PASS")

        page = self.root / "app/src/main/java/com/example/OnboardingPageFragment.kt"
        page.write_text(
            page.read_text(encoding="utf-8").replace("observe(viewLifecycleOwner)", "observe(this)"),
            encoding="utf-8",
        )
        broken = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        self.assertEqual(broken.finding("FLOW_ONBOARDING_PAGE_LIFECYCLE").status, "FAIL")

    def test_onboarding_page_lifecycle_rule_is_silent_without_the_fragment(self):
        self.write_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        self.assertFalse(any(f.rule_id == "FLOW_ONBOARDING_PAGE_LIFECYCLE" for f in report.findings))
```

The second test guards against double-reporting: a project with no onboarding page
fragment is already covered by `FLOW_ONBOARDING_PAGE_RENDERING`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit -k onboarding_page -v`
Expected: the first test FAILs with `StopIteration`; the second passes trivially

- [ ] **Step 3: Implement the rule**

In `scripts/ads_audit_lib.py`, inside `_check_screen_flow_rules`, immediately after the
existing `FLOW_ONBOARDING_PAGE_RENDERING` block (which ends around line 1038), add:

```python
    # Only meaningful once the fragment exists and observes something; a missing
    # fragment or a missing observe call is already FLOW_ONBOARDING_PAGE_RENDERING.
    if onboarding_page and ".observe(" in onboarding_page_text:
        if "observe(viewLifecycleOwner)" in onboarding_page_text:
            report.findings.append(Finding.pass_(
                "FLOW_ONBOARDING_PAGE_LIFECYCLE",
                "placement_flow",
                "onboarding page observes its ad LiveData with viewLifecycleOwner",
                "found",
                _line_ref(root, onboarding_page, "observe(viewLifecycleOwner)"),
            ))
        else:
            report.findings.append(Finding.fail(
                "FLOW_ONBOARDING_PAGE_LIFECYCLE",
                "placement_flow",
                "onboarding page observes its ad LiveData with viewLifecycleOwner",
                "observes with the fragment lifecycle instead",
                "Observe with `viewLifecycleOwner`; the fragment lifecycle leaks observers as ViewPager2 recycles pages.",
                _line_ref(root, onboarding_page, ".observe("),
            ))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_run_audit -k onboarding_page -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 58 tests

- [ ] **Step 6: Commit**

```bash
git add scripts/ads_audit_lib.py tests/test_run_audit.py
git commit -m "feat: require the onboarding page to observe with viewLifecycleOwner"
```

---

### Task 4: `FLOW_SPLASH_BANNER` rule

**Files:**
- Modify: `scripts/ads_audit_lib.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `_banner_evidence`, `_source_by_class`, `_line_ref`, `Finding`, `AuditContract`.
- Produces: rule id `FLOW_SPLASH_BANNER` (PASS/FAIL, silent when the contract omits `banner_splash`).

**Why this rule exists and why it is a FAIL:** the Infinity base defines `banner_splash`
in `ad_config.json` and `AdRemoteConfigExtensions.kt` but never loads it on any screen —
verified by grep against the base on 2026-08-26. Partner apps do show a splash banner, so
a contract that lists the key and a `SplashActivity` that never binds it is a real defect,
not a mapping gap. When the contract omits the key, the rule stays silent.

- [ ] **Step 1: Write the failing tests**

```python
    def _add_banner_splash_to_contract(self):
        self.ads_csv.write_text(
            self.ads_csv.read_text(encoding="utf-8").replace(
                ",,APP ID,ca-app-pub-123~999,\n",
                "3,banner,banner_splash,ca-app-pub-123/444,Banner on splash\n"
                ",,APP ID,ca-app-pub-123~999,\n",
            ),
            encoding="utf-8",
        )

    def test_splash_banner_is_silent_when_the_contract_omits_the_key(self):
        self.write_full_base_flow_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        self.assertFalse(any(f.rule_id == "FLOW_SPLASH_BANNER" for f in report.findings))

    def test_splash_banner_fails_when_the_contract_lists_it_but_splash_never_binds_it(self):
        self.write_full_base_flow_project()
        self._add_banner_splash_to_contract()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        finding = report.finding("FLOW_SPLASH_BANNER")
        self.assertEqual(finding.status, "FAIL")
        self.assertIn("banner_splash", finding.expected)

    def test_splash_banner_passes_when_splash_binds_the_key(self):
        self.write_full_base_flow_project()
        self._add_banner_splash_to_contract()
        splash = self.root / "app/src/main/java/com/example/SplashActivity.kt"
        splash.write_text(
            splash.read_text(encoding="utf-8").replace(
                "fun onResume(){",
                "val bannerConfig = BannerConfig(AdRemoteConfig.banner_splash, false); fun onResume(){",
            ),
            encoding="utf-8",
        )

        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        self.assertEqual(report.finding("FLOW_SPLASH_BANNER").status, "PASS")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit -k splash_banner -v`
Expected: the first test passes; the other two FAIL with `StopIteration`

- [ ] **Step 3: Implement the rule**

`_check_screen_flow_rules` does not currently receive the contract, so add the parameter.
Change its signature (line 950) to:

```python
def _check_screen_flow_rules(report: AuditReport, root: Path, source_paths: list[Path], contract: AuditContract) -> None:
```

Then, inside that function immediately after the `FLOW_SPLASH_OPEN_RESUME` block (which
ends around line 985), add:

```python
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
```

Finally update the call site in `inspect_project` (line 1277) to pass the contract:

```python
    _check_screen_flow_rules(report, root, source_paths, contract)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_run_audit -k splash_banner -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 61 tests

- [ ] **Step 6: Commit**

```bash
git add scripts/ads_audit_lib.py tests/test_run_audit.py
git commit -m "feat: require Splash to bind banner_splash when the contract lists it"
```

---

### Task 5: The area rollup module

**Files:**
- Create: `scripts/area_rollup.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `ads_audit_lib.Finding`.
- Produces:
  - `AreaResult(name: str, status: str, reason: str)` — frozen dataclass.
  - `AreaReport(app_name: str, package_name: str, audit_date: str, areas: list[AreaResult], note: str, overall: str)` — frozen dataclass.
  - `area_of(rule_id: str) -> str | None`
  - `area_rollup(findings: list[Finding], app_name: str, package_name: str, audit_date: str | None = None) -> AreaReport`

- [ ] **Step 1: Write the failing tests**

Add a second test class to `tests/test_run_audit.py`, after `class AdsAuditTest`:

```python
class AreaRollupTest(unittest.TestCase):
    def rollup(self, findings, **kwargs):
        return area_rollup.area_rollup(findings, "Demo Player", "com.example.player", "2026-08-26", **kwargs)

    def test_all_pass_rolls_up_to_five_done_areas(self):
        report = self.rollup([Finding.pass_("ARCH_GLOBAL_INIT_ORDER", "architecture", "x", "found")])

        self.assertEqual([area.name for area in report.areas],
                         ["Init", "Splash", "Language", "Onboarding", "Config"])
        self.assertEqual({area.status for area in report.areas}, {"Done"})
        self.assertEqual(report.overall, "Done")
        self.assertEqual(report.note, "")

    def test_a_fail_marks_only_its_own_area(self):
        report = self.rollup([Finding.fail("FLOW_LANGUAGE_OBSERVER_SWAP", "placement_flow", "x", "y", "fix")])

        statuses = {area.name: area.status for area in report.areas}
        self.assertEqual(statuses["Language"], "Error")
        self.assertEqual(statuses["Splash"], "Done")
        self.assertEqual(report.overall, "Error")

    def test_needs_mapping_and_runtime_proof_leave_the_area_done(self):
        report = self.rollup([
            Finding.needs_mapping("PLACEMENT_FLOW:inter_onboarding", "x", "y", "fix"),
            Finding.needs_runtime("RUNTIME:inter_splash", "x", "y", "fix"),
        ])

        self.assertEqual({area.status for area in report.areas}, {"Done"})
        self.assertEqual(report.overall, "Done")

    def test_error_reason_uses_the_short_vietnamese_phrase(self):
        report = self.rollup([Finding.fail("FLOW_LANGUAGE_OBSERVER_SWAP", "placement_flow", "x", "y", "fix")])

        language = next(area for area in report.areas if area.name == "Language")
        self.assertEqual(language.reason, "thiếu removeObservers")

    def test_config_failures_collapse_to_a_single_count_phrase(self):
        report = self.rollup([
            Finding.fail("AD_CONFIG_RELEASE:native_home", "ad_config", "x", "y", "fix"),
            Finding.fail("AD_CONFIG_RELEASE:inter_splash", "ad_config", "x", "y", "fix"),
            Finding.fail("AD_CONFIG_RELEASE:ENABLE:native_home", "ad_config", "x", "y", "fix"),
        ])

        config = next(area for area in report.areas if area.name == "Config")
        self.assertEqual(config.reason, "sai 3 key config")

    def test_out_of_scope_failures_land_in_the_note(self):
        report = self.rollup([Finding.fail("ARCH_BANNER_BASE_RELOAD", "architecture", "x", "y", "fix")])

        self.assertEqual({area.status for area in report.areas}, {"Done"})
        self.assertIn("banner", report.note)

    def test_note_is_capped_and_marked_when_truncated(self):
        findings = [
            Finding.fail(f"UNKNOWN_RULE_{index}", "architecture", "x", "y", "fix")
            for index in range(40)
        ]
        report = self.rollup(findings)

        self.assertLessEqual(len(report.note), 200)
        self.assertTrue(report.note.endswith("…"))

    def test_reason_is_capped_at_120_characters(self):
        findings = [
            Finding.fail(rule, "architecture", "x", "y", "fix")
            for rule in ("ARCH_GLOBAL_INIT_ORDER", "ARCH_DEV_CONFIG_INIT", "ARCH_DEV_CONFIG_BUILD_FIELDS",
                         "ARCH_ADS_CONFIG_FIELDS", "ARCH_APP_OPEN_EXCLUSIONS", "ARCH_MOBILE_ADS_INIT",
                         "ARCH_REMOTE_CONFIG_INIT", "ARCH_ERAIN_INIT", "ARCH_INTERSTITIAL_INTERVAL")
        ]
        report = self.rollup(findings)

        init = next(area for area in report.areas if area.name == "Init")
        self.assertLessEqual(len(init.reason), 120)

    def test_area_of_maps_placement_flow_rules_to_their_screen(self):
        self.assertEqual(area_rollup.area_of("PLACEMENT_FLOW:native_language_1"), "splash")
        self.assertEqual(area_rollup.area_of("PLACEMENT_FLOW:native_language_1_click"), "language")
        self.assertEqual(area_rollup.area_of("AD_CONFIG_RELEASE:ENABLE:native_home"), "config")
        self.assertIsNone(area_rollup.area_of("ARCH_BANNER_BASE_RELOAD"))

    def test_audit_date_defaults_to_today(self):
        report = area_rollup.area_rollup([], "Demo", "com.demo")

        self.assertRegex(report.audit_date, r"^\d{4}-\d{2}-\d{2}$")
```

`native_language_1` belongs to **Splash**, not Language: the base preloads it from
`SplashActivity`'s splash-interstitial `onAdLoaded` callback. `native_language_1_click`
belongs to Language, which is where it is loaded.

Add `import area_rollup  # noqa: E402` to the import block at the top of the file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit.AreaRollupTest -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'area_rollup'`

- [ ] **Step 3: Write the module**

Create `scripts/area_rollup.py`:

```python
#!/usr/bin/env python3
"""Collapse audit findings onto the five areas of the Infinity ads journey.

Marketing and QA need one line per area, not a hundred findings. This module is
pure: it takes the findings the engine produced and returns a small value object
that the Markdown, Discord, and Google Sheet renderers all read from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from ads_audit_lib import Finding


AREA_ORDER = ("init", "splash", "language", "onboarding", "config")

AREA_TITLES = {
    "init": "Init",
    "splash": "Splash",
    "language": "Language",
    "onboarding": "Onboarding",
    "config": "Config",
}

REASON_LIMIT = 120
NOTE_LIMIT = 200

# Exact rule id to area. A rule absent from every table here is out of scope and
# its failures go to the Note field instead.
RULE_AREA = {
    "ARCH_GLOBAL_INIT_ORDER": "init",
    "ARCH_DEV_CONFIG_INIT": "init",
    "ARCH_DEV_CONFIG_BUILD_FIELDS": "init",
    "ARCH_ADS_CONFIG_FIELDS": "init",
    "ARCH_APP_OPEN_EXCLUSIONS": "init",
    "ARCH_MOBILE_ADS_INIT": "init",
    "ARCH_REMOTE_CONFIG_INIT": "init",
    "ARCH_ERAIN_INIT": "init",
    "ARCH_INTERSTITIAL_INTERVAL": "init",
    "FLOW_INTER_WELCOME_BACK_REGISTRATION": "init",
    "FLOW_SPLASH_REMOTE_CONFIG": "splash",
    "FLOW_SPLASH_INTER_PRELOAD_LANGUAGE": "splash",
    "FLOW_SPLASH_OPEN_RESUME": "splash",
    "FLOW_SPLASH_BANNER": "splash",
    "FLOW_LANGUAGE_DEV_SETTING": "language",
    "FLOW_LANGUAGE_PRELOAD_AND_RENDER": "language",
    "FLOW_LANGUAGE_OBSERVER_SWAP": "language",
    "FLOW_ONBOARDING_PRELOAD_AND_SHOW": "onboarding",
    "FLOW_ONBOARDING_PAGE_RENDERING": "onboarding",
    "FLOW_ONBOARDING_PAGE_LIFECYCLE": "onboarding",
    "FLOW_INTER_ONBOARDING_SHOW": "onboarding",
    "ADMOB_APP_ID": "config",
    "ADMOB_MANIFEST_META": "config",
    "BASE_KEY_COVERAGE": "config",
    "BASE_KEY_EXTRA": "config",
}

# Placement key to area, for PLACEMENT_FLOW:<key> rules. native_language_* sits
# under Splash because the base preloads it from the splash interstitial's
# onAdLoaded callback, not from LanguageActivity.
PLACEMENT_AREA = {
    "inter_splash": "splash",
    "open_resume": "splash",
    "banner_splash": "splash",
    "native_language_1": "splash",
    "native_language_2": "splash",
    "native_language_1_click": "language",
    "native_language_2_click": "language",
    "native_onboarding_1_1": "language",
    "native_onboarding_2_1": "language",
    "native_onboarding_1_4": "onboarding",
    "native_onboarding_2_4": "onboarding",
    "native_onboarding_fullscreen_1_3": "onboarding",
    "native_onboarding_fullscreen_2_3": "onboarding",
    "native_onboarding_fullscreen_1_4": "onboarding",
    "native_onboarding_fullscreen_2_4": "onboarding",
    "inter_onboarding": "onboarding",
}

RULE_REASON = {
    "ARCH_GLOBAL_INIT_ORDER": "sai thứ tự init",
    "ARCH_DEV_CONFIG_INIT": "thiếu DevConfig.init",
    "ARCH_DEV_CONFIG_BUILD_FIELDS": "thiếu version field",
    "ARCH_ADS_CONFIG_FIELDS": "thiếu field ERainAdConfig",
    "ARCH_APP_OPEN_EXCLUSIONS": "thiếu loại trừ AppOpen",
    "ARCH_MOBILE_ADS_INIT": "thiếu MobileAds.initialize",
    "ARCH_REMOTE_CONFIG_INIT": "thiếu AdRemoteConfig",
    "ARCH_ERAIN_INIT": "thiếu ERainAd.init",
    "ARCH_INTERSTITIAL_INTERVAL": "interval inter khác 35",
    "FLOW_INTER_WELCOME_BACK_REGISTRATION": "chưa đăng ký lifecycle observer",
    "FLOW_SPLASH_REMOTE_CONFIG": "chưa lấy RemoteConfig",
    "FLOW_SPLASH_INTER_PRELOAD_LANGUAGE": "sai preload native language",
    "FLOW_SPLASH_OPEN_RESUME": "chưa cấu hình open_resume",
    "FLOW_SPLASH_BANNER": "chưa load banner splash",
    "FLOW_LANGUAGE_DEV_SETTING": "thiếu DevSetting",
    "FLOW_LANGUAGE_PRELOAD_AND_RENDER": "sai load hoặc render native",
    "FLOW_LANGUAGE_OBSERVER_SWAP": "thiếu removeObservers",
    "FLOW_ONBOARDING_PRELOAD_AND_SHOW": "sai preload hoặc show inter",
    "FLOW_ONBOARDING_PAGE_RENDERING": "sai map LiveData cho page",
    "FLOW_ONBOARDING_PAGE_LIFECYCLE": "observe sai lifecycle owner",
    "FLOW_INTER_ONBOARDING_SHOW": "thiếu nhánh else onAction",
    "ADMOB_APP_ID": "sai AdMob App ID",
    "ADMOB_MANIFEST_META": "thiếu meta-data AdMob",
    "BASE_KEY_COVERAGE": "thiếu key so với base",
    "PLACEMENT_FLOW": "chưa gắn placement",
}

# Out-of-scope rules keep a phrase too, because their failures are summarised in
# the Note field rather than dropped.
NOTE_REASON = {
    "APP_NAME": "sai app_name",
    "APP_PACKAGE": "sai package",
    "FIREBASE_PROJECT": "sai Firebase project",
    "ARCH_ADS_MANAGER": "thiếu AdsManager",
    "ARCH_ADS_MANAGER_NATIVE_GATES": "AdsManager thiếu gate native",
    "ARCH_ADS_MANAGER_UA_GATES": "sai gate UA",
    "ARCH_ADS_MANAGER_INTER_GATES": "AdsManager thiếu gate inter",
    "ARCH_ADS_MANAGER_BANNER": "AdsManager thiếu loadBanner",
    "ARCH_ENABLE_GATE": "thiếu gate isEnable",
    "ARCH_PURCHASE_GATE": "thiếu gate purchase",
    "ARCH_NETWORK_GATE": "thiếu gate network",
    "ARCH_UA_GATE": "thiếu gate enableUaCheck",
    "ARCH_DIRECT_SDK_BYPASS": "gọi SDK trực tiếp",
    "ARCH_PRIMARY_SCREENS_ACTIVITY": "màn chính dùng Fragment",
    "ARCH_BANNER_BASE_RELOAD": "banner chưa theo base",
    "FLOW_RESUME_RULE": "sai luồng resume",
    "FLOW_WELCOME_NATIVE_AND_INTER": "sai luồng Welcome",
    "FLOW_INTER_WELCOME_SHOW": "Welcome thiếu else onAction",
    "FLOW_INTER_WELCOME_BACK_OBSERVER": "sai observer welcome back",
    "FLOW_INTER_WELCOME_BACK_LOAD_SHOW": "sai load/show welcome back",
    "FLOW_INTER_WELCOME_BACK_MANAGER": "AdsManager thiếu inter welcome",
    "WEBHOOK_DELIVERY": "gửi Discord lỗi",
    "SHEET_DELIVERY": "ghi Google Sheet lỗi",
}


@dataclass(frozen=True)
class AreaResult:
    name: str
    status: str
    reason: str


@dataclass(frozen=True)
class AreaReport:
    app_name: str
    package_name: str
    audit_date: str
    areas: list[AreaResult]
    note: str
    overall: str


def area_of(rule_id: str) -> str | None:
    """Return the area a rule belongs to, or None when it is out of scope."""
    if rule_id in RULE_AREA:
        return RULE_AREA[rule_id]
    if rule_id.startswith("AD_CONFIG_RELEASE:"):
        return "config"
    if rule_id.startswith("PLACEMENT_FLOW:"):
        return PLACEMENT_AREA.get(rule_id.split(":", 1)[1])
    return None


def _note_phrase(rule_id: str) -> str:
    if rule_id in NOTE_REASON:
        return NOTE_REASON[rule_id]
    if rule_id.startswith("TOKEN:"):
        return "thiếu token dịch vụ"
    if rule_id.startswith("PLACEMENT_FLOW:"):
        return f"chưa gắn {rule_id.split(':', 1)[1]}"
    return rule_id.split(":", 1)[0].lower()


def _join_capped(phrases: Iterable[str], limit: int) -> str:
    """Join unique phrases with '; ', truncating with an ellipsis at the limit."""
    unique = list(dict.fromkeys(phrase for phrase in phrases if phrase))
    joined = ""
    for phrase in unique:
        candidate = phrase if not joined else f"{joined}; {phrase}"
        if len(candidate) > limit:
            return f"{joined}…" if joined else phrase[: limit - 1] + "…"
        joined = candidate
    return joined


def _area_reason(rule_ids: list[str]) -> str:
    """Build one area's reason text, collapsing config key failures to a count."""
    config_failures = sum(1 for rule_id in rule_ids if rule_id.startswith("AD_CONFIG_RELEASE:"))
    phrases = []
    if config_failures:
        phrases.append(f"sai {config_failures} key config")
    for rule_id in rule_ids:
        if rule_id.startswith("AD_CONFIG_RELEASE:"):
            continue
        if rule_id.startswith("PLACEMENT_FLOW:"):
            phrases.append(f"chưa gắn {rule_id.split(':', 1)[1]}")
            continue
        phrases.append(RULE_REASON.get(rule_id, rule_id.lower()))
    return _join_capped(phrases, REASON_LIMIT)


def area_rollup(
    findings: list[Finding],
    app_name: str,
    package_name: str,
    audit_date: str | None = None,
) -> AreaReport:
    """Collapse findings onto the five journey areas.

    Only a FAIL makes an area Error. NEEDS_MAPPING and NEEDS_RUNTIME_PROOF mean
    static analysis could not settle the claim, which is not the same as the app
    being wrong; treating them as failures would mark nearly every app red.
    """
    failures: dict[str, list[str]] = {area: [] for area in AREA_ORDER}
    out_of_scope: list[str] = []

    for finding in findings:
        if finding.status != "FAIL":
            continue
        area = area_of(finding.rule_id)
        if area is None:
            out_of_scope.append(finding.rule_id)
        else:
            failures[area].append(finding.rule_id)

    areas = [
        AreaResult(
            name=AREA_TITLES[area],
            status="Error" if failures[area] else "Done",
            reason=_area_reason(failures[area]) if failures[area] else "",
        )
        for area in AREA_ORDER
    ]

    return AreaReport(
        app_name=app_name,
        package_name=package_name,
        audit_date=audit_date or date.today().isoformat(),
        areas=areas,
        note=_join_capped((_note_phrase(rule_id) for rule_id in out_of_scope), NOTE_LIMIT),
        overall="Error" if any(area.status == "Error" for area in areas) else "Done",
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_run_audit.AreaRollupTest -v`
Expected: PASS, 10 tests

- [ ] **Step 5: Write the end-to-end test over the compliant fixture**

The unit tests above prove the tables; this one proves the rollup against findings the
real engine produced. Add it to `class AdsAuditTest`:

```python
    def test_compliant_base_project_rolls_up_to_five_done_areas(self):
        self.write_full_base_flow_project()
        # The fixture ships two config keys; the coverage rule wants all 24.
        config_path = self.root / "app/src/main/assets/ad_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for key in ads_audit_lib.BASE_PLACEMENT_KEYS:
            config.setdefault(key, {"id": f"ca-app-pub-123/{key}", "isEnable": True})
        config_path.write_text(json.dumps(config), encoding="utf-8")
        # banner_splash is in the contract, so Splash must bind it.
        self._add_banner_splash_to_contract()
        splash = self.root / "app/src/main/java/com/example/SplashActivity.kt"
        splash.write_text(
            splash.read_text(encoding="utf-8").replace(
                "fun onResume(){",
                "val bannerConfig = BannerConfig(AdRemoteConfig.banner_splash, false); fun onResume(){",
            ),
            encoding="utf-8",
        )

        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))
        rolled = area_rollup.area_rollup(report.findings, "Demo Player", "com.example.player", "2026-08-26")

        errors = {area.name: area.reason for area in rolled.areas if area.status == "Error"}
        self.assertEqual(errors, {})
        self.assertEqual(rolled.overall, "Done")
```

`_add_banner_splash_to_contract` is the helper added in Task 4.

If this test fails, the failing area's `reason` names the rule. Either the fixture is
genuinely missing base behaviour — fix the fixture — or a rule is mapped to the wrong
area in `RULE_AREA` / `PLACEMENT_AREA` — fix the table. Do not weaken the assertion.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 72 tests

- [ ] **Step 7: Commit**

```bash
git add scripts/area_rollup.py tests/test_run_audit.py
git commit -m "feat: add the five-area rollup over audit findings"
```

---

### Task 6: Short Markdown summary and the findings dump

**Files:**
- Modify: `scripts/ads_audit_lib.py`
- Modify: `scripts/run_audit.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `area_rollup.AreaReport`, `area_rollup.area_rollup` from Task 5.
- Produces:
  - `ads_audit_lib.render_summary(report: AuditReport, area_report: AreaReport) -> str` — signature changes; the area report is now required.
  - `ads_audit_lib.findings_payload(report: AuditReport) -> list[dict]`
  - `ads-audit-findings.json` replaces `ads-audit-evidence.json`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_summary_leads_with_the_five_area_table(self):
        self.write_full_base_flow_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))
        rolled = area_rollup.area_rollup(report.findings, "Demo Player", "com.example.player", "2026-08-26")

        summary = render_summary(report, rolled)

        self.assertIn("| Init |", summary)
        self.assertIn("| Splash |", summary)
        self.assertIn("| Config |", summary)
        self.assertIn("Demo Player", summary)
        self.assertIn("2026-08-26", summary)
        self.assertLess(len(summary.splitlines()), 120)

    def test_summary_never_contains_secret_values(self):
        self.write_full_base_flow_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))
        rolled = area_rollup.area_rollup(report.findings, "Demo Player", "com.example.player", "2026-08-26")

        summary = render_summary(report, rolled)

        self.assertNotIn("adjust-secret", summary)
        self.assertNotIn("facebook-client-secret", summary)
        self.assertNotIn("tiktok-secret", summary)

    def test_findings_payload_carries_every_finding_field(self):
        self.write_project()
        report = inspect_project(self.root, parse_ads_script(self.ads_csv), parse_working_file(self.working_csv))

        payload = ads_audit_lib.findings_payload(report)

        self.assertEqual(len(payload), len(report.findings))
        self.assertEqual(
            set(payload[0]),
            {"rule_id", "category", "status", "expected", "observed", "recommendation", "location"},
        )

    def test_cli_writes_findings_json_instead_of_evidence_json(self):
        self.write_project()
        output_dir = self.root / "audit-output"
        script = SCRIPTS_DIR / "run_audit.py"

        result = subprocess.run(
            [sys.executable, str(script), "--project", str(self.root),
             "--ads-script", str(self.ads_csv), "--working-file", str(self.working_csv),
             "--output-dir", str(output_dir), "--no-webhook"],
            text=True, capture_output=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertTrue((output_dir / "ads-audit-summary.md").is_file())
        self.assertFalse((output_dir / "ads-audit-evidence.json").exists())
        findings = (output_dir / "ads-audit-findings.json").read_text(encoding="utf-8")
        self.assertNotIn("facebook-client-secret", findings)
```

Then **delete** `test_cli_writes_sanitized_reports_even_when_audit_fails` (currently at
line 548). The new `test_cli_writes_findings_json_instead_of_evidence_json` replaces it
and keeps the same secret-leak assertion.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit -k summary_leads -k findings_payload -k findings_json -v`
Expected: FAIL — `render_summary` takes one argument, `findings_payload` does not exist

- [ ] **Step 3: Replace `render_summary` and add the findings dump**

In `scripts/ads_audit_lib.py`, replace the whole of `render_summary` (lines 1594 to the
end of the file) with:

```python
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
```

Also **delete** these now-unused functions from `ads_audit_lib.py`: `_mkt_error`,
`_mkt_area_for_finding`, `_mkt_detail_for_area`, `_limited_list`, `_config_key`,
`_group_mkt_errors`, `_group_mkt_confirmations`, and `build_webhook_payload` (lines 1286
through 1591). Task 7 removes the last callers of `build_webhook_payload`; if the suite
complains about it during this task, leave `build_webhook_payload` in place and delete it
in Task 7 instead.

Add the import at the top of `ads_audit_lib.py`, below the existing imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoids a circular import at runtime; area_rollup imports Finding
    from area_rollup import AreaReport
```

- [ ] **Step 4: Update `run_audit.py`**

In `scripts/run_audit.py`, change the import line (line 14) to:

```python
from ads_audit_lib import Finding, findings_payload, inspect_project, parse_ads_script, parse_working_file, render_summary
from area_rollup import area_rollup
```

Then replace the report-writing block in `main` (lines 230 to 234) with:

```python
    area_report = area_rollup(report.findings, checklist_name(report), checklist_package(report))
    summary_path = output_dir / "ads-audit-summary.md"
    findings_path = output_dir / "ads-audit-findings.json"
    summary_path.write_text(render_summary(report, area_report), encoding="utf-8")
    findings_path.write_text(json.dumps(findings_payload(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

Add these two helpers above `main` in `run_audit.py`:

```python
def checklist_name(report) -> str:
    return report.checklist.app_name or Path(report.project_root).name


def checklist_package(report) -> str:
    return report.checklist.package_name or "<chưa tìm thấy>"
```

Finally change the two closing print lines (lines 257 to 258) to:

```python
    print(f"Summary: {summary_path}")
    print(f"Findings: {findings_path}")
```

Leave the webhook block between them alone for now; Task 7 rewrites it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_run_audit -k summary_leads -k summary_never -k findings_payload -k findings_json -v`
Expected: PASS, 4 tests

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: several MKT payload tests FAIL — this is expected and Task 7 fixes them. Confirm the failures are limited to: `test_redacts_secret_values_and_payload_never_contains_them`, `test_webhook_identity_error_includes_expected_and_observed_values`, `test_mkt_webhook_names_app_and_explains_primary_fragment_error`, `test_mkt_payload_groups_duplicate_findings_and_keeps_original_counts`, `test_mkt_payload_groups_base_flow_errors_by_area_without_duplicate_titles`, `test_discord_report_can_split_long_audit_into_multiple_messages`, `test_webhook_posts_summary_markdown_as_discord_attachment`, `test_cli_posts_to_embedded_webhook_by_default`. Any other failure is a real regression — fix it before continuing.

- [ ] **Step 7: Commit**

```bash
git add scripts/ads_audit_lib.py scripts/run_audit.py tests/test_run_audit.py
git commit -m "feat: replace the long summary with the five-area short form"
```

---

### Task 7: One short Discord message

**Files:**
- Modify: `scripts/run_audit.py`
- Modify: `scripts/ads_audit_lib.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `area_rollup.AreaReport` from Task 5.
- Produces: `run_audit.discord_message(area_report: AreaReport) -> dict`.
- Removes: `run_audit.discord_message_payloads`, `run_audit.discord_message_payload`, `run_audit._discord_error_block`, `run_audit._fit_discord_block`, and `ads_audit_lib.build_webhook_payload`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_discord_message_lists_the_five_areas_on_one_line_each(self):
        rolled = area_rollup.AreaReport(
            app_name="Demo Player",
            package_name="com.example.player",
            audit_date="2026-08-26",
            areas=[
                area_rollup.AreaResult("Init", "Done", ""),
                area_rollup.AreaResult("Splash", "Done", ""),
                area_rollup.AreaResult("Language", "Error", "thiếu removeObservers"),
                area_rollup.AreaResult("Onboarding", "Done", ""),
                area_rollup.AreaResult("Config", "Error", "sai 3 key config"),
            ],
            note="banner chưa theo base",
            overall="Error",
        )

        message = run_audit.discord_message(rolled)
        content = message["content"]

        self.assertEqual(message["allowed_mentions"], {"parse": []})
        self.assertIn("🚨", content)
        self.assertIn("Demo Player", content)
        self.assertIn("com.example.player", content)
        self.assertIn("Language", content)
        self.assertIn("thiếu removeObservers", content)
        self.assertIn("Khác: banner chưa theo base", content)
        self.assertLess(len(content), 2000)

    def test_discord_message_uses_the_pass_icon_and_drops_an_empty_note(self):
        rolled = area_rollup.AreaReport(
            app_name="Demo", package_name="com.demo", audit_date="2026-08-26",
            areas=[area_rollup.AreaResult(name, "Done", "")
                   for name in ("Init", "Splash", "Language", "Onboarding", "Config")],
            note="", overall="Done",
        )

        content = run_audit.discord_message(rolled)["content"]

        self.assertIn("✅", content)
        self.assertNotIn("Khác:", content)

    def test_cli_posts_one_message_without_an_attachment(self):
        self.write_project()
        output_dir = self.root / "audit-output"
        with patch.object(run_audit, "post_webhook", return_value=None) as post:
            result = run_audit.main([
                "--project", str(self.root),
                "--ads-script", str(self.ads_csv),
                "--working-file", str(self.working_csv),
                "--output-dir", str(output_dir),
            ])

        self.assertEqual(result, 2)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], run_audit.DEFAULT_WEBHOOK_URL)
        content = post.call_args.args[2]["content"]
        self.assertIn("Demo Player", content)
        self.assertIn("com.example.player", content)
        self.assertNotIn("adjust-secret", content)
        self.assertIsNone(post.call_args.kwargs.get("attachment_path"))
```

Then **delete** these eight now-obsolete tests, all of which assert on the removed MKT
payload or the removed multi-message Discord path:

1. `test_redacts_secret_values_and_payload_never_contains_them`
2. `test_webhook_identity_error_includes_expected_and_observed_values`
3. `test_cli_posts_to_embedded_webhook_by_default`
4. `test_mkt_webhook_names_app_and_explains_primary_fragment_error`
5. `test_mkt_payload_groups_duplicate_findings_and_keeps_original_counts`
6. `test_mkt_payload_groups_base_flow_errors_by_area_without_duplicate_titles`
7. `test_discord_report_can_split_long_audit_into_multiple_messages`
8. `test_webhook_posts_summary_markdown_as_discord_attachment`

Secret-leak coverage is not lost: `test_summary_never_contains_secret_values` from Task 6
and `test_cli_posts_one_message_without_an_attachment` above both assert it.

Remove `build_webhook_payload` from the `from ads_audit_lib import (...)` block at the top
of the test file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit -k discord_message -k posts_one_message -v`
Expected: FAIL with `AttributeError: module 'run_audit' has no attribute 'discord_message'`

- [ ] **Step 3: Write the renderer**

In `scripts/run_audit.py`, delete `_discord_error_block`, `_fit_discord_block`,
`discord_message_payloads`, and `discord_message_payload` (lines 150 to 213) and put this
in their place:

```python
def discord_message(area_report) -> dict:
    """Render the whole audit as one short Discord message.

    Five areas, one line each. The summary file stays on disk rather than being
    attached, because the areas are what people act on.
    """
    icon = "✅" if area_report.overall == "Done" else "🚨"
    width = max(len(area.name) for area in area_report.areas)
    lines = [
        f"{icon} **Ads Audit — {area_report.app_name}**",
        f"`{area_report.package_name}`",
        "",
    ]
    for area in area_report.areas:
        suffix = f": {area.reason}" if area.status == "Error" and area.reason else ""
        lines.append(f"{area.name.ljust(width)} → {area.status}{suffix}")
    if area_report.note:
        lines.extend(["", f"Khác: {area_report.note}"])
    return {"content": "\n".join(lines), "allowed_mentions": {"parse": []}}
```

- [ ] **Step 4: Rewrite the webhook block in `main`**

Replace the webhook block in `main` (lines 241 to 256) with:

```python
    if webhook_url:
        error = post_webhook(webhook_url, args.webhook_token, discord_message(area_report))
        if error:
            report.findings.append(Finding.needs_runtime("WEBHOOK_DELIVERY", "successful webhook delivery", error, "Check the configured Discord webhook, TLS, authorization and network, then rerun the audit."))
            area_report = area_rollup(report.findings, checklist_name(report), checklist_package(report))
            summary_path.write_text(render_summary(report, area_report), encoding="utf-8")
            findings_path.write_text(json.dumps(findings_payload(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
```

`post_webhook` keeps its current signature and behaviour, so its four existing tests still
pass. It is now called once with no attachment.

- [ ] **Step 5: Delete the dead payload builder**

If `build_webhook_payload` and its helpers were left in `ads_audit_lib.py` at the end of
Task 6, delete them now: `_mkt_error`, `_mkt_area_for_finding`, `_mkt_detail_for_area`,
`_limited_list`, `_config_key`, `_group_mkt_errors`, `_group_mkt_confirmations`, and
`build_webhook_payload`.

Verify nothing still references them:

```bash
grep -rn "build_webhook_payload\|_group_mkt\|_mkt_area_for_finding\|discord_message_payload" scripts tests
```

Expected: no output.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 70 tests

- [ ] **Step 7: Commit**

```bash
git add scripts/run_audit.py scripts/ads_audit_lib.py tests/test_run_audit.py
git commit -m "feat: send one short five-area Discord message"
```

---

### Task 8: Google Sheet row push

**Files:**
- Create: `scripts/sheet_push.py`
- Modify: `scripts/run_audit.py`
- Test: `tests/test_run_audit.py`

**Interfaces:**
- Consumes: `area_rollup.AreaReport` from Task 5.
- Produces:
  - `sheet_push.build_row(area_report: AreaReport, token: str | None) -> dict`
  - `sheet_push.post_row(url: str, payload: dict, timeout: int = 30) -> str | None` — `None` on success, an error string otherwise.
  - `run_audit.DEFAULT_SHEET_URL: str`
  - CLI flags `--sheet-url`, `--sheet-token`, `--no-sheet`.

**Transport note:** Apps Script answers a POST with a `302` to a one-time
`script.googleusercontent.com` URL holding the JSON reply. `curl -L` fails on it
consistently — three consecutive attempts against the live deployment on 2026-08-26 each
returned a Google Drive "file not found" page. The push therefore POSTs without
`--location`, reads `%{redirect_url}`, and GETs that URL separately.

- [ ] **Step 1: Write the failing tests**

```python
class SheetPushTest(unittest.TestCase):
    def area_report(self):
        return area_rollup.AreaReport(
            app_name="Demo Player",
            package_name="com.example.player",
            audit_date="2026-08-26",
            areas=[
                area_rollup.AreaResult("Init", "Done", ""),
                area_rollup.AreaResult("Splash", "Done", ""),
                area_rollup.AreaResult("Language", "Error", "thiếu removeObservers"),
                area_rollup.AreaResult("Onboarding", "Done", ""),
                area_rollup.AreaResult("Config", "Error", "sai 3 key config"),
            ],
            note="banner chưa theo base",
            overall="Error",
        )

    def test_row_carries_exactly_the_documented_fields(self):
        row = sheet_push.build_row(self.area_report(), "secret-token")

        self.assertEqual(
            set(row),
            {"token", "package", "app_name", "date", "init", "splash",
             "language", "onboarding", "config", "note"},
        )
        self.assertEqual(row["package"], "com.example.player")
        self.assertEqual(row["date"], "2026-08-26")
        self.assertEqual(row["language"], "Error")
        self.assertEqual(row["init"], "Done")

    def test_row_note_merges_the_area_reasons_and_the_note(self):
        row = sheet_push.build_row(self.area_report(), None)

        self.assertIn("thiếu removeObservers", row["note"])
        self.assertIn("sai 3 key config", row["note"])
        self.assertIn("banner chưa theo base", row["note"])

    def test_post_row_reads_the_reply_behind_the_redirect(self):
        posted = subprocess.CompletedProcess([], 0, b"302 https://script.googleusercontent.com/echo?k=1", b"")
        replied = subprocess.CompletedProcess([], 0, b'{"ok":true,"row":7}', b"")
        with patch.object(sheet_push.subprocess, "run", side_effect=[posted, replied]) as run:
            result = sheet_push.post_row("https://script.google.com/macros/s/x/exec", {"package": "com.x"})

        self.assertIsNone(result)
        post_command = run.call_args_list[0].args[0]
        self.assertNotIn("--location", post_command)
        self.assertIn("https://script.googleusercontent.com/echo?k=1", run.call_args_list[1].args[0])

    def test_post_row_surfaces_an_apps_script_rejection(self):
        posted = subprocess.CompletedProcess([], 0, b"302 https://script.googleusercontent.com/echo?k=1", b"")
        replied = subprocess.CompletedProcess([], 0, b'{"ok":false,"error":"unauthorized"}', b"")
        with patch.object(sheet_push.subprocess, "run", side_effect=[posted, replied]):
            result = sheet_push.post_row("https://script.google.com/macros/s/x/exec", {})

        self.assertIn("unauthorized", result)

    def test_post_row_never_echoes_the_endpoint_or_stderr(self):
        url = "https://script.google.com/macros/s/SECRET-ID/exec"
        with patch.object(sheet_push.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 7, b"", b"contains SECRET-ID")):
            result = sheet_push.post_row(url, {})

        self.assertEqual(result, "curl exited with code 7")
        self.assertNotIn("SECRET-ID", result)

    def test_post_row_reports_missing_curl_and_timeouts(self):
        with patch.object(sheet_push.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(sheet_push.post_row("https://x/exec", {}), "curl is not installed")
        with patch.object(sheet_push.subprocess, "run", side_effect=subprocess.TimeoutExpired("curl", 30)):
            self.assertEqual(sheet_push.post_row("https://x/exec", {}), "curl timed out")
```

Add to `class AdsAuditTest`:

```python
    def test_cli_pushes_a_sheet_row_when_a_token_is_configured(self):
        self.write_project()
        with patch.object(run_audit, "post_webhook", return_value=None), \
             patch.object(run_audit, "post_row", return_value=None) as push:
            run_audit.main([
                "--project", str(self.root),
                "--ads-script", str(self.ads_csv),
                "--working-file", str(self.working_csv),
                "--output-dir", str(self.root / "audit-output"),
                "--sheet-token", "secret-token",
            ])

        push.assert_called_once()
        self.assertEqual(push.call_args.args[0], run_audit.DEFAULT_SHEET_URL)
        self.assertEqual(push.call_args.args[1]["token"], "secret-token")

    def test_cli_skips_the_sheet_push_without_a_token(self):
        self.write_project()
        with patch.object(run_audit, "post_webhook", return_value=None), \
             patch.object(run_audit, "post_row", return_value=None) as push:
            run_audit.main([
                "--project", str(self.root),
                "--ads-script", str(self.ads_csv),
                "--working-file", str(self.working_csv),
                "--output-dir", str(self.root / "audit-output"),
            ])

        push.assert_not_called()

    def test_sheet_delivery_failure_becomes_a_finding_without_leaking_the_url(self):
        self.write_project()
        output_dir = self.root / "audit-output"
        with patch.object(run_audit, "post_webhook", return_value=None), \
             patch.object(run_audit, "post_row", return_value="HTTP 500"):
            run_audit.main([
                "--project", str(self.root),
                "--ads-script", str(self.ads_csv),
                "--working-file", str(self.working_csv),
                "--output-dir", str(output_dir),
                "--sheet-token", "secret-token",
            ])

        summary = (output_dir / "ads-audit-summary.md").read_text(encoding="utf-8")
        self.assertIn("SHEET_DELIVERY", summary)
        self.assertNotIn("secret-token", summary)
```

Add `import sheet_push  # noqa: E402` to the import block at the top of the test file.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_run_audit.SheetPushTest -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sheet_push'`

- [ ] **Step 3: Write the module**

Create `scripts/sheet_push.py`:

```python
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
    """Append the row. Returns None on success, or a sanitized error string.

    Error strings never carry the endpoint, the shared secret, or curl's stderr,
    because they end up in a report that other people read.
    """
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
    return f"Apps Script rejected the row: {parsed.get('error', 'unknown')}"
```

- [ ] **Step 4: Wire it into `run_audit.py`**

Add the endpoint constant beside the existing `DEFAULT_WEBHOOK_URL` (line 18):

```python
# The Apps Script Web App bound to the Infinity audit spreadsheet. Safe to embed:
# the script rejects any request without the matching shared secret, which is
# deliberately NOT stored here — package_skill.py ships this file to partners.
DEFAULT_SHEET_URL = "https://script.google.com/macros/s/AKfycbyKxCaMNLKZPlQRGr37QcWbcut-EkkKvazqqsFeKrOstcygchWBjMmNu3uy2ckJNUUyJg/exec"
```

Add the import beside the others:

```python
from sheet_push import build_row, post_row
```

Add the flags in `build_parser`:

```python
    parser.add_argument("--sheet-url", help="Apps Script Web App endpoint for the audit spreadsheet")
    parser.add_argument("--sheet-token", help="Shared secret for the Apps Script endpoint; never written to output")
    parser.add_argument("--no-sheet", action="store_true", help="Do not append a row to the audit spreadsheet")
```

Then add this block in `main`, immediately after the Discord webhook block from Task 7 and
before the closing `print` lines:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_run_audit.SheetPushTest -v`
Expected: PASS, 6 tests

Run: `python3 -m unittest tests.test_run_audit -k sheet -v`
Expected: PASS

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest tests.test_run_audit`
Expected: OK, 79 tests

- [ ] **Step 7: Verify against the live deployment**

This is the only step that touches the real sheet. Run it once, then delete the row it
adds.

```bash
cd /home/infinity01/Skill/Infinity-ads-compliance-audit-main
ADS_AUDIT_SHEET_TOKEN=<sheet-secret> python3 scripts/run_audit.py \
  --project /home/infinity01/StudioProjects/TestSill \
  --ads-script <path to an ADS SCRIPTS csv> \
  --working-file <path to a working checklist csv> \
  --output-dir /tmp/claude-1000/base-audit \
  --no-webhook
```

Expected: no `SHEET_DELIVERY` line in `/tmp/claude-1000/base-audit/ads-audit-summary.md`,
and one new row in the spreadsheet. Tell the operator which row to delete.

If the two CSVs are not available, skip this step and say so; the unit tests already cover
the transport, and step 6 is the gate that matters.

- [ ] **Step 8: Commit**

```bash
git add scripts/sheet_push.py scripts/run_audit.py tests/test_run_audit.py
git commit -m "feat: append each audit result to the Google Sheet log"
```

---

### Task 9: Documentation and schema

**Files:**
- Modify: `references/report-schema.json`
- Modify: `SKILL.md`
- Modify: `README.md`, `README.vi.md`, `README.hi.md`
- Modify: `references/base-integration-rules.md`

**Interfaces:**
- Consumes: everything from Tasks 1 to 8. Produces no code.

- [ ] **Step 1: Rewrite the report schema**

Replace `references/report-schema.json` with:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Infinity Ads Audit area report and sheet row",
  "type": "object",
  "required": ["app_name", "package_name", "audit_date", "areas", "note", "overall"],
  "properties": {
    "app_name": {"type": "string"},
    "package_name": {"type": "string"},
    "audit_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "overall": {"enum": ["Done", "Error"]},
    "note": {"type": "string", "maxLength": 200},
    "areas": {
      "type": "array",
      "minItems": 5,
      "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["name", "status", "reason"],
        "properties": {
          "name": {"enum": ["Init", "Splash", "Language", "Onboarding", "Config"]},
          "status": {"enum": ["Done", "Error"]},
          "reason": {"type": "string", "maxLength": 120}
        }
      }
    }
  },
  "$defs": {
    "sheetRow": {
      "type": "object",
      "required": ["package", "app_name", "date", "init", "splash", "language", "onboarding", "config", "note"],
      "properties": {
        "token": {"type": "string", "description": "Apps Script shared secret; never stored in the repository"},
        "package": {"type": "string"},
        "app_name": {"type": "string"},
        "date": {"type": "string"},
        "init": {"enum": ["Done", "Error"]},
        "splash": {"enum": ["Done", "Error"]},
        "language": {"enum": ["Done", "Error"]},
        "onboarding": {"enum": ["Done", "Error"]},
        "config": {"enum": ["Done", "Error"]},
        "note": {"type": "string"}
      }
    }
  }
}
```

- [ ] **Step 2: Update `SKILL.md`**

Replace the `## Webhook` section and the `## Partner-facing result format` section with:

````markdown
## Reporting

The audit reports five areas of the ads journey, each `Done` or `Error`:

| Area | Covers |
| --- | --- |
| **Init** | `GlobalApp` init order, DevConfig fields, `ERainAdConfig`, AppOpen exclusions, interstitial interval, lifecycle observer registration |
| **Splash** | RemoteConfig, `inter_splash`, `banner_splash`, `open_resume`, and the native-language preload from `onAdLoaded` |
| **Language** | DevSetting, native click load, onboarding page-1 preload, observer swap with `removeObservers`, render and hide |
| **Onboarding** | Preloads, page LiveData mapping, `viewLifecycleOwner`, and the interstitial before Home |
| **Config** | Release `ad_config.json` keys and IDs, AdMob app id, and coverage against the base's own key list |

An area is `Error` only when it has a `FAIL`. `NEEDS_MAPPING` and
`NEEDS_RUNTIME_PROOF` never turn an area red — they mean static analysis could
not settle the claim, not that the app is wrong.

Failures outside the five areas — Welcome/Resume, Banner, service tokens,
Firebase, direct SDK calls — are summarised in a single Note line. They still set
the exit code to `2`.

Three outputs:

- `ads-audit-output/ads-audit-summary.md` — the five-area table plus each failure.
- `ads-audit-output/ads-audit-findings.json` — every finding, for deep debugging.
- One Discord message, and one row appended to the audit spreadsheet.

### Discord

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

Disable with `--no-webhook`. Override with `--webhook-url` or
`ADS_AUDIT_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL`.

### Audit spreadsheet

One row per audit: `STT | Package | App name | Ngày | Init | Splash | Language | Onboarding | Config | Note`.

The endpoint is embedded; the shared secret is not. Set `ADS_AUDIT_SHEET_TOKEN`
or pass `--sheet-token`, otherwise the push is skipped with a note on stderr.
Disable with `--no-sheet`. `templates/apps-script-sheet.gs` is the receiving
script.

## Partner-facing result format

Reply in the partner's language, in this shape:

```text
Init       → Done
Splash     → Done
Language   → Error: thiếu removeObservers
Onboarding → Done
Config     → Error: thiếu 3 key

Khác: <một dòng>
```

Add `file:line` for each `Error` only when the partner asks for detail. Never
output raw Adjust, Facebook client, TikTok, webhook, or sheet secret values.
````

Also add `--base-project` to the command examples in the `## Run the audit` section:

```bash
python3 "/absolute/path/to/this-skill/scripts/run_audit.py" --project . \
  --base-project /home/infinity01/StudioProjects/TestSill
```

- [ ] **Step 3: Update the three READMEs**

In `README.md`, replace the `## What gets checked`, `## Output`, and `## Discord webhook`
sections with exactly this:

````markdown
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

Disable per-run with `--no-webhook`. Override the endpoint with `--webhook-url`
or the `ADS_AUDIT_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` environment variables.

## Audit spreadsheet

Each audit appends one row:

`STT | Package | App name | Ngày | Init | Splash | Language | Onboarding | Config | Note`

The rows arrive through a Google Apps Script Web App bound to the spreadsheet;
`templates/apps-script-sheet.gs` is the script to paste into it.

The endpoint is embedded in the skill. **The shared secret is not** — this skill
gets packaged into partner repositories, so the secret would travel with it. Set
it yourself:

```bash
export ADS_AUDIT_SHEET_TOKEN=<the secret configured in the Apps Script>
```

Without it the push is skipped with a note on stderr and the audit still
succeeds. Disable it outright with `--no-sheet`, or point somewhere else with
`--sheet-url` / `ADS_AUDIT_SHEET_URL`.
````

Then translate the same content into `README.vi.md` and `README.hi.md`, replacing their
corresponding sections. Keep each file entirely in its own language — do not leave English
prose in the Vietnamese or Hindi file. The `Done` / `Error` status words, the rule ids,
the CLI flags, the environment variable names, and the Discord example block stay verbatim
in all three.

- [ ] **Step 4: Document the new rule ids**

In `references/base-integration-rules.md`, add these four entries to the
`## Pipeline rule ids` list:

```markdown
- `FLOW_LANGUAGE_OBSERVER_SWAP`
- `FLOW_ONBOARDING_PAGE_LIFECYCLE`
- `FLOW_SPLASH_BANNER`
- `BASE_KEY_COVERAGE` / `BASE_KEY_EXTRA`
```

Then correct the `## Optional placements` section: `banner_splash` is no longer treated as
an optional unmapped placement when the contract lists it. Replace its mention with:

```markdown
`native_home`, `native_permission`, `native_onboarding_fullscreen_*_4`, and
`reward_example` are provided by `AdsManager` in the base but are not wired to a
screen there. When the contract lists one and no screen calls it, that is
`NEEDS_MAPPING`, not a failure.

`banner_splash` is different. The base defines it in `ad_config.json` but wires
it to no screen, while partner apps do show a splash banner. When the contract
lists `banner_splash` and `SplashActivity` never binds it, `FLOW_SPLASH_BANNER`
reports `FAIL`.
```

- [ ] **Step 5: Verify the documentation matches the code**

```bash
cd /home/infinity01/Skill/Infinity-ads-compliance-audit-main
grep -rn "ads-audit-evidence.json" . --include=*.md --include=*.py --include=*.js --include=*.json
```

Expected: no output. Every mention of the old evidence file must be gone.

```bash
python3 -m unittest tests.test_run_audit
```

Expected: OK, 79 tests

- [ ] **Step 6: Commit**

```bash
git add SKILL.md README.md README.vi.md README.hi.md references/
git commit -m "docs: describe the five-area report and the spreadsheet push"
```
