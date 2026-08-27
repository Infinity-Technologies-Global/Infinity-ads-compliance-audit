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
            return (joined or phrase)[: limit - 1] + "…"
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
