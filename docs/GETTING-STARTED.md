# Hướng dẫn cài đặt và sử dụng (cho người mới)

Tài liệu này dành cho người lần đầu chạy hệ thống. Nó chỉ nói **làm gì, theo thứ tự nào, và kiểm tra thế nào**. Lý do thiết kế nằm ở `docs/architecture/SYSTEM-DESIGN.md`; luật giao dịch nằm trong `knowledge/`. Khi tài liệu này và các file đó khác nhau, các file đó đúng.

---

## 1. Hệ thống này làm gì

Một hệ thống ra quyết định giao dịch chạy trong Claude Code, gồm ba phần:

| Phần | Việc | Chạy ở đâu |
|---|---|---|
| **Phân tích** | Đọc thị trường theo Wyckoff + ICT + Footprint + Heatmap, chấm điểm, ra kết luận TRADE / WAIT / NO_TRADE | Lệnh `/analyze`, `/bias`, `/entry` trong Claude |
| **Tự động hoá nền** | Scanner quét nến mỗi phút, đọc cục bộ, và **pilot** tự đặt lệnh theo luật cứng | launchd trên máy Mac, bật tắt bằng `/automation` |
| **Nhật ký và cải tiến** | Ghi mọi lệnh vào `trades/`, review sau khi đóng, đề xuất cải tiến có kiểm soát | `/journal`, `/review`, `/improve` |

**Luật cứng, không có ngoại lệ ở bất kỳ môi trường nào:**

- Không bao giờ giao dịch Forex.
- Chỉ các mã trong `docs/architecture/instruments.json` — **một nguồn duy nhất**, đừng chép danh sách đi đâu khác. File có hai danh sách: `analysis` (được quét và phân tích) và `execution` (được đặt lệnh, luôn là tập con). Mã chỉ nằm trong `analysis` = **chỉ theo dõi**, không bao giờ vào pilot hay `/execute`. Thêm/bớt mã: sửa file đó rồi chạy `python3 scripts/sync-instruments.py --write`.
- Rủi ro tối đa **1% vốn mỗi lệnh**. Loader tự kẹp xuống 1% nếu file cấu hình ghi cao hơn.

---

## 2. Hai môi trường: demo và real

| | `demo` | `real` |
|---|---|---|
| Tiền | Giả (Binance Testnet) | **Thật** (Binance Mainnet) |
| File | `config/env.demo` | `config/env.real` |
| Trạng thái ban đầu | Sẵn sàng, trỏ vào key testnet trong Keychain | Có chỗ trống `__FILL_ME__`, phải tự điền |

Công tắc chọn môi trường là một dòng trong `docs/architecture/automation-config.json`:

```json
"execution": { "environment": "demo" }
```

Đổi bằng tay, hoặc gõ `/automation demo` / `/automation real`. Mọi script đặt lệnh đọc dòng này ở mỗi lần gọi, nên đổi xong là có hiệu lực ngay ở tick kế tiếp.

**Chừng nào `config/env.real` còn `__FILL_ME__` thì không gì đặt được lệnh thật.** Đây là kiểm tra đúng sai chứ không phải luật cấm, và nó là lưới an toàn duy nhất giữa mày và tiền thật. Đừng điền cho đến khi thật sự muốn chạy.

---

## 3. Cài đặt lần đầu

### 3.1 Cần có

- macOS, `python3`, `curl`, Claude Code.
- Tài khoản Binance Testnet (miễn phí): https://testnet.binance.vision và https://testnet.binancefuture.com
- MetaTrader 5 nếu muốn quét vàng, bạc, dầu. Không có MT5 thì phần crypto vẫn chạy đầy đủ.

### 3.2 Đưa key testnet vào Keychain

Chỉ làm một lần. Key đi vào Keychain của macOS, **không bao giờ dán vào chat, không bao giờ commit**.

```bash
# Spot testnet
security add-generic-password -a binance-testnet -s trading-system-binance-testnet-api-key    -w '<KEY>'
security add-generic-password -a binance-testnet -s trading-system-binance-testnet-secret-key -w '<SECRET>'
# Futures testnet
security add-generic-password -a binance-futures-testnet -s trading-system-binance-futures-testnet-api-key    -w '<KEY>'
security add-generic-password -a binance-futures-testnet -s trading-system-binance-futures-testnet-secret-key -w '<SECRET>'
```

`config/env.demo` đã trỏ sẵn vào bốn mục này. Không cần sửa gì.

### 3.3 Kiểm tra toàn bộ

```bash
bash scripts/verify-automation-v3.sh
```

Script này không đặt lệnh, không cài gì, không ghi file dừng. Nó biên dịch mọi script, kiểm tra file cấu hình, gọi thử endpoint chỉ đọc trên môi trường đang bật. Dòng cuối phải là `FAIL=0`. Nếu có FAIL, sửa xong mới đi tiếp.

### 3.4 MT5 (chỉ khi cần CFD)

1. Mở MT5, mở một chart cho **mỗi** mã muốn quét (XAUUSD, XAGUSD, USOIL, UKOIL). EA gắn theo từng chart, nên một chart chỉ cho ra dữ liệu một mã.
2. Gắn `integrations/mt5/ExportOHLCV.mq5` vào từng chart, đặt `InpBarsToExport` từ 300 trở lên.
3. Kiểm tra: `data/live/mt5-bridge/ohlcv.<MÃ>.15m.json` xuất hiện và được cập nhật.

Hiện tại chỉ XAUUSD có dữ liệu. Chi tiết và cảnh báo về tick volume: `docs/architecture/mt5-bridge.md`.

### 3.5 Vốn tài khoản

Hệ thống chưa tự đọc số dư cho phần phân tích. Điền `account_equity` trong `docs/architecture/risk-config.json`. Pilot thì tự đọc số dư USDT qua connector.

---

## 4. Dùng hàng ngày

### 4.1 Bật và tắt tự động hoá

```
/automation            xem trạng thái, an toàn gõ bất cứ lúc nào
/automation env        môi trường nào đang bật, file đã điền đủ chưa
/automation on         bật hết: scanner, pilot, giữ máy không ngủ
/automation off        tắt hết, và giữ nguyên tắt sau khi khởi động lại máy
/automation demo       chọn demo rồi bật hết
/automation real       chọn real rồi bật hết (từ chối nếu env.real chưa điền)
```

**Sau khi khởi động lại máy:** mở MT5 trước (nếu dùng CFD), rồi gõ `/automation on`. Nếu lần tắt máy trước đang ở trạng thái bật, launchd tự chạy lại scanner và pilot khi đăng nhập mà không cần gõ gì.

**Hai loại "tự động" khác nhau, cần hiểu rõ:**

| Tầng | Chạy bằng gì | Sống được khi nào |
|---|---|---|
| Scanner (lấy data, quét sự kiện Wyckoff/ICT), pilot (đặt lệnh), giữ máy thức | launchd, ngoài Claude | Cả khi đóng Claude, cả sau khi khởi động lại máy |
| Đọc cục bộ Sonnet, phân tích toàn diện hằng ngày, cập nhật chart/artifact | Cron **bên trong phiên Claude**, do `/automation on` tạo lại từ `integrations/crons/` | Chỉ khi phiên Claude đang mở; hết hạn sau 7 ngày |

Nghĩa là: đóng Claude thì scanner và pilot vẫn chạy, nhưng chart và các bản nhận định ngừng cập nhật cho đến khi mở Claude và gõ `/automation on` lần nữa.

**Chạy một phần:**

```
/automation market cfd off
/automation timeframe 4h off --market crypto   # khung được quét: 15m (scalping), 1h (day), 4h (swing)
/automation instrument SOLUSDT off
/automation layer pilot off        # scanner vẫn chạy, pilot ngừng đặt lệnh từ tick kế tiếp
```

Tài liệu đầy đủ của lệnh này: `.claude/commands/automation.md`.

### 4.2 Theo dõi

```
/status                          nguồn dữ liệu nào AVAILABLE / MOCK / STALE, vị thế đang mở
/automation pilot status         pilot có đang chạy không, có file STOP không, dòng log cuối
python3 scripts/strategy-runner.py --report    trạng thái vị thế / lệnh chờ của pilot
```

Log: `data/live/pilot-futures/loop.log` (pilot — một sàn duy nhất từ 2026-09-13), `data/live/scan-loop.log` (scanner).

### 4.3 Dừng khẩn cấp

Không cần Claude, không cần mạng:

```bash
touch data/live/pilot-futures/STOP              # pilot dừng ở tick kế tiếp
python3 scripts/strategy-runner.py --flatten    # đóng mọi vị thế ngay lập tức
```

`/automation on` sẽ tự xoá file STOP khi bật lại.

### 4.4 Phân tích bằng tay

```
/bias BTCUSDT          chỉ xu hướng khung lớn, không chấm điểm
/analyze BTCUSDT       toàn bộ quy trình 12 bước, ra TRADE / WAIT / NO_TRADE, ghi nhật ký
/entry BTCUSDT 64700   kiểm tra một điểm vào cụ thể sau khi đã có /bias
/execute <id lệnh>     đặt lệnh bằng tay, luôn hỏi xác nhận một lần, nói rõ đang ở môi trường nào
```

Thêm `mock` vào cuối để diễn tập bằng dữ liệu giả: kết quả sẽ có nhãn REHEARSAL và không bao giờ được coi là tín hiệu thật.

### 4.5 Nhật ký và học

```
/journal      ghi hoặc cập nhật một lệnh trong trades/
/review       review sau khi đóng lệnh, điền kết quả cho các mâu thuẫn đã ghi
/improve      đề xuất cải tiến; không bao giờ tự áp dụng
```

---

## 5. Chuyển sang tiền thật, theo thứ tự

1. Chạy demo đủ lâu để có lệnh đã đóng trong `trades/`. Lúc viết tài liệu này, nhật ký có 0 lệnh đã đóng. Đừng bỏ qua bước này.
2. Tạo API key mainnet trên Binance với quyền **chỉ giao dịch**, không rút tiền. Bật giới hạn IP nếu có thể.
3. Đưa vào Keychain với tên tài khoản `binance-mainnet`, rồi trong `config/env.real` trỏ tới bằng `keychain:<service>@binance-mainnet`. Mẫu nằm ngay đầu file đó.
4. Chỉ còn **một sàn pilot**: `PILOT_MARKETS=futures` (`config/env.example:39`). Hạ `PILOT_RISK_PCT` xuống nhỏ hơn khi mới chạy — trần cứng là `trading_env.MAX_RISK_PCT` = **0.03** (3 %/lệnh, quyết định người dùng 2026-09-13, đi kèm sàn R:R kế hoạch **3.0** đọc qua `trading_env.min_rr()`); `config/env.example` đang đặt sẵn `PILOT_RISK_PCT=0.03`, tức là ngay ở trần.
5. Chạy lại `bash scripts/verify-automation-v3.sh`. Mục 6 sẽ gọi endpoint chỉ đọc trên mainnet.
6. Gõ `/automation real`. Đọc kỹ phần báo cáo, đặc biệt các dòng bắt đầu bằng `!`.
7. Theo dõi tick đầu tiên trong `data/live/pilot-futures/loop.log`. Lưu ý: `strategy-runner.py` **từ chối mọi tick khi `execution.environment == "real"`** (`strategy-runner.py:181` (`== "real"`)) — quyết định người dùng 2026-09-11, pilot demo/testnet trước. Vòng lặp có thể khởi động ở `real` nhưng sẽ không đặt lệnh.

---

## 6. Dùng model nào

Nguyên tắc (SYSTEM-DESIGN.md §14): **Haiku chỉ hiển thị, không bao giờ suy luận.** Mọi bước cần phân tích, nhận định, chấm điểm dùng ít nhất Sonnet, và điều này được ghim trong file thay vì chỉ dặn:

- Năm agent phân tích trong `.claude/agents/` ghim `model: sonnet`, nên dù phiên đang ở Haiku, chúng vẫn chạy Sonnet.
- Các lệnh có suy luận (`/analyze`, `/bias`, `/entry`, `/review`, `/improve`, `/exit`, `/invalidate`, `/risk`, `/journal`, `/status`) có cổng kiểm tra model ở đầu: nếu phiên là Haiku, lệnh tự đẩy toàn bộ việc sang một agent Sonnet và chỉ hiển thị kết quả.
- `/execute` thì dừng và bảo đổi model, vì lần xác nhận của con người phải ở cùng lượt với model đã chuẩn bị lệnh.

| Việc | Model |
|---|---|
| `/automation` (mọi tham số) | Haiku được, chỉ in output. Nếu output có dòng `!` hay `REFUSED`, Haiku phải in nguyên văn và đề nghị đổi sang Sonnet, không tự diễn giải. Lần `demo`/`real` đầu tiên nên dùng Sonnet |
| Mọi thứ còn lại | Sonnet trở lên |

---

## 7. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `environment 'real' incomplete` | `config/env.real` còn `__FILL_ME__` | Điền key, chạy lại verify |
| `ABSENT (... unresolvable keychain: reference)` | Keychain không có mục được trỏ tới | Kiểm tra lại tên service và account trong lệnh `security add-generic-password` |
| `pilot NOT installed: a pilot loop is already running outside launchd` | Có loop chạy tay từ terminal | `touch data/live/pilot-futures/STOP`, đợi một tick, gõ `/automation on` lại |
| `MT5 bridge NOT fresh` | MT5 chưa mở hoặc EA chưa gắn | Mở MT5, gắn EA; CFD tự chạy lại khi file tươi |
| Scanner log ghi `disabled by /automation` mỗi phút | Công tắc đang tắt | `/automation on` |
| Claude báo bị "classifier" chặn khi sửa file trong `.claude/commands/` | Chế độ auto của Claude Code chặn tự sửa file lệnh | Tắt auto mode một lượt, hoặc tự copy file |
| Điểm không bao giờ đạt ngưỡng cho vàng/dầu | CFD chỉ có 2 trên 4 chiều dữ liệu, tối đa NORMAL | Đây là giới hạn cấu trúc, xem `SYSTEM-DESIGN.md` §12 mục 3 |

---

## 8. Bản đồ file quan trọng

| File | Vai trò |
|---|---|
| `docs/architecture/SYSTEM-DESIGN.md` | Kiến trúc, cách chấm điểm, mọi quyết định thiết kế |
| `docs/architecture/automation-config.json` | Trạng thái tự động hoá và công tắc môi trường |
| `config/env.demo`, `config/env.real` | Thông tin tài khoản từng môi trường, không commit |
| `docs/architecture/risk-config.json` | Vốn và giới hạn rủi ro cho phần phân tích |
| `docs/architecture/analysis-params.json` | Ngưỡng số: khối có trích dẫn sách và khối tự định nghĩa |
| `docs/architecture/session-model.md` | Phiên giao dịch và trọng số theo mã |
| `knowledge/10-integrated-method.md` | Quy trình đọc thị trường hợp nhất, đọc trước khi sửa skill |
| `scripts/automation.py` | Toàn bộ logic của `/automation` |
| `scripts/strategy-runner.py` | Engine pilot duy nhất — luật đặt lệnh, trần rủi ro, sàn R:R |
| `scripts/verify-automation-v3.sh` | Bài kiểm tra chấp nhận |
| `trades/` | Nhật ký lệnh, nguồn duy nhất để đánh giá hệ thống có edge hay không |
