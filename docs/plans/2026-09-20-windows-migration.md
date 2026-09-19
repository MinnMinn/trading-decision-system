# Chuyển sang Windows — kế hoạch

**Yêu cầu người dùng (2026-09-19):** *"Chúng ta sẽ chuyển sang máy Windows vào ngày mai. Hãy lên kế hoạch trước."*

Động cơ đã rõ từ câu hỏi trước: trên Windows, gói `MetaTrader5` của MetaQuotes **chạy được**, và nó tốt hơn
cầu nối file về mọi mặt. Bằng chứng nó **không** chạy được ở đây, chạy trên chính máy này 2026-09-19:

```
$ pip3 download MetaTrader5 --no-deps
ERROR: Could not find a version that satisfies the requirement MetaTrader5 (from versions: none)
```

Không có bản phân phối nào cho nền tảng này. Đó là lý do repo dùng cầu nối file (`mt5-bridge.md:14`).

---

## 0. Nguyên tắc: **hai thay đổi, hai ngày, không trộn**

Chuyển hệ điều hành **và** đổi cách nói chuyện với MT5 là hai thay đổi độc lập. Làm cùng lúc thì khi có lỗi
sẽ không biết cái nào gây ra.

- **Ngày 1 — chạy y nguyên hệ hiện tại trên Windows**, kể cả cầu nối file. Mục tiêu duy nhất: **parity**.
  Suite xanh, `--replay` khớp, một lệnh demo đi trọn vòng.
- **Ngày 2+ — đổi MT5 sang Python API**, sau khi ngày 1 đã xanh.

Repo đã có sẵn chỗ để đổi: `docs/architecture/providers.json` khai `mt5_bridge → scripts/mt5-order-bridge.py`.
Đổi adapter là **một dòng registry**, không phải sửa engine (`CLAUDE.md` §2/§4).

---

## 1. Kiểm kê: cái gì thật sự phụ thuộc hệ điều hành

Đã đo, không đoán. Từ Python, **đường đặt lệnh live chỉ gọi 2 script shell**: `get-secret.sh` và
`pilot-loop.sh`. Ngoài ra `providers.json` khai 3 adapter bash:

| Thành phần | Dòng | Rủi ro trên Windows |
|---|---|---|
| `fetch-binance-klines.sh` | 74 | cần `bash`, `curl`, `jq` |
| `binance-futures-testnet-order.sh` | 204 | cần `bash`, `curl`, `jq`, `openssl`; **ký HMAC** |
| `binance-testnet-order.sh` | 254 | như trên (spot, hiện không dùng) |
| `get-secret.sh` | 12 | **`security find-generic-password` = Keychain của macOS. Không có tương đương trên Windows.** |
| `pilot-loop.sh` | 54 | `nohup`, `rmdir` làm lock, `date -u -j -f` (**cú pháp BSD**, Git Bash dùng `-d`) |

Những chỗ khác, không nằm trên đường đặt lệnh nhưng sẽ vỡ:

- **launchd** (`integrations/launchd/*.plist`) → Windows dùng **Task Scheduler**.
- **symlink** `data/live/mt5-bridge` → trên Windows dùng **junction** (`mklink /J`), chạy được **không cần
  quyền admin**, khác với symlink.
- **`chmod 600`** trên `config/env.*` (`verify-automation-v3.sh:30`) → Windows dùng **ACL** (`icacls`).
  Đây là ràng buộc an ninh trong `CLAUDE.md`, không được bỏ, phải **dịch** sang ACL.
- `flock` (1 chỗ), `pkill`, `/usr/bin/time` — chỉ trong script phụ trợ và kiểm thử.

**Cái KHÔNG đổi:** toàn bộ phân tích, backtest, registry, test — Python thuần, không phụ thuộc hệ điều hành.
Đó là phần lớn nhất của repo và nó sang Windows không cần sửa gì.

---

## 2. Quyết định kiến trúc: **viết lại 3 adapter Binance bằng Python**, không phải làm cho bash chạy được

Bash + `jq` + `curl` + `openssl` trên Windows là cài Git Bash rồi vá từng khác biệt (`date` BSD vs GNU,
`jq` phải cài riêng, đường dẫn, dòng CRLF). Mỗi cái là một chỗ hỏng thầm lặng trên **đường đặt lệnh**.

Python **đã là** điều kiện bắt buộc của hệ thống. Viết lại 3 adapter bằng Python (tổng 532 dòng bash, phần
lớn là parse JSON và ký HMAC — cả hai Python làm gọn hơn) **xoá hẳn** phụ thuộc bash khỏi đường đặt lệnh và
biến việc chuyển Windows thành chuyện không đáng kể.

Đây **không** phải "viết lại cho vui": `providers.json` đã coi adapter là dữ liệu, nên đổi là đổi một entry,
và có `scripts/tests/test_execution_router.py` giữ hành vi. Làm trước khi chuyển máy thì ngày 1 nhẹ hẳn.

**`get-secret.sh`** cũng phải đi theo: Keychain không có trên Windows. Thay bằng một reader Python duy nhất
đọc được cả hai nguồn — Keychain trên macOS, **Windows Credential Manager** trên Windows — giữ nguyên cú pháp
`keychain:<service>[@<account>]` đã khai trong `CLAUDE.md`, để không registry nào phải sửa.

---

## 3. Ngày 1 — danh sách việc, theo thứ tự

1. **Trước khi rời máy Mac**: chạy suite đầy đủ, ghi lại con số; chạy `--replay` và lưu output làm **mốc
   parity**. Không có mốc thì không chứng minh được gì trên máy mới.
2. Cài trên Windows: Python (cùng phiên bản minor), Git, MT5 terminal, `pip install MetaTrader5` (để sẵn cho
   ngày 2, chưa dùng).
3. Clone repo. **Không** copy `config/env.*` qua mạng — tạo lại tại chỗ và đặt ACL.
4. Dịch bí mật: nhập lại vào Windows Credential Manager, trỏ reader mới vào đó.
5. Trỏ `data/live/mt5-bridge`: `mklink /J` tới `%APPDATA%\MetaQuotes\Terminal\Common\Files`.
6. Biên dịch lại `OrderBridge.mq5` trong MetaEditor, gắn vào chart, bật Algo Trading.
   **Nhớ đặt `InpBridgeDir`** nếu chạy nhiều tài khoản.
7. Chạy `python scripts/mt5-order-bridge.py check` → phải in `"demo": true`.
8. Chạy suite. So với mốc ở bước 1.
9. Chạy `--replay` cùng tham số. So với mốc.
10. Một lệnh demo trọn vòng: đặt → đọc lại → sửa SL → đóng. Đúng quy trình đã ghi ở `mt5-bridge.md:9`.
11. Task Scheduler thay launchd, **chỉ sau khi** 8–10 xanh.

**Tiêu chí xong ngày 1:** suite cùng số lượng pass, replay khớp mốc, một lệnh demo trọn vòng. Nếu bất kỳ cái
nào lệch, dừng và tìm nguyên nhân — **không** chuyển sang ngày 2.

---

## 4. Ngày 2+ — đổi MT5 sang Python API

Viết `scripts/mt5-api-adapter.py` cùng giao diện dòng lệnh với `mt5-order-bridge.py` (`check`, `account`,
`symbol`, `limit`, `market`, `cancel`, `close`, `position-status`, `order-status`), rồi đổi một entry trong
`providers.json`. Engine không biết gì cả.

**Cái API gỡ bỏ được:**

- cuộc đua **đọc-rồi-xoá** file trả lời — biến mất, vì gọi đồng bộ;
- một thư mục cầu nối cho mỗi tài khoản (`InpBridgeDir`) — không còn cần;
- độ trễ poll 1 s của EA (`InpPollMs`);
- bước biên dịch/gắn EA bằng tay cho mỗi terminal.

**Cái API KHÔNG gỡ được, và phải nói rõ:**

- **một terminal một tài khoản vẫn đúng.** Gói Python giữ **một** kết nối cho mỗi tiến trình, nên N khách vẫn
  là N terminal và N tiến trình. API bỏ cuộc đua file, **không** bỏ số terminal.
- Vì vậy `bind_account()`, kill switch hai tầng, và cổng `exposure` vẫn nguyên giá trị.

**Giữ lại kiểm tra danh tính** (`mt5_assert_identity`): với API nó rẻ hơn và vẫn đúng lý do — xác minh terminal
đang trả lời **đúng là** tài khoản tiến trình này định giao dịch, trước khi đặt bất cứ thứ gì.

**Và giữ EA export OHLCV.** Nến CFD đang đến từ `ExportOHLCV.mq5`; API cũng lấy được nến
(`copy_rates_from_pos`), nhưng đó là thay đổi **thứ ba** và không thuộc ngày 2. Một việc một lần.

---

## 4b. Tương tác với quyết định Redis Streams (cùng ngày)

Người dùng chọn **Redis Streams** làm broker cho fan-out tín hiệu
(`docs/plans/2026-09-19-multi-account.md` §3b.4). Nó đụng thẳng vào việc chuyển máy này:

**Redis không có bản Windows chính thức.** Bốn đường đi, chưa cái nào được kiểm chứng ở đây:

| Đường | Được | Mất |
|---|---|---|
| **WSL2** | Redis Linux thật, miễn phí | Thêm một lớp; mạng WSL↔Windows phải thông tới worker |
| **Docker Desktop** | Redis thật, tái lập được | Cần Docker Desktop (giấy phép cho doanh nghiệp), thêm một daemon |
| **Memurai** | Chạy native Windows, tương thích Redis | Sản phẩm thương mại; phải xác nhận có `XAUTOCLAIM` |
| **Host Linux riêng** | Sạch nhất về vận hành | Bản tin đi qua mạng → phải tính bảo mật và độ trễ |

**Thứ tự bắt buộc: Redis đi SAU khi ngày 1 đã xanh.** Chuyển hệ điều hành và thêm một hạ tầng mới cùng lúc thì
lỗi nào cũng không quy được cho ai. Ngày 1 chạy bản file của seam (`publish`/`claim`/`ack`), không phụ thuộc
Redis chút nào — đó là lý do seam được vẽ trước khi chọn broker.

---

## 5. Rủi ro đã biết

- **Bí mật đi qua mạng.** Đừng copy `config/env.*`. Nhập lại tại chỗ. `CLAUDE.md` cấm commit/echo chúng và
  việc chuyển máy là lúc dễ vi phạm nhất.
- **Dòng CRLF.** Git trên Windows có thể đổi kết thúc dòng và làm hỏng script shell còn lại; đặt
  `core.autocrlf=false` hoặc thêm `.gitattributes` trước khi clone.
- **Múi giờ.** Mọi thứ trong repo dùng UTC. Máy Windows đặt sai múi giờ sẽ không làm sai dữ liệu nhưng sẽ làm
  sai mọi log và mọi cửa sổ phiên đọc từ đồng hồ cục bộ.
- **Broker khác nhau về symbol.** `mt5-bridge.md:9` đã ghi: broker hiện tại có XAUUSD/XAGUSD nhưng **không có**
  USOIL/UKOIL. Kiểm lại trên terminal mới trước khi tin bất kỳ setup CFD nào.

- **Redis trên Windows** — xem §4b. Chọn đường đi trước, đừng để nó thành việc phát sinh giữa ngày 1.
- **Bí mật đã chuyển chưa?** `scripts/get_secret.py` (viết 2026-09-19) đọc được Windows Credential Manager,
  nhưng nó chỉ đọc cái đã có ở đó. Nhập lại toàn bộ trước lần chạy đầu, và kiểm bằng cách gọi thẳng
  `python scripts\get_secret.py <service> <account>` cho từng khoá — nó in ra stdout và **không** log.
