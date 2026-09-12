# Prompt cho session mới — chạy pilot tự động cho Top 5 setup ổn định nhất

> **Đã thực hiện trong phiên 2026-09-11** (không cần session mới): plan `docs/plans/2026-09-11-top5-pilot-profile.md`, review an toàn `docs/security/2026-09-11-top5-pilot.md`, parity `docs/backtests/2026-09-11-runner-parity.md`. Lưu ý: trong lúc làm phát hiện lỗi nhìn-trước trong backtest ICT; xếp hạng "top 5" ban đầu không còn đúng — xem SYSTEM-DESIGN §9.y trước khi bật profile.

Copy toàn bộ phần dưới dấu `---` vào session mới trong `/Users/tungnguyen/TYME/Trading`. Trước khi dán, quyết định hai việc ghi ở mục 0.

---

## 0. Quyết định của tao (điền trước khi chạy)

- Môi trường: **demo** (Binance Futures TESTNET, tiền giả) — `docs/architecture/automation-config.json → execution.environment = "demo"`. KHÔNG đổi sang `real` trong session này. Chuyển sang real là quyết định riêng sau khi pilot testnet đạt tiêu chí ở mục 6.
- Thời gian pilot: 6 tuần hoặc tới khi đủ 60 lệnh đóng (cái nào tới trước), sau đó dừng và báo cáo.
- Vốn tham chiếu để tính rủi ro: số dư USDT thực trên testnet (không giả định $10.000).

## 1. Bối cảnh (đọc trước, không làm gì khác)

Đọc theo thứ tự: `docs/architecture/SYSTEM-DESIGN.md` (đặc biệt §9 pilot, §13 một người ghi một file, §14 chính sách model), `docs/backtests/2026-09-11-stability-by-timeframe.md` (mục "Cách đọc" và bảng xếp hạng), `scripts/backtest-methods.py` (docstring + hàm `find_ict`, `fvg_fill`, `walk`, `htf_position`, `htf_allows`, `simulate`), `scripts/wyckoff_rules.py` (docstring), `scripts/demo-pilot.py` (docstring + `evaluate`, `place_long`, `check_exit_futures`, cổng `/automation`), `scripts/binance-futures-testnet-order.sh` (usage header), `scripts/pilot-loop.sh`, `scripts/journal.py`, `docs/architecture/analysis-params.json`.

Luật cứng không được vi phạm: bảo toàn vốn; chỉ BTCUSDT/ETHUSDT/SOLUSDT; rủi ro ≤ 1 % vốn mỗi lệnh; đòn bẩy ≤ 3, ISOLATED; không bao giờ tự bật/tắt `/automation` (đó là công tắc của tao); không bao giờ ghi khoá/secret vào file hay transcript (Keychain qua `scripts/get-secret.sh`); một người ghi một file; số từ code, chữ từ model; không lệnh nào do LLM quyết — mọi lệnh phải là luật cơ khí.

## 2. Top 5 phải chạy (từ bảng xếp hạng 2026-09-11, cả long lẫn short)

| # | Khung | Luật vào | Cấu hình | Backtest 4 năm |
|---|---|---|---|---|
| 1 | 30m | ICT | B: limit maker + hoà vốn +1R, không lọc khung lớn | +76 %/năm, 94 % quý dương, DD −23 % |
| 2 | 30m | KẾT HỢP | B | +70 %/năm, 94 % quý dương, DD −13 % |
| 3 | 1H | ICT | B | +45 %/năm, 88 % quý dương, DD −14 % |
| 4 | 30m | ICT | C: B + lọc khung lớn 2H | +44 %/năm, 88 % quý dương, DD −19 % |
| 5 | 30m | KẾT HỢP | C: B + lọc khung lớn 2H | +49 %/năm, 88 % quý dương, DD −11 % |

Thực chất là 3 luật (ICT 30m, KẾT HỢP 30m, ICT 1H) × có/không lọc khung lớn. Chạy #4 và #5 như **cùng tín hiệu** với #1/#2 nhưng gắn nhãn `htf_pass: true/false` trong nhật ký để so sánh, KHÔNG mở lệnh trùng: mỗi mã tối đa một vị thế, tín hiệu #1 và #2 trùng nến thì ưu tiên KẾT HỢP (stop chặt hơn về cấu trúc).

Định nghĩa luật = đúng code backtest, không diễn giải lại:
- Tham số khung: `P["30m"] = R 48, K 14, T 14, H 84, sob 5`; `P["1H"] = R 48, K 12, T 12, H 72, sob 4` (backtest-methods.py).
- ICT: quét pivot 3 nến gần nhất (`last_pivot`), MSS = nến đóng thân qua pivot ngược chiều trong K nến (`find_ict`), FVG 3 nến theo wick trong nhịp sweep→MSS, **vào bằng LIMIT tại mép gần FVG** (`fvg_fill`: giá quay về mép trong K nến sau MSS; không quay về = không vào), stop = cực trị của cú sweep − 0,05 %, target = đỉnh/đáy R nến trước (thanh khoản đối diện). Không dùng khối lượng.
- KẾT HỢP: Spring/Upthrust proxy (đáy/đỉnh xuyên biên R nến, đóng lại trong 0–2 nến, loại KL theo `analysis-params.json`; loại 3 chỉ khi nến đóng lại có KL ≥ 1,5×) + xác nhận ICT như trên; vào limit tại mép FVG, không quay về thì vào tại nến đóng MSS (market); stop = đáy/đỉnh Spring − 0,05 %; target = biên đối diện.
- Quản lý: khi giá chạm +1R, dời stop về giá vào (WMT p272). Hết H nến chưa đóng → đóng market (time stop).
- Lọc khung lớn (#4/#5): `htf_allows` — long chỉ khi 2H đang ở phần ba dưới vùng R nến của nó hoặc đã phá lên; short ngược lại.
- Phí: limit post-only (GTX) cho lệnh vào; nếu bị từ chối vì sẽ khớp ngay thì bỏ tín hiệu đó (không đuổi bằng market, vì kết quả #1/#3/#4 phụ thuộc phí maker — xem "Cách đọc" trong báo cáo ổn định).

## 2b. Profile lấy thông tin ở đâu (một nguồn, ba lớp)

- **Định nghĩa profile** = file mới `docs/architecture/pilot-profiles.json` (schema `docs/architecture/schemas/pilot-profiles.schema.json`). Đây là nơi duy nhất nói "top5 gồm những gì". Mẫu:

```json
{
  "schema_version": 1,
  "profiles": {
    "legacy": {"runner": "scripts/demo-pilot.py", "note": "pilot 15m sweep→MSS→FVG, luật trong docstring của demo-pilot.py"},
    "top5": {
      "runner": "scripts/strategy-runner.py",
      "source": "docs/backtests/2026-09-11-stability-by-timeframe.md",
      "market": "futures",
      "entry_order": "limit_post_only",
      "management": {"breakeven_at_R": 1.0, "time_stop": "H bars of the timeframe"},
      "halt": {"equity_drawdown_pct": 15, "consecutive_losses": 5, "connection_errors": 3},
      "strategies": [
        {"id": "ict-30m",      "tf": "30m", "rule": "ICT",      "htf_filter": false, "rank": 1},
        {"id": "combined-30m", "tf": "30m", "rule": "COMBINED", "htf_filter": false, "rank": 2},
        {"id": "ict-1h",       "tf": "1H",  "rule": "ICT",      "htf_filter": false, "rank": 3},
        {"id": "ict-30m-htf",  "tf": "30m", "rule": "ICT",      "htf_filter": true,  "rank": 4, "shadow_of": "ict-30m"},
        {"id": "combined-30m-htf", "tf": "30m", "rule": "COMBINED", "htf_filter": true, "rank": 5, "shadow_of": "combined-30m"}
      ]
    }
  }
}
```
  `shadow_of` = cùng tín hiệu với strategy gốc, chỉ gắn nhãn `htf_pass` trong journal, không mở lệnh riêng.
- **Luật và tham số số** KHÔNG chép vào file này. Runner import thẳng `scripts/backtest-methods.py` (`P["30m"]`, `P["1H"]`, `find_ict`, `fvg_fill`, `htf_position`, `htf_allows`, `STOP_BUFFER_PCT`, `RISK`) và `scripts/wyckoff_rules.py`, cùng `docs/architecture/analysis-params.json` cho ngưỡng khối lượng. Một nguồn: đổi số trong backtest là runner đổi theo, và kiểm tra tương đương (bước 4) chứng minh hai bên cùng luật.
- **Công tắc** `docs/architecture/automation-config.json → execution.pilot_profile` chỉ chứa *tên* profile. `/automation pilot profile top5` làm đúng ba việc: kiểm tra tên có trong `pilot-profiles.json`, kiểm tra `runner` tồn tại và thị trường phù hợp, ghi tên + history. Không sao chép nội dung profile vào config.
- **Lúc chạy**: `pilot-loop.sh` hỏi `automation.py status --json` lấy tên profile → mở `pilot-profiles.json` lấy `runner` → mỗi tick gọi runner với `--profile top5`; runner đọc lại `pilot-profiles.json` mỗi tick (đổi profile giữa chừng có hiệu lực ở tick sau, không cần restart), ghi `profile`, `strategy`, `htf_pass` vào từng bản ghi journal.

## 3. Việc phải làm, theo thứ tự (không nhảy bước)

1. **Tạo `docs/architecture/pilot-profiles.json` + schema** như mục 2b, kèm test đọc/validate trong `scripts/tests/`.
2. **Thêm khung 30m vào tầng dữ liệu**: `scripts/automation.py` (`MARKET_TIMEFRAMES["crypto"]`, `TIMEFRAMES`, `STYLE`, `CONTEXT_STYLE` 30m→2H nếu cần), `scripts/scan-loop.sh` (fetch 30m và 2H, 300 nến, tại phút 00/30), `scripts/fetch-binance-klines.sh` (interval 30m, 2h), `docs/architecture/schemas/automation-config.schema.json` và `automation-config.json`. Giữ một người ghi một file: scanner là người ghi duy nhất của `data/live/market-data/`.
3. **Thêm lệnh LIMIT post-only vào connector** `scripts/binance-futures-testnet-order.sh`: `open-long-limit <SYM> <QTY> <PRICE>` / `open-short-limit` với `type=LIMIT&timeInForce=GTX`, `order-status`, `cancel-order` đã có. Giữ nguyên allowlist, ISOLATED, đòn bẩy ≤ 3, không in secret. Kiểm tra bằng `check` rồi một lệnh limit xa giá trên testnet và huỷ.
4. **Viết `scripts/strategy-runner.py`** (mới, không sửa luật của `demo-pilot.py`): import trực tiếp `backtest-methods.py` (qua importlib) và dùng đúng các hàm trên nến live `data/live/market-data/ohlcv.<SYM>.<30m|1H>.json`; trạng thái ở `data/live/pilot-futures/` (cùng thư mục, cùng kill switch STOP với pilot cũ, để `/automation off` vẫn dừng được nó); mỗi tick tại nến đóng: (a) cổng `python3 scripts/automation.py allows pilot` phải exit 0, môi trường phải là demo, không blackout sự kiện (`event_blackout` như demo-pilot), (b) sinh tín hiệu cho 3 luật, (c) đặt limit GTX + kích thước = rủi ro 1 % / khoảng stop, notional cap như demo-pilot, (d) khi khớp: đặt STOP_MARKET và TAKE_PROFIT_MARKET closePosition, (e) quản lý: huỷ limit chưa khớp sau K nến, dời stop về entry khi +1R, time stop sau H nến, (f) ghi mỗi sự kiện vào journal qua `scripts/journal.py` với `strategy` ∈ {ict-30m, combined-30m, ict-1h} và `htf_pass`, `config` = B/C. Tự dừng (ghi STOP + lý do) khi: vốn giảm 15 % so với lúc bắt đầu, 5 thua liên tiếp, hoặc lỗi kết nối 3 tick liên tiếp.
5. **Kiểm tra tương đương (bắt buộc trước khi chạy live testnet)**: chạy runner ở chế độ `--replay` trên `data/history/ohlcv.<SYM>.30m.json` 500 nến cuối và so với `backtest-methods.py --tf 30m --fee-pct 0.02 --mgmt be` cùng đoạn: cùng danh sách tín hiệu (thời gian, chiều, entry, stop, target). Ghi kết quả vào `docs/backtests/2026-09-XX-runner-parity.md`. Sai lệch bất kỳ → sửa runner, không sửa backtest.
6. **Nối vào `/automation` bằng một profile, KHÔNG tạo vòng lặp hay launchd agent mới**:
   - `docs/architecture/automation-config.json` + schema: thêm `execution.pilot_profile` ∈ {`legacy`, `top5`} (mặc định `legacy`); `scripts/automation.py` là người ghi duy nhất của file này nên thêm subcommand `pilot profile <legacy|top5>` (audited, ghi history) và in profile trong `status`.
   - `scripts/pilot-loop.sh`: đọc profile qua `automation.py status --json`; `top5` → mỗi tick chạy `strategy-runner.py --live` thay cho `demo-pilot.py`, tick tại phút 00 và 30 (30m) và runner tự bỏ qua luật 1H khi chưa tới giờ chẵn. Thị trường `spot` không dùng profile top5 (chỉ futures, vì có short).
   - Preset của `/automation demo` bật thêm khung 30m (và 2H cho lọc khung lớn) cho crypto để scanner có dữ liệu; `timeframe` subcommand nhận `30m`.
   - Kết quả: vận hành chỉ còn `/automation pilot profile top5` một lần, rồi `/automation demo` (hoặc `on`) để chạy, `/automation off` để dừng, `/automation status` / `pilot status` để xem. Hai profile không bao giờ chạy song song vì cùng một loop.
7. **Test thật trên testnet** với một tín hiệu: tao sẽ tự gõ `/automation pilot profile top5` rồi `/automation demo`; session chỉ chuẩn bị cờ `--force-signal` (chỉ hoạt động khi môi trường là demo) để xác nhận đường đi limit → khớp → stop/TP → hoà vốn → journal, rồi xoá cờ sau khi test.
7. Cập nhật `docs/architecture/SYSTEM-DESIGN.md` §9 (pilot top5), `docs/architecture/data-sources.md` (30m/2H), `trades/README.md`, và `integrations/crons/journal-publish.md` nếu trang nhật ký cần thêm cột strategy. Không commit trừ khi tao bảo.

## 4. Định tuyến theo rules toàn cục của tao

Việc này chạm tiền và API bên ngoài → trust boundary → **full workflow**: brainstorming ngắn → plan (`writing-plans`) → Security subagent (đọc `docs/security/` nếu có, kiểm tra: secret chỉ qua Keychain, allowlist, đòn bẩy, kill switch, môi trường demo cứng) → triển khai từng bước ở mục 3 theo `subagent-driven-development` với TDD (`scripts/tests/`) → QA. Mỗi dispatch theo `rules/dispatch-prompt-contract.md`.

## 5. Không được làm

- Không chuyển `execution.environment` sang `real`. Không tự gõ `/automation on|demo|pilot profile` — đó là việc của tao sau khi bước 5 và 7 đạt. Không tăng rủi ro quá 1 %. Không dùng market để đuổi lệnh limit hụt. Không thêm luật mới ngoài 3 luật trên (muốn thêm → `/improve`). Không cho model quyết định lệnh. Không sửa `scripts/backtest-methods.py` hay `wyckoff_rules.py` để "khớp" với runner.

## 6. Tiêu chí kết thúc pilot và báo cáo

Sau 6 tuần hoặc 60 lệnh đóng: `python3 scripts/journal.py all` rồi báo cáo theo strategy × htf_pass: số lệnh, tỉ lệ thắng, R ròng trung bình (đã trừ phí thật của testnet), PF, sụt giảm tối đa, tỉ lệ limit bị huỷ vì không khớp, so với backtest cùng đoạn (chạy `backtest-methods.py` trên `data/history` đã fetch thêm tới ngày báo cáo). Chỉ khi (a) R ròng trung bình ≥ 0 cho ít nhất 2/3 luật, (b) sụt giảm ≤ 15 %, (c) tỉ lệ khớp limit ≥ 60 %, thì đề xuất qua `/improve` việc chuyển sang real với rủi ro 0,5 % — quyết định cuối là của tao.
