**Language / Ngôn ngữ / भाषा:** [English](README.md) | [Tiếng Việt](README.vi.md) | [हिन्दी](README.hi.md)

# Infinity Ads Compliance Audit

Skill cho **Claude Code** và **Codex**, dùng để kiểm tra phần gắn quảng cáo của
một app Android so với project base Infinity và 2 tài liệu hợp đồng của chính
app đó. Skill chỉ đọc project, không sửa code.

Cài một lần, sau đó nhờ AI kiểm tra bất kỳ project Android nào.

## Cài đặt

```bash
git clone https://github.com/Infinity-Technologies-Global/Infinity-ads-compliance-audit.git
cd Infinity-ads-compliance-audit
./install.sh          # macOS / Linux
.\install.ps1         # Windows PowerShell
```

Script tự nhận diện các agent có trên máy và copy skill vào từng chỗ:

| Host | Vị trí | Gọi bằng |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/` | `/infinity-ads-compliance-audit` |
| Codex CLI | `$CODEX_HOME/skills/` (mặc định `~/.codex/skills/`) | `$infinity-ads-compliance-audit` |
| Antigravity / Gemini | `~/.gemini/antigravity/skills/` | nhắn bằng lời bình thường |

Codex đọc skill ở `$CODEX_HOME/skills`, **không phải** `~/.agents/skills`. Script
cài vào cả hai nên Codex bản cũ vẫn chạy được.

Muốn cài cho riêng một repo thì clone vào
`<project>/.claude/skills/infinity-ads-compliance-audit/` (hoặc `.agents/skills/`).
Cài xong nhớ khởi động lại agent để nó nạp skill.

Yêu cầu: Python 3.9 trở lên và `curl`. Không cần cài thư viện Python nào.

## Cách dùng

Đứng ở thư mục gốc project Android.

**Claude Code** — chạy `claude`, rồi gõ:

```text
/infinity-ads-compliance-audit

Kiểm tra project này. Tài liệu:
  ADS SCRIPTS:  https://docs.google.com/spreadsheets/d/.../edit#gid=0
  Checklist:    https://docs.google.com/document/d/.../edit
Không sửa code. Trả lời bằng tiếng Việt.
```

**Codex CLI** — chạy `codex`, rồi dùng dấu `$`:

```text
$infinity-ads-compliance-audit

Kiểm tra project này. Tài liệu:
  ADS SCRIPTS:  https://docs.google.com/spreadsheets/d/.../edit#gid=0
  Checklist:    https://docs.google.com/document/d/.../edit
Không sửa code. Trả lời bằng tiếng Việt.
```

Cả hai đều có thể tự chọn skill khi bạn chỉ mô tả công việc ("kiểm tra tuân thủ
ads cho project này"). Gõ `/` hoặc `$` là cách chắc chắn nhất.

Nếu 2 file CSV đã nằm sẵn trong project thì bỏ hẳn phần Tài liệu — skill tự tìm.

AI sẽ chạy auditor, đọc các báo cáo local, rồi đối chiếu từng lỗi với code thật.
Việc gửi Discord hoặc bảng tính là tùy chọn và cần cấu hình rõ ràng.

### Hai tài liệu đầu vào

| Tài liệu | Chứa gì |
| --- | --- |
| **ADS SCRIPTS** | key vị trí, loại quảng cáo, ad-unit ID, AdMob APP ID |
| **Working checklist** | tên app, package, Firebase project, token Adjust/Facebook/TikTok |

Mỗi tài liệu có thể là file CSV trên máy, hoặc **link Google Sheets / Google
Docs**. Sheets được export sang CSV; Docs được đọc theo các dòng dạng
`nhãn: giá trị`. Nhớ để link ở chế độ *bất kỳ ai có link đều xem được*, nếu
không bản tải về sẽ là trang đăng nhập và audit dừng lại kèm thông báo lỗi chia
sẻ.

Nếu 2 file CSV đã nằm sẵn trong project thì skill tự tìm — một file có tên chứa
`ADS SCRIPTS`, một file chứa `working` hoặc `work file`. Khi không tìm thấy hoặc
tìm thấy nhiều file, skill dừng và yêu cầu chỉ rõ, không bao giờ đoán.

File của mỗi đối tác không cần cùng một layout. Parser xử lý được dấu phân cách
phẩy/chấm phẩy/tab/gạch đứng, tiêu đề tiếng Anh lẫn tiếng Việt, vài dòng thừa
phía trên header thật, và các alias thường gặp. Khi tên cột lạ, nó đoán cột dựa
trên nội dung — package name, URL Firebase, loại quảng cáo, ad-unit ID. Alias
khai báo rõ luôn được ưu tiên, và nếu hai cột có độ tin cậy ngang nhau thì audit
**dừng lại và báo**, thay vì chấm nhầm dữ liệu.

### Tài liệu được xin như thế nào

Skill không bao giờ audit khi thiếu tài liệu, và không bao giờ đoán. Nó đi lần
lượt theo 3 tầng:

| Tầng | Tình huống | Điều xảy ra |
| --- | --- | --- |
| **1** | 2 file CSV đã có sẵn trong project | Tự tìm thấy. Bạn không bị hỏi gì cả. |
| **2** | Thiếu tài liệu và chưa đưa link | AI hỏi xin cả 2 tài liệu — link hoặc file — **trước khi** chạy bất cứ thứ gì. |
| **3** | Có link nhưng không có quyền truy cập | Audit dừng và đưa 2 cách gỡ: đổi chế độ chia sẻ, hoặc tải file về rồi đưa đường dẫn. |

Nếu qua tầng 3 vẫn không có tài liệu, audit **dừng hẳn và báo rõ**. Nó sẽ không
xuất báo cáo nửa vời, không bịa ad-unit ID, không lấy giá trị của project base
thay thế — một bản audit thiếu dữ liệu nhưng trông như kết luận thì tệ hơn là
không audit.

Phần tự tìm file cũng không đoán bừa: không thấy file nào, hoặc thấy nhiều file
cùng lúc, đều rơi xuống tầng 2 chứ không tự chọn một cái.

## Kiểm tra những gì

Báo cáo bao phủ năm khu vực của hành trình quảng cáo. Mỗi khu vực là `Done` hoặc
`Error`.

| Khu vực | Bao gồm |
| --- | --- |
| **Init** | Thứ tự khởi tạo `GlobalApp`, các trường phiên bản của DevConfig, các trường `ERainAdConfig`, danh sách loại trừ AppOpen, khoảng thời gian quảng cáo xen kẽ 35 giây, đăng ký bộ quan sát vòng đời |
| **Splash** | Tải và áp dụng RemoteConfig, `inter_splash`, `banner_splash`, `open_resume`, và tải trước quảng cáo gốc của Language từ `onAdLoaded` của quảng cáo xen kẽ Splash |
| **Language** | DevSetting trên tiêu đề, tải quảng cáo gốc khi nhấp, tải trước trang Onboarding 1, chuyển đổi bằng `removeObservers` giữa hai bộ quan sát quảng cáo gốc, hiển thị và ẩn khi `null` |
| **Onboarding** | Tải trước quảng cáo gốc trang 4, quảng cáo gốc toàn màn hình và `inter_onboarding`, ánh xạ LiveData của trang, quan sát bằng `viewLifecycleOwner`, và quảng cáo xen kẽ trước Home |
| **Config** | Khóa và ID `ad_config.json` bản phát hành so với ADS SCRIPTS, mã ứng dụng AdMob từ `manifestPlaceholders` bản **phát hành**, và mức bao phủ 24 khóa của dự án cơ sở |

Một khu vực chỉ thành `Error` khi một kiểm tra thực sự `FAIL`. `NEEDS_MAPPING` và
`NEEDS_RUNTIME_PROOF` không bao giờ làm khu vực đỏ — chúng chỉ có nghĩa phân tích
tĩnh chưa thể kết luận, không phải ứng dụng sai.

Mọi nội dung khác vẫn được kiểm tra — Welcome/Resume, Banner, mã thông báo dịch
vụ, Firebase, tên ứng dụng và tên gói, lời gọi SDK trực tiếp — được tóm tắt trong
một dòng Note. Các lỗi đó vẫn đặt mã thoát thành `2`.

Truyền `--base-project /path/to/base` để đọc danh sách 24 khóa từ bản sao mã
nguồn của dự án cơ sở thay vì bản sao đi kèm bộ kỹ năng này.

## Kết quả

Ghi vào `ads-audit-output/` bên trong dự án được kiểm tra:

- `ads-audit-summary.md` — bảng năm khu vực, sau đó là từng lỗi cùng `file:line`.
- `ads-audit-findings.json` — mọi phát hiện, để gỡ lỗi chuyên sâu.

Lệnh trả về `0` khi không có lỗi, `2` khi bất kỳ kiểm tra nào lỗi, và `1` khi đầu
vào không hợp lệ.

Báo cáo che giá trị Adjust, mã ứng dụng khách Facebook và TikTok. Chúng không bao giờ gồm
kiểm tra `app-ads.txt`.

## Vị trí quảng cáo riêng

Nếu một vị trí trả về `NEEDS_MAPPING`, sao chép `templates/ads-audit-overrides.yaml`
vào ứng dụng rồi khai báo lớp và lời gọi đã được duyệt, giữ nguyên khóa và ID trong
hợp đồng. Một số vị trí — `native_home`, `native_permission`,
`native_onboarding_fullscreen_*_4`, `reward_example` — có sẵn
trong `AdsManager` nhưng dự án cơ sở không gắn vào màn nào, nên được xếp ở đây theo thiết kế.

## Điểm nhận Discord (tùy chọn)

Mỗi lần kiểm tra gửi một tin nhắn ngắn, không có tệp đính kèm:

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

Việc gửi Discord chỉ được bật khi cấu hình rõ ràng. Đặt điểm cuối bằng
`--webhook-url` hoặc biến môi trường `ADS_AUDIT_WEBHOOK_URL` /
`DISCORD_WEBHOOK_URL`. Nếu không có, auditor chỉ giữ báo cáo cục bộ. Dùng
`--no-webhook` để bỏ qua cấu hình được kế thừa từ môi trường.

## Bảng tính kiểm tra

Mỗi lần kiểm tra thêm một hàng vào bảng tính kiểm tra dùng chung của Infinity:

`STT | Package | App name | Ngày | Init | Splash | Language | Onboarding | Config | Note`

Không cần cấu hình gì. Bộ kỹ năng nhúng sẵn cả URL Google Apps Script Web App lẫn
bí mật dùng chung, nên skill đã cài sẽ tự ghi log mỗi lần chạy. Bí mật này chỉ
ghi được — chỉ thêm một hàng vào tab `Audit Log`, không đọc/sửa/xóa được gì.

Muốn gửi đi nơi khác thì ghi đè:

- `--sheet-url` / `ADS_AUDIT_SHEET_URL` — điểm cuối;
- `--sheet-token` / `ADS_AUDIT_SHEET_TOKEN` / file `scripts/.sheet-token` — bí mật.

`templates/apps-script-sheet.gs` là tập lệnh nhận đã triển khai, để tái tạo hoặc
xoay vòng bí mật. Dùng `--no-sheet` để bỏ hẳn thao tác gửi; việc kiểm tra vẫn
thành công và vẫn ghi báo cáo cục bộ.

## Chạy auditor trực tiếp

Dùng cho CI hoặc khi cần debug; cách chuẩn vẫn là gọi qua AI ở trên.

```bash
python3 scripts/run_audit.py --project /duong/dan/app --no-webhook --no-sheet
python3 scripts/run_audit.py --project . \
  --no-webhook --no-sheet \
  --ads-script "https://docs.google.com/spreadsheets/d/<id>/edit#gid=0" \
  --working-file "./working file.csv"
```

## Đóng gói cho repo đối tác

```bash
python3 scripts/package_skill.py --skill-root . --output infinity-ads-audit.zip
```

## Tài liệu tham chiếu

- `references/base-code-reference.md` — code base thật: Gradle, `GlobalApp`,
  `AdsManager`, từng màn hình, các gate, schema config.
- `references/base-integration-rules.md` — cùng bộ rule ở dạng checklist.
- `references/placement-rule-map.yaml` — bằng chứng được duyệt cho từng vị trí.
