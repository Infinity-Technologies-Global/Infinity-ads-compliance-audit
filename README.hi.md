**Language / Ngôn ngữ / भाषा:** [English](README.md) | [Tiếng Việt](README.vi.md) | [हिन्दी](README.hi.md)

# Infinity Ads Compliance Audit

**Claude Code** और **Codex** के लिए एक agent skill, जो किसी Android app के
Infinity ads integration को base project और उस app के अपने contract documents
के विरुद्ध जाँचती है। यह audit project को सिर्फ़ पढ़ती है; source code कभी नहीं
बदलती।

एक बार install कीजिए, फिर किसी भी Android project की जाँच AI से करवाइए।

## Install

```bash
git clone https://github.com/Infinity-Technologies-Global/Infinity-ads-compliance-audit.git
cd Infinity-ads-compliance-audit
./install.sh          # macOS / Linux
.\install.ps1         # Windows PowerShell
```

Installer मशीन पर मौजूद agents को पहचानता है और skill को हर एक में copy कर देता
है:

| Host | जगह | कैसे बुलाएँ |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `/infinity-ads-compliance-audit` |
| Codex CLI | `$CODEX_HOME/skills/` (default `~/.codex/skills/`) | `$infinity-ads-compliance-audit` |
| Antigravity / Gemini | `~/.gemini/antigravity/skills/` | सामान्य भाषा में कहिए |

Codex skills को `$CODEX_HOME/skills` से पढ़ता है, `~/.agents/skills` से **नहीं**।
Installer दोनों जगह लिखता है, ताकि पुराना Codex भी चलता रहे।

पूरी मशीन के बजाय सिर्फ़ एक repository में install करना हो तो
`<project>/.claude/skills/infinity-ads-compliance-audit/` (या `.agents/skills/`)
में clone कीजिए। उसके बाद agent को restart कीजिए ताकि नई skill load हो जाए।

ज़रूरत: Python 3.9+ और `curl`. कोई Python package install नहीं करना पड़ता —
सिर्फ़ standard library।

## इस्तेमाल

Android project की root से चलाइए।

**Claude Code** — `claude` शुरू कीजिए, फिर:

```text
/infinity-ads-compliance-audit

इस project की जाँच कीजिए। Documents:
  ADS SCRIPTS:  https://docs.google.com/spreadsheets/d/.../edit#gid=0
  Checklist:    https://docs.google.com/document/d/.../edit
Source मत बदलिए। जवाब हिन्दी में दीजिए।
```

**Codex CLI** — `codex` शुरू कीजिए, फिर `$` sigil लगाइए:

```text
$infinity-ads-compliance-audit

इस project की जाँच कीजिए। Documents:
  ADS SCRIPTS:  https://docs.google.com/spreadsheets/d/.../edit#gid=0
  Checklist:    https://docs.google.com/document/d/.../edit
Source मत बदलिए। जवाब हिन्दी में दीजिए।
```

दोनों hosts काम का ब्यौरा देने भर से भी skill खुद चुन लेते हैं ("इस project का
ads compliance check करो")। `/` या `$` लिखना सिर्फ़ पक्का करने के लिए है।

अगर दोनों CSV files पहले से project में हैं, तो Documents वाला हिस्सा हटा
दीजिए — वे अपने आप मिल जाती हैं।

Agent bundled auditor चलाता है, बनी हुई reports पढ़ता है, हर finding को code से
मिलाकर देखता है, और sanitized report Discord पर भेज देता है — जब तक आप
local-only run न माँगें।

### दो documents

| Document | इसमें क्या होता है |
| --- | --- |
| **ADS SCRIPTS** | placement key, ad type, ad-unit ID, AdMob APP ID |
| **working checklist** | app name, package, Firebase project, Adjust/Facebook/TikTok tokens |

हर एक या तो local CSV हो सकता है, या **Google Sheets / Google Docs link**।
Sheets को CSV के रूप में export किया जाता है; Docs को `label: value` पंक्तियों
की तरह पढ़ा जाता है। Link की sharing *anyone with the link → Viewer* रखिए, वरना
download में sign-in page आ जाता है और audit sharing error के साथ रुक जाती है।

अगर दोनों documents पहले से project के अंदर CSV हैं, तो वे अपने आप मिल जाती
हैं — एक filename में `ADS SCRIPTS`, दूसरे में `working` या `work file`। शून्य
या एक से ज़्यादा matches मिलने पर discovery कभी अंदाज़ा नहीं लगाती।

Partner की spreadsheet का layout तय नहीं होना चाहिए। Parser comma, semicolon,
tab और pipe delimiters, अंग्रेज़ी और वियतनामी column labels, असली header से पहले
की title rows, और आम aliases सँभाल लेता है। Headers अनजाने हों तो वह पहचानने
योग्य values से column का अनुमान लगाता है — package names, Firebase URLs, ad
formats, ad-unit IDs। स्पष्ट alias हमेशा जीतता है, और अगर दो columns बराबर के
संभावित हों तो audit ग़लत data जाँचने के बजाय **रुककर बताती है**।

### Documents कैसे माँगे जाते हैं

Skill दोनों documents के बिना कभी audit नहीं करती, और कभी अंदाज़ा नहीं लगाती।
यह तीन स्तरों पर काम करती है:

| स्तर | स्थिति | क्या होता है |
| --- | --- | --- |
| **1** | दोनों CSV पहले से project में हैं | अपने आप मिल जाती हैं। आपसे कुछ नहीं पूछा जाता। |
| **2** | नहीं हैं, और कोई link भी नहीं दिया | Agent कुछ भी चलाने से **पहले** दोनों documents माँगता है — link हो या file। |
| **3** | Link दिया गया पर access नहीं है | Audit रुक जाती है और दो रास्ते देती है: link sharing बदलिए, या file download करके उसका path दीजिए। |

स्तर 3 के बाद भी document न मिले तो audit **रुक जाती है और यह साफ़ बता देती है**।
वह अधूरी report नहीं बनाएगी, ad-unit ID नहीं गढ़ेगी, और base project की values
पर वापस नहीं जाएगी — फ़ैसले जैसी दिखने वाली आधी-अधूरी audit, बिना audit से भी
ख़राब है।

Discovery उम्मीदवारों के बीच भी अंदाज़ा नहीं लगाती: शून्य matches हों या कई,
दोनों हालात में यह किसी एक को चुनने के बजाय स्तर 2 पर चली जाती है।

## क्या-क्या जाँचा जाता है

रिपोर्ट विज्ञापन यात्रा के पाँच क्षेत्रों को कवर करती है। हर क्षेत्र `Done` या
`Error` होता है।

| क्षेत्र | शामिल है |
| --- | --- |
| **Init** | `GlobalApp` का आरंभीकरण क्रम, DevConfig के संस्करण क्षेत्र, `ERainAdConfig` क्षेत्र, AppOpen बहिष्करण, 35 सेकंड का अंतरालीय विज्ञापन अंतराल और जीवनचक्र पर्यवेक्षक का पंजीकरण |
| **Splash** | RemoteConfig को लोड और लागू करना, `inter_splash`, `banner_splash`, `open_resume`, और Splash अंतरालीय विज्ञापन के `onAdLoaded` से Language मूल विज्ञापन को पहले लोड करना |
| **Language** | शीर्षक पर DevSetting, क्लिक पर मूल विज्ञापन को लोड करना, Onboarding पृष्ठ 1 को पहले लोड करना, दो मूल विज्ञापन पर्यवेक्षकों के बीच `removeObservers` बदलाव, और `null` पर दिखाना या छिपाना |
| **Onboarding** | मूल विज्ञापन पृष्ठ 4, पूरे-पर्दे वाले मूल विज्ञापन और `inter_onboarding` को पहले लोड करना, पृष्ठ का LiveData मानचित्रण, `viewLifecycleOwner` से अवलोकन और Home से पहले अंतरालीय विज्ञापन |
| **Config** | ADS SCRIPTS के विरुद्ध रिलीज़ `ad_config.json` की कुंजियाँ और IDs, **रिलीज़** `manifestPlaceholders` से AdMob ऐप पहचान, और आधार परियोजना की अपनी 24 कुंजियों का आवरण |

कोई क्षेत्र केवल तभी `Error` बनता है जब कोई जाँच सीधे `FAIL` हो।
`NEEDS_MAPPING` और `NEEDS_RUNTIME_PROOF` किसी क्षेत्र को लाल नहीं करते — उनका
मतलब है कि स्थिर विश्लेषण दावे को तय नहीं कर सका, यह नहीं कि ऐप गलत है।

बाकी जाँची जाने वाली बातें — Welcome/Resume, Banner, सेवा टोकन, Firebase,
ऐप का नाम और पैकेज, सीधे SDK कॉल — एक Note पंक्ति में संक्षेपित होती हैं। वे
त्रुटियाँ भी निकास कोड को `2` करती हैं।

शामिल प्रति के बजाय आधार परियोजना की स्रोत प्रति से 24 कुंजियों की सूची पढ़ने के लिए
`--base-project /path/to/base` दें।

## नतीजा

जाँचे गए परियोजना के अंदर `ads-audit-output/` में लिखा जाता है:

- `ads-audit-summary.md` — पाँच क्षेत्रों की तालिका, फिर `file:line` के साथ हर त्रुटि।
- `ads-audit-findings.json` — गहरी जाँच के लिए हर निष्कर्ष।

कमांड में त्रुटि न होने पर `0`, किसी भी जाँच के विफल होने पर `2`, और अमान्य
इनपुट पर `1` लौटता है।

रिपोर्टें Adjust, Facebook के क्लाइंट मान और TikTok मान छिपाती हैं। इनमें
`app-ads.txt` की जाँच कभी नहीं होती।

## अपने विज्ञापन स्थान

अगर कोई विज्ञापन स्थान `NEEDS_MAPPING` लौटाए, तो `templates/ads-audit-overrides.yaml`
को ऐप में प्रतिलिपि बनाइए और स्वीकृत वर्ग व कॉल मानचित्रण जोड़िए — अनुबंध की कुंजी
और ID बिलकुल वैसी ही रखिए। कुछ विज्ञापन स्थान — `native_home`, `native_permission`,
`native_onboarding_fullscreen_*_4`, `reward_example` —
`AdsManager` में मौजूद तो हैं, पर आधार परियोजना में किसी स्क्रीन से जुड़े नहीं हैं, इसलिए
इनका यहाँ आना अपेक्षित है।

## Discord वेबहुक

हर जाँच के लिए एक छोटा संदेश भेजा जाता है, कोई संलग्नक नहीं:

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

एक बार चलाने के लिए `--no-webhook` से बंद कीजिए। अंत बिंदु बदलने के लिए
`--webhook-url` या `ADS_AUDIT_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` पर्यावरण चर
इस्तेमाल करें।

## जाँच की स्प्रेडशीट

हर जाँच एक पंक्ति जोड़ती है:

`STT | Package | App name | Ngày | Init | Splash | Language | Onboarding | Config | Note`

पंक्तियाँ स्प्रेडशीट से बंधे Google Apps Script Web App तक पहुँचती हैं;
`templates/apps-script-sheet.gs` उसमें चिपकाई जाने वाली स्क्रिप्ट है।

अंत बिंदु कौशल में अंतर्निहित है। **साझा गुप्त मान नहीं है** — यह कौशल साझेदार
रिपॉज़िटरी में पैक किया जाता है, इसलिए गुप्त मान भी साथ चला जाएगा। इसे खुद
निर्धारित कीजिए:

```bash
export ADS_AUDIT_SHEET_TOKEN=<Apps Script में कॉन्फ़िगर किया हुआ गुप्त मान>
```

इसके बिना भेजना stderr पर एक टिप्पणी के साथ छोड़ा जाता है और जाँच फिर भी सफल
होती है। पूरी तरह बंद करने के लिए `--no-sheet`, या दूसरी जगह भेजने के लिए
`--sheet-url` / `ADS_AUDIT_SHEET_URL` इस्तेमाल करें।

## Auditor सीधे चलाना

CI या debugging के लिए उपयोगी; ऊपर बताया गया AI वाला रास्ता ही असल तरीक़ा है।

```bash
python3 scripts/run_audit.py --project /path/to/app --no-webhook
python3 scripts/run_audit.py --project . \
  --ads-script "https://docs.google.com/spreadsheets/d/<id>/edit#gid=0" \
  --working-file "./working file.csv"
```

## Partner repo के लिए package बनाना

```bash
python3 scripts/package_skill.py --skill-root . --output infinity-ads-audit.zip
```

## संदर्भ

- `references/base-code-reference.md` — base implementation, code में: Gradle,
  `GlobalApp`, `AdsManager`, हर screen, gates, config schema।
- `references/base-integration-rules.md` — वही नियम checklist के रूप में।
- `references/placement-rule-map.yaml` — हर placement के लिए स्वीकृत evidence।
