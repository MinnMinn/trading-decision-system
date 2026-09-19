# Chạy 10–100 tài khoản đồng thời, mỗi tài khoản một phương pháp

**Yêu cầu người dùng (2026-09-19):** *"Hiện tại system đang setup trade cho một tài khoản cả demo và real.
Hãy setup để có thể trade cùng lúc 10-100 tài khoản khác nhau, mỗi tài khoản có thể lựa chọn một phương pháp
giao dịch khác nhau. Cho tao biết nếu tao đang sai ở đâu."*

Tài liệu này trả lời vế thứ hai trước, vì câu trả lời đó đổi **cái cần xây**.

**Làm rõ của người dùng (cùng ngày):** *"trong tương lai tao sẽ có nhiều khách hàng muốn thuê phương pháp để
trade. Họ sẽ đưa cho chúng ta tài khoản, và công việc của chúng ta là gắn tài khoản của khách + setup của
phương pháp mà khách hàng lựa chọn. Vậy nên một tài khoản có thể dùng nhiều phương pháp với nhiều thị trường.
Và ngược lại, một phương pháp cũng có thể setup cho nhiều tài khoản dùng chung."*

Điều này đổi thiết kế ở ba chỗ, và §1.2 bên dưới đã được viết lại theo nó.

---

## 0. Mô hình nghiệp vụ: cho thuê phương pháp (multi-tenant)

### 0.1 Quan hệ là **nhiều–nhiều**, nên nó là một bảng riêng

Một tài khoản chạy nhiều phương pháp trên nhiều thị trường; một phương pháp phục vụ nhiều tài khoản. Đó không
phải một trường `setups[]` gắn vào hồ sơ tài khoản — đó là một **bảng uỷ nhiệm** (mandate) riêng:

```
owner (khách hàng)  1 ──── n  account  n ──── n  setup
                                     └── mandate: {id, account_id, setup_id, setup_version,
                                                   state, started_at, ended_at, risk_pct}
```

`setup_version` được chốt **tại thời điểm gắn**, không phải đọc động. Lý do: khi chúng ta sửa một phương pháp
(như bốn thay đổi hôm nay), khách hàng đang thuê bản cũ phải tiếp tục chạy bản họ đã đồng ý cho tới khi họ
chấp nhận bản mới. `scripts/setup_version.py` đã tính sẵn version từ các trường phát hiện — đây là chỗ nó
trở nên bắt buộc thay vì chỉ hữu ích.

### 0.2 **Chủ sở hữu** là ranh giới của rủi ro, không phải "toàn hệ"

Xem §1.2. Hệ quả cụ thể đã cài trong `scripts/exposure.py`: trần `max_correlated_accounts` tính **theo chủ sở
hữu**; con số toàn nhà được **báo cáo** (`house_holders`) chứ không dùng để từ chối. Từ chối lệnh của khách B
vì khách A vào trước không phải quản trị rủi ro — đó là để ai tick trước thì thắng.

### 0.3 Bốn việc mà mô hình cho thuê bắt buộc phải có, hệ hiện tại chưa có

| # | Việc | Vì sao bắt buộc | Trạng thái |
|---|---|---|---|
| 1 | **Quy kết từng lệnh** về `(account, mandate, setup, setup_version)` | Tính tiền, và tranh chấp. Khách hỏi "lệnh này của phương pháp nào, bản nào" phải trả lời được bằng dữ liệu | **ĐÃ LÀM.** `plan_of()` mang `mandate` bên cạnh `setup_version` đã có; `log()` đóng dấu `account` lên mọi bản ghi; `client_id()` gieo mầm bằng account — thiếu mầm đó thì **hai tài khoản cùng tín hiệu sinh ra cùng một `newClientOrderId`**, sàn từ chối cái thứ hai như trùng lặp, một khách mất lệnh trong im lặng và lỗi trông như lỗi sàn |
| 2 | **Cô lập sự cố giữa các khách** | Một khách hết tiền/khoá hỏng không được làm đứng 99 khách kia | **ĐÃ LÀM.** `--account <id>` + `bind_account()` đưa state, log, cache nến và `STOP` về `data/live/accounts/<id>/`; `halted()` đọc **hai tầng** — `GLOBAL_STOP` dừng cả hệ, `STOP` riêng dừng một khách. Không truyền `--account` thì mọi đường dẫn về **đúng như cũ**. Còn lại: `errors`/`ERROR_HALT` vẫn là một biến đếm chung cho hai venue **trong một tài khoản** — tách state đã cô lập giữa các khách, phần còn lại là vấn đề có từ trước |
| 3 | **Thứ tự khớp lệnh công bằng và ghi lại được** | 50 tài khoản cùng một tín hiệu: ai vào trước được giá tốt hơn. Nếu thứ tự là "tình cờ theo tiến trình nào tick trước" thì nó vừa bất công vừa không giải trình được | **ĐÃ LÀM.** `scripts/dispatch_order.py`: `sha256(signal_id‖account_id)`. Đều (mỗi tài khoản đứng đầu ~1/N lần), tất định (vị trí hàng đợi tính lại được từ bản ghi lệnh sau nhiều tháng — đó là thứ biến nó thành **câu trả lời** cho tranh chấp), và **không cần trạng thái chung** nên N tiến trình độc lập thống nhất thứ tự mà không cần bộ điều phối trung tâm. Độ trễ `stagger_ms` khai trong `execution-safety.json` và được nói thẳng là **độ trễ thật** |
| 4 | **Trần theo sức chứa của thị trường** | Cùng một tín hiệu nhân N tài khoản tự đẩy giá chống lại chính nó trên mã mỏng | **ĐÃ LÀM, và nói rõ cái chưa đo được.** Không script nào đọc độ sâu sổ lệnh nên **không thể** đặt một con số sức chứa — bịa ra còn tệ hơn nói thẳng. Mã **có thể** khai `max_estate_notional_usd` trong `instruments.json` và khi đó là trần cứng; khi không khai, mỗi lần cấp hạn ngạch mang `capacity: UNDECLARED`, và khi vượt `capacity_required_above_accounts` tài khoản cùng giữ mã đó thì điều chưa biết **chuyển thành từ chối** (§20: UNKNOWN không được im lặng thành vô hại) |

**Chưa nối vào tick.** `dispatch_order` và cổng sức chứa đã có và đã test, nhưng `tick()` chưa gọi chúng — việc đó thuộc Pha 2/5b, vì nó cần rủi ro theo tài khoản đi tới `size()` trước.

### 0.4 Ba việc **không phải** của code, phải bạn quyết trước khi có khách thật

- **Giữ khoá API của người khác.** Đây là tài sản và uỷ quyền của bên thứ ba. Quy tắc "không bao giờ yêu cầu
  quyền rút tiền" đã có trong `CLAUDE.md §51` và có kiểm chứng (`scripts/execution_safety.py` key-scope probe),
  nhưng khoá mỗi khách phải tách riêng (Pha 3) và đó là **ranh giới tin cậy** — cần Security review trước khi
  viết code, không phải sau.
- **Điều khoản của quỹ.** Nhiều quỹ prop cấm copy-trading giữa các tài khoản cùng chủ sở hữu hưởng lợi. Tôi
  **chưa kiểm chứng** điều khoản hiện hành của FTMO/The5ers, và số liệu hai quỹ này trong
  `docs/architecture/account-profiles.json` vẫn mang cờ `_source.verify`.
- **Công bố tương quan.** Khách thuê cùng một phương pháp sẽ thắng và thua **cùng lúc**. Đó là đặc tính của
  sản phẩm, không phải lỗi — nhưng nó phải được nói ra trước, không phải khám phá vào ngày đầu tiên cả nhóm
  cùng chạm luật thua ngày.

### 0.5 Và cái chưa có để bán

Hiện có **2** luật chạy được và **3** setup (n = 64/74/51, cả hai nguồn stability đang FLAGGED). Danh mục cho
thuê hôm nay là 3 món, không phải 100. Xây được năng lực gắn khách vào phương pháp; nhưng số phương pháp để
khách chọn là một việc khác, đang chạy song song, và không nên bị trộn vào đây.


---

## 1. Ba chỗ yêu cầu đang sai (có bằng chứng, không phải ý kiến)

### 1.1 Danh mục cho thuê hiện có **3 món**, không phải 100

*(Viết lại sau làm rõ của người dùng. Bản đầu tôi đọc yêu cầu thành "mỗi tài khoản một phương pháp riêng" và
phản đối rằng không đủ phương pháp cho 100 tài khoản. Với mô hình cho thuê thì một phương pháp phục vụ nhiều
khách, nên phản đối đó không đúng chỗ. Cái còn đúng là về **danh mục**.)*

`scripts/methods.py:361` `runnable()` trả về đúng hai luật: **ICT** và **WYCKOFF-BOOK**. `COMBINED-BOOK` có
`runnable: false` vì gần như không phát tín hiệu. `docs/architecture/pilot-top5.json` có **3** setup, cỡ mẫu
**64 / 74 / 51**, và cả hai nguồn stability của nó mang `research_validity.worst = "FLAGGED"`.

Với cỡ mẫu đó, bootstrap lồng trong `scripts/performance.py` cho khoảng ước lượng tỉ lệ pass **rất rộng** —
đó là lý do `prop_key()` xếp hạng theo **cận dưới** khi ước lượng bị đánh dấu rộng. Bán một phương pháp cho
khách là một lời hứa; ba món với khoảng tin cậy rộng là những gì hiện có để hứa.

Điều này **không chặn** việc xây năng lực gắn khách. Nó chặn việc coi "khách chọn phương pháp" như một menu
dài. Menu hôm nay là 3 dòng.

### 1.2 Nguy cơ thật không phải "đòn bẩy" — là **hỏng đồng loạt**

*(Mục này đã được viết lại. Bản đầu tôi viết "100 tài khoản cùng tín hiệu = đặt cược gấp 100 lần". **Sai về số
học**, và chính test của module mới bắt được:)*

| Số tài khoản | Vốn tổng | Rủi ro tổng (1 %/tài khoản) | % vốn tổng |
|---|---|---|---|
| 1 | $10.000 | $100 | 1,00 % |
| 10 | $100.000 | $1.000 | 1,00 % |
| 100 | $1.000.000 | $10.000 | 1,00 % |

Mỗi tài khoản có vốn riêng, nên rủi ro 1 % mỗi tài khoản **là** 1 % của tổng, với mọi N. Một trần biểu diễn
bằng phân số của vốn tổng **bất biến theo N** và vì thế không thể là cổng làm cho đa tài khoản an toàn.

Nguy cơ thật sự tăng theo N là **hỏng đồng loạt**. Mỗi tài khoản quỹ mang luật thua ngày và luật sụt giảm
tổng của riêng nó (`docs/architecture/account-profiles.json`). Nếu 100 tài khoản cùng long một mã, một cú
chạy ngược **phá luật thua ngày của cả 100 tài khoản trong cùng một ngày** — mất cả trăm suất thử thách, chứ
không phải mất 1 %. Không cổng per-account nào thấy được điều đó, vì nhìn từ bên trong một tài khoản thì
không có gì bất thường.

Hai lỗi thật trong code vẫn đúng và vẫn phải sửa (đã xác minh):

- **`effective_risk_pct` của tài khoản KHÔNG bao giờ tới đường tính khối lượng.** `grep` trong
  `strategy-runner.py` không có kết quả nào; chỉ `trading_system.py:435`, `performance.py:621`,
  `build-artifact.py:806` đọc nó — toàn bề mặt mô tả, không phải bề mặt đặt lệnh. `size()` (`:981`) và
  `mt5_lots()` (`:990`) đọc biến module `RISK_PCT` (`:202-205`). Viết một tỉ lệ rủi ro riêng cho tài khoản
  hôm nay là viết vào chỗ không ai đọc.
- **Không có bất kỳ kiểm tra phơi nhiễm tổng hợp nào.** `scripts/risk_model.py:151` `open_risk()` và
  `:231-243` nhánh `existing_exposure` **tồn tại nhưng runner không gọi**.

→ Cổng P0 là **đếm số tài khoản đang giữ cùng một (mã, chiều)**, không phải trần phân số. Đã cài:
`scripts/exposure.py` + `max_correlated_accounts` trong `risk-config.json`. Trần phân số
(`max_portfolio_risk_pct`) vẫn giữ, nhưng đúng với việc nó thật sự làm: chặn **lệch tập trung** khi các tài
khoản chênh nhau về vốn hoặc tỉ lệ rủi ro — không phải chặn tương quan.

Cổng đó đồng thời là một **phép đo**: nếu các tài khoản thật sự chạy phương pháp khác nhau thì chúng hiếm khi
đụng nhau và trần hiếm khi chạm. Một trần chạm liên tục chính là bằng chứng rằng tiền đề "mỗi tài khoản một
phương pháp" không đúng.

### 1.3 Đa tài khoản trên **cùng một quỹ** có thể vi phạm luật của chính quỹ đó

Nhiều quỹ prop cấm copy-trading giữa các tài khoản cùng một chủ sở hữu hưởng lợi. Tôi **chưa kiểm chứng** điều
khoản hiện hành của FTMO/The5ers — và các con số trong `docs/architecture/account-profiles.json` cho hai quỹ
này vẫn đang mang cờ `_source.verify`, tức là tóm tắt web search chưa đối chiếu trang nhà cung cấp. Đây là việc
người dùng phải xác nhận trước khi mở nhiều tài khoản thật, không phải việc code giải quyết được.

---

## 2. Điều đúng trong yêu cầu

Tách **danh tính tài khoản** ra khỏi **venue** là đúng và nên làm dù chỉ có 2 tài khoản. Hôm nay tài khoản
được tra theo `(venue, environment)` chứ không theo id: `scripts/account_profile.py:286-292` `for_venue()`
**ném lỗi** nếu không đúng một hồ sơ khớp, và `:123-132` **từ chối ngay lúc import** hai hồ sơ cùng
`(venue, environment)`. Nghĩa là đa tài khoản trên một venue hiện là **cấu hình bị từ chối**, không phải
"chưa làm". Đó là một quyết định an toàn đúng đắn cho thiết kế một-tài-khoản, và là thứ đầu tiên phải thay.

---

## 3. 21 điểm nghẽn một-thực-thể (đã xác minh, `path:line`)

Nhóm theo cách xử lý.

**A. Trạng thái chia sẻ có khoá là SYMBOL, phải thành (account, symbol)**

| # | Thứ | Ở đâu |
|---|---|---|
| 1 | `positions` | `strategy-runner.py:363`, ghi `:1536`, `:1823` |
| 2 | `pending` | `:363`, `:1832` |
| 3 | `trades_today` | `:363`, reset `:1424`, đọc `:1708`, tăng `:1534`/`:1823` |
| 4 | `seen` (khử trùng tín hiệu, 800 phần tử) | `:1661-1664` — khoá `setup-symbol-side-time`, không có tài khoản |
| 5 | `client_id` | `:909-913` — `sha1(setup\|symbol\|side\|time)` |

**B. Đường dẫn hằng số, phải tham số hoá theo account id**

| # | Thứ | Ở đâu |
|---|---|---|
| 6 | `top5-state.json` | `:81`, ghi `:391-393` — `open(...,"w")` trần, **không khoá, không đổi tên nguyên tử** |
| 7 | `top5-log.jsonl` / `top5-mt5-log.jsonl` | `:82`, `:83`, `VENUE_LOG` `:228` |
| 8 | `STOP` | `:84`, ghi `:1362`, đọc `:1412`; `automation.py:225-232` hard-code một thư mục cho mọi thị trường |
| 9 | thư mục cache nến | `:79`, ghi `:533`, đọc `:537` |
| 10 | `trades/index.jsonl` + id lệnh | `journal.py:51-52`, `:234`, ghi lại toàn file `:289-291` |
| 11 | `data/live/feed-health.json` | `feed_health.py:46`, ghi lại toàn file `:158-165` |
| 12 | `data/live/key-scope.json` | `execution_safety.py:88`, khoá theo provider `:179` |

**C. Biến toàn cục trong tiến trình**

| # | Thứ | Ở đâu |
|---|---|---|
| 13 | `RISK_PCT` / `RISK_CEILING` | `:201-205` |
| 14 | `_PROFILES` (2 ô, cố định lúc import) | `:167-180` |
| 15 | `ENV_NAME` (một tên môi trường cho cả tiến trình) | `:157`, `trading_env.py:91-99` |
| 16 | `errors` + `ERROR_HALT = 3` | `:363`, `:151`, `:1450`, `:1549` |
| 17 | `_LAT`, `_MIN_NOTIONAL`, `_MT5_SYMBOLS`, `_REPLAY_QUALITY` | `:102`, `:863`, `:465` |

**D. Điểm nghẽn vật lý / cấu hình (không sửa bằng refactor được)**

| # | Thứ | Ở đâu |
|---|---|---|
| 18 | Bộ khoá API: một bộ mỗi venue, chọn bởi một `active_env_name()` | `config/env.example:21-36`, `trading_env.py:102-103`, `trading-env.sh:68`, `binance-futures-testnet-order.sh:49-54` |
| 19 | Cầu MT5 là **singleton vật lý**: một thư mục symlink, một terminal đã đăng nhập, một EA | `mt5-order-bridge.py:24`, `OrderBridge.mq5:31-34`; `res-<id>.json` bị **đọc-rồi-xoá** (`:64`) nên hai client tranh nhau phản hồi của nhau |
| 20 | `pilot_process` một ô + một launchd label | `automation-config.json`, `automation.py:601-611` ("Do not start a second loop"), `:244` |
| 21 | Bộ công cụ & dimensions theo **market**, không theo tài khoản | `:301-309` `enabled_symbols()`, `:312-327` `allowed_methods()` |

Điểm 19 là ràng buộc cứng: **N tài khoản MT5 = N terminal = N tiến trình**. Không có cách nào khác.

---

## 3b. Sửa kiến trúc: **một phân tích, phát tin, N người thực thi** (quan điểm người dùng, 2026-09-19)

**Người dùng nêu:** *"khi một phương pháp phân tích và có tín hiệu vào lệnh, lúc này chỉ cần send message với
data là id phương pháp, id thị trường cho một topic. Topic này sẽ dựa vào id phương pháp và id thị trường để
tìm kiếm toàn bộ tài khoản đang có các foreign keys này và thực hiện việc vào lệnh bất đồng bộ."*

**Đúng, và nó thay thế §4 bên dưới ở phần phân tích.** Bốn lý do, không phải một:

1. **Tín hiệu là thuộc tính của THỊ TRƯỜNG, không phải của tài khoản.** Hôm nay mỗi tài khoản một tiến trình
   và cả N tiến trình chạy **cùng một** phép quét trên **cùng một** bộ nến. Cache nến dùng chung đã bỏ được
   phần *tải dữ liệu* trùng lặp, nhưng phần *tính toán* vẫn nhân N. Một phân tích cho mỗi
   `(phương pháp, thị trường, khung)` xoá hẳn phần nhân đó: chi phí CPU thôi phụ thuộc vào số khách.
2. **Đây chính là kiến trúc mà repo đã tự khai.** `CLAUDE.md` §35/§36 tách **Decision Engine** khỏi
   **Execution Router**, và `SYSTEM-DESIGN.md:626` ghi router mới **"Partial"**. Đề xuất này là nửa còn thiếu.
3. **Bảng tra đã có sẵn.** `scripts/mandates.py` `for_setup()` trả về đúng danh sách tài khoản mang khoá ngoại
   đó, và trần 10 tài khoản/phương pháp/thị trường đã chặn sẵn độ rộng của cú fan-out.
4. **Thứ tự khớp lệnh công bằng trở nên tự nhiên.** Bên phát tin giữ toàn bộ danh sách tài khoản đủ điều kiện
   **cùng một lúc**, nên `dispatch_order.order(signal_id, accounts)` được áp một lần ở đó thay vì mỗi tiến
   trình tự tính thứ hạng của mình.

### 3b.1 Cái KHÔNG đổi, và đây là chỗ hay bị hiểu nhầm

Fan-out đổi **ai quyết định**. Nó không đổi **lệnh tới sàn bằng đường nào**.

Với MT5 **không có API**. Dự án nói chuyện với terminal bằng cách **ghi một file lệnh** vào thư mục mà
terminal đang theo dõi; EA đọc file đó, đặt lệnh, rồi **ghi file trả lời**. Connector đọc file trả lời **rồi
xoá nó** (`scripts/mt5-order-bridge.py`). Một terminal đăng nhập **một** tài khoản.

Nên nếu worker của hai tài khoản ghi vào **cùng một thư mục**, cả hai cùng thấy cả hai file trả lời, và ai đọc
trước thì xoá mất — **xác nhận khớp lệnh của khách A có thể bị giao cho khách B**. Tách thư mục theo tài khoản
(`InpBridgeDir` phía EA, `MT5_BRIDGE_SUBDIR` phía runner) là thứ chặn điều đó, và nó **cần thiết bất kể** lệnh
đến từ topic hay từ tiến trình riêng. Fan-out bất đồng bộ làm nó **cần hơn**, vì giờ nhiều lệnh rời đi cùng
một khoảnh khắc.

*(`InpBridgeDir` là input **biên dịch**: sửa file `.mq5` không có tác dụng cho tới khi biên dịch lại trong
MetaEditor và gắn lại EA vào chart.)*

### 3b.2 Worker KHÔNG phải cái máy sao chép

Mỗi tài khoản vẫn phải tự chạy phần của nó, vì những thứ này khác nhau giữa các khách:

- khối lượng (vốn khác nhau → `size()` với `effective_risk_pct` của chính tài khoản đó);
- luật tài khoản §33 (thua ngày, sụt giảm, số vị thế, số lệnh/ngày);
- hai cổng `scripts/exposure.py` (tương quan theo chủ sở hữu, sức chứa theo mã);
- state, log, kill switch riêng — tức `bind_account()` đã làm vẫn còn nguyên giá trị, chỉ là nó phục vụ phía
  **thực thi** thay vì phía phân tích.

Một worker **có quyền từ chối cho riêng tài khoản của nó** mà không ảnh hưởng ai khác. Đó là §62: một lane
hỏng không được làm đứng lane khác.

### 3b.3 Rủi ro phải nói ra

Một bên phát tin là **một điểm hỏng chung**: một phân tích sai hoặc cũ sẽ tới **mọi** khách cùng lúc. Hôm nay
điều đó gần như đã đúng (cùng một đoạn code), nhưng nhiều tiến trình ít ra còn tính lại độc lập. Bù lại:
bản tin phải **mang theo trạng thái thị trường nó đã đọc và cửa sổ hiệu lực của nó**, và mỗi worker **kiểm
tra lại độ tươi và các cổng** trước khi đặt — không đặt lệnh theo một bản tin nó không tự xác minh được.

### 3b.4 Hình dạng cụ thể — broker chọn theo SỐ ĐO; kết luận: Redis Streams

**Đính chính §57.** Tôi đã nói nhầm nó là "cấm hàng đợi". Nguyên văn: *"Do not introduce **speculative**: …
queues … **unless required by the current phase**"* (`CLAUDE.md:2355-2367`). Đó là cấm **đầu cơ**, không phải
cấm hàng đợi. Khi một pha thật sự cần hàng đợi thì §57 **cho phép**. Không có lệnh cấm nào để gỡ.

**Số đo quyết định.** Tần suất tín hiệu thật, đo trên chính lịch sử của repo sau khi sửa luật khớp lệnh:

| Chuỗi | Số lệnh | Số ngày | Tín hiệu/tuần |
|---|---|---|---|
| BTCUSDT 15m | 15 | 1 094 | 0,10 |
| ETHUSDT 15m | 4 | 1 094 | 0,03 |
| XAUUSD 15m | 17 | 3 104 | 0,04 |
| BTCUSDT 1H | 2 | 1 459 | 0,01 |
| ETHUSDT 1H | 2 | 1 459 | 0,01 |
| XAUUSD 1H | 8 | 8 134 | 0,01 |
| **Cộng** | | | **0,19/tuần** |

Với fan-out 10 tài khoản: **≈ 2 bản tin mỗi tuần**. Kafka được thiết kế cho hàng trăm nghìn bản tin mỗi
**giây**, phân vùng, nhân bản, consumer group, quản lý offset. Dùng nó ở đây không phải "quá mức" — nó là
thêm một daemon, một quyết định schema, một chế độ hỏng mới **nằm trên đường đặt lệnh**, để chuyển hai bản
tin một tuần.

**Tiêu chí thật sự, và nó KHÔNG phải throughput: worker có nằm trên nhiều máy không?**

- **Một máy** (hiện tại, và bắt buộc như vậy chừng nào còn MT5 — terminal phải chạy cục bộ): file + một cột
  `claim` là đủ, và nó cho cả ba thứ mà broker được mua về vì chúng: giao ít nhất một lần, biên nhận, và
  phát lại để audit. Không daemon mới.
- **Nhiều máy** (khi số terminal MT5 vượt một host): lúc đó broker **được §57 cho phép** vì pha yêu cầu nó,
  và thư mục chia sẻ qua NFS chính là chỗ chuyện "đọc-rồi-xoá" hỏng thật.

**Broker đã chọn: Redis Streams** (quyết định người dùng 2026-09-19). Lý do nó hợp tải này: một tiến trình,
`XADD`/`XREADGROUP` cho consumer group có **ack** (`XACK`) và **phát lại** (`XAUTOCLAIM` cho bản tin bị bỏ
rơi khi worker chết giữa chừng), và log có giới hạn độ dài nên không cần quản lý retention như một cluster.
Kafka bị loại vì nó giải bài toán chúng ta không có.

**Ba điều kèm theo quyết định này, phải xử lý chứ không phải ghi chú:**

1. **Redis trên Windows.** Redis không có bản Windows chính thức. Các đường đi: **WSL2**, **Docker Desktop**,
   **Memurai** (bản thương mại tương thích Redis cho Windows), hoặc đặt Redis trên một host Linux riêng.
   Phải chọn **trước** khi nối, và nó tương tác thẳng với việc chuyển máy ngày mai
   (`docs/plans/2026-09-20-windows-migration.md`). Chưa kiểm chứng cái nào — phải thử trên máy thật.
2. **Thứ tự.** Nối Redis **sau** khi bản chạy trên Windows đã xanh. Chuyển hệ điều hành và thêm một hạ tầng
   mới cùng lúc thì lỗi nào cũng không quy được cho ai. Đây là lý do kỹ thuật, không phải do dự.
3. **Seam vẫn giữ nguyên.** `publish(signal)` / `claim() -> signal` / `ack(signal_id)`. Bản chạy đầu là file
   để ngày 1 không phụ thuộc Redis; đổi sang Redis Streams là thay phần thân của ba hàm đó. Không đoạn
   nghiệp vụ nào biết khác biệt, và `XADD`/`XREADGROUP`/`XACK` ánh xạ một-một vào ba hàm ấy — đó chính là
   lý do seam được vẽ theo hình dạng này.

**Thiết kế seam ngay bây giờ để việc đổi là một file.** Đó chính là câu đầu của §57 — *"architect for future
extensibility where the current domain requires it"*. Publisher và worker chỉ nói chuyện qua một giao diện
`publish(signal)` / `claim() -> signal` / `ack(signal_id)`; bản chạy đầu là file, bản sau là broker, và không
có đoạn code nghiệp vụ nào biết sự khác biệt.

Quy ước hiện tại của repo là **file + registry**, và nó đủ cho bản chạy đầu:

```
scripts/signal-publisher.py           MỚI: một tiến trình cho mỗi (phương pháp, thị trường, khung)
   quét một lần  →  ghi data/live/signals/<signal_id>.json
        signal = { id, method, market, tf, symbol, side, setup_id, setup_version,
                   entry, stop, target, expires_bar, market_state, decided_at, valid_until }
        + queue: dispatch_order.order(signal_id, accounts)   ← thứ tự công bằng, chốt một lần
        |
        v
scripts/signal-worker.py --account <id>   MỚI: mỏng. Không phân tích.
   đọc bản tin  →  xác minh lại độ tươi  →  luật tài khoản  →  exposure.quota
                 →  chờ delay theo rank  →  đặt lệnh  →  ghi vào log của chính tài khoản
```

`signal_id` đã có định nghĩa: `dispatch_order.signal_id(setup_id, symbol, side, signal_time)` — đúng bốn
trường mà runner đang dùng để khử trùng tín hiệu.

**Thứ tự làm**: Pha 1–2 (state và rủi ro theo tài khoản) vẫn phải xong trước, vì worker cần chúng. Sau đó
tách `tick()` thành publisher + worker. Việc này **không** phụ thuộc vào setup nào sống sót sau lần xếp hạng
lại — nó là hạ tầng.

---

## 4. Kiến trúc đích

**Một phân tích cho mỗi (phương pháp, thị trường, khung); một tiến trình THỰC THI mỗi tài khoản.**

*(Sửa theo §3b. Bản đầu của mục này viết "một tiến trình mỗi tài khoản" và để mỗi tiến trình tự phân tích —
tức nhân cùng một phép quét lên N lần. Phần phân tích nay tách ra một bên phát tin.)*

Vẫn **không** multiplex N tài khoản trong một tiến trình thực thi. Lý do không đổi: MT5 buộc phải vậy
(điểm 19 — một terminal một tài khoản, một thư mục cầu nối), và cô lập lỗi là thứ mình muốn — một tài khoản
kẹt connector không được làm đứng 99 tài khoản kia (`ERROR_HALT`, điểm 16).

**Hồ sơ tài khoản KHÔNG đẻ thêm registry.** `docs/architecture/account-profiles.json` **đã là** registry tài
khoản và `scripts/account_profile.py` đã là reader duy nhất của nó. Nhưng quan hệ tài khoản↔setup là
**nhiều–nhiều** (§0.1), và một quan hệ nhiều–nhiều nhét vào một trường mảng trên một bên sẽ mất chỗ ghi những
thứ thuộc về **chính mối quan hệ**: bản phương pháp đã chốt, ngày bắt đầu, ngày kết thúc, tỉ lệ rủi ro đã thoả
thuận. Nên có đúng một file mới, và nó là bảng quan hệ:

```
docs/architecture/account-profiles.json
   profiles.<id> += { "owner": "<customer id>",   <- ranh giới của một pool rủi ro (§0.2)
                      "credentials": "<ref>" }    <- hậu tố bộ khoá, KHÔNG phải giá trị khoá

docs/architecture/mandates.json         <- MỚI: bảng nhiều-nhiều (§0.1)
   mandates[] = { id, account_id, setup_id, setup_version, state,
                  started_at, ended_at, risk_pct }
        |
        v
scripts/account_profile.py              <- reader duy nhất của hồ sơ; for_account(id) bên cạnh for_venue()
scripts/mandates.py                     <- MỚI: reader duy nhất của bảng uỷ nhiệm
        |
        +--> scripts/signal-publisher.py   <- MỚI (§3b): MỘT phân tích cho mỗi (phương pháp, thị trường, khung)
        |          |                             ghi data/live/signals/<signal_id>.json + hàng đợi công bằng
        |          v
        +--> scripts/supervisor.py      <- MỚI: sinh/giám sát N worker, mỗi cái --account <id>
        |          |
        |          +--> signal-worker.py --account acc-001   (state riêng, log riêng, STOP riêng; KHÔNG phân tích)
        |          +--> signal-worker.py --account acc-002
        |          +--> ...
        |
        +--> scripts/exposure.py        <- ĐÃ CÓ: trần tương quan theo chủ sở hữu, file chia sẻ có khoá
```

**Quy tắc bất biến mới (P0):** trước khi bất kỳ tiến trình nào đặt lệnh, nó phải xin hạn ngạch từ
`exposure.py`. Hai cổng: số tài khoản **của cùng một chủ sở hữu** đang giữ cùng một (mã, chiều) ≤
`max_correlated_accounts`; và tổng rủi ro mở ≤ `max_portfolio_risk_pct` × tổng vốn đã báo cáo. Không có hạn
ngạch → không đặt lệnh. Mọi bất định đều **từ chối**: slice cũ, vị thế không định giá được, sổ không đọc được.

---

## 5. Các pha

**Pha 0 — danh tính (không đổi hành vi).** Thêm `for_account(id)` vào `scripts/account_profile.py`, giữ
`for_venue()` như lớp vỏ cho trường hợp đúng một tài khoản định tuyến được trên venue đó.
Gỡ luật duy nhất `(venue, environment)` và thay bằng luật duy nhất **account id**. Test: hai hồ sơ cùng venue
cùng env được phép khi khác id; đường đặt lệnh vẫn phải nêu id, không được đoán.

**Pha 0b — bảng uỷ nhiệm.** `docs/architecture/mandates.json` + `scripts/mandates.py`. Chốt `setup_version`
tại thời điểm gắn (`scripts/setup_version.py` đã tính sẵn): khách đang thuê bản cũ tiếp tục chạy bản họ đã
đồng ý cho tới khi họ nhận bản mới. Thêm `owner` vào hồ sơ tài khoản (cổng tương quan đã đọc nó).

**Pha 1 — trạng thái theo tài khoản.** `--account <id>` cho `strategy-runner.py`; mọi đường dẫn ở nhóm B
thành `data/live/accounts/<id>/...`; mọi khoá ở nhóm A thêm chiều tài khoản; `client_id` thêm id.
`save_state` chuyển sang ghi tmp + `os.replace` (hiện đang `open(...,"w")` trần).

**Pha 2 — rủi ro theo tài khoản + trần tổng hợp.** `size()`/`mt5_lots()` nhận `risk_pct` làm **tham số**, lấy
từ `AP.effective_risk_pct(profile_của_tài_khoản)` thay vì biến module. `scripts/exposure.py` + gọi nó trong
`tick()` trước bước đặt lệnh. Trần tổng hợp khai trong `risk-config.json` (nguồn duy nhất đã có).

**Pha 3 — khoá theo tài khoản.** `config/env.<env>.<account-id>`, `trading_env` nhận account id.
`key-scope.json` đổi khoá thành `(provider, account)`. Adapter shell nhận biến môi trường có tiền tố.
**Đây là ranh giới tin cậy** — phải có Security review trước khi viết code.

**Pha 3b — tách phân tích khỏi thực thi** (§3b, quan điểm người dùng). `scripts/signal-publisher.py` +
`scripts/signal-worker.py`; `tick()` tách làm hai. Không phụ thuộc vào setup nào sống sót sau lần xếp hạng
lại — đây là hạ tầng. Phải sau Pha 1–2 vì worker cần state và rủi ro theo tài khoản.

**Pha 4 — supervisor.** `scripts/supervisor.py` + một launchd plist mỗi tài khoản (hoặc một supervisor duy
nhất sinh con). Thay ô `pilot_process` đơn bằng bảng. `STOP` hai tầng: STOP toàn hệ + STOP mỗi tài khoản.

**Pha 5 — bộ công cụ theo uỷ nhiệm.** `enabled_symbols`/`allowed_methods` nhận **mandate**, không phải market:
tài khoản chạy đúng những setup mà uỷ nhiệm của nó khai, trên đúng thị trường của các setup đó. Đây là pha
thực sự cho phép "một tài khoản nhiều phương pháp, một phương pháp nhiều tài khoản".

**Pha 5b — quy kết, cô lập, thứ tự, sức chứa** (§0.3, bốn việc bắt buộc của mô hình cho thuê). Id lệnh mang
`(account, mandate, setup_version)`; `STOP` hai tầng; thứ tự khớp giữa các tài khoản được khai báo và ghi
lại; trần notional tổng theo mã. Đây là pha thực sự cho phép "mỗi tài khoản một phương pháp".

**Pha 6 — giới hạn thật.** MT5: N terminal. Crypto: rate limit per-key cần đo trước khi chạy >10 tiến trình.

---

## 6. Đề nghị thứ tự

Pha 0→2 là thứ nên làm **ngay cả khi mãi mãi chỉ có 2 tài khoản**: nó sửa một lỗi thật (rủi ro theo tài khoản
không tới được đường tính khối lượng) và thêm một cổng an toàn còn thiếu (phơi nhiễm tổng hợp).

Pha 0b nên đi ngay sau Pha 0: bảng uỷ nhiệm là nơi "khách thuê phương pháp gì" được ghi, và mọi pha sau đều
đọc nó. Pha 5b là điều kiện để nhận **khách thật** — quy kết và cô lập không phải tính năng, là nghĩa vụ. Việc tìm thêm phương pháp là
việc riêng, đang chạy song song, và không nên bị trộn vào đây.
