# Công tắc phương pháp vào lệnh + registry phương pháp (thiết kế, duyệt 2026-09-12)

**Vấn đề.** Hệ thống có hai tầng dùng chung từ vựng "phương pháp" nhưng rời nhau, và không tầng nào đổi được nhanh:

- Tầng phân tích: `docs/architecture/automation-config.json` → `markets.<crypto|cfd>.dimensions`, bốn cờ
  `wyckoff / ict / footprint / heatmap` (SYSTEM-DESIGN.md §6.2). Đổi bằng `/automation dimension <tên> <on|off>`,
  từng cờ một, chỉ ở terminal.
- Tầng pilot: `scripts/strategy-runner.py:86` `METHODS = ("ICT", "COMBINED", "WYCKOFF", "WYCKOFF-BOOK")`, chọn
  qua `docs/architecture/pilot-top5.json` và `execution.pilot_profile`. Không liên quan gì tới bốn cờ trên.

Không có khái niệm "đang chạy phương pháp nào", không có chỗ nào đổi được từ ngoài máy, và thêm một phương pháp
hay một dimension mới phải sửa tay nhiều bản sao.

**Quyết định.** Một **preset** có tên điều khiển cả hai tầng. Preset chỉ là *tên gọi* của một tập bốn cờ dimension
đã có — không thêm trường nào vào `automation-config.json`, không bump `schema_version`. Định nghĩa preset,
dimension và runner method chuyển vào một registry JSON mới, song sinh với `instruments.json`. Một trang Artifact
hiển thị và cho chạm chọn; một cron Claude đọc lựa chọn đó và áp dụng.

---

## 1. Quyết định đã chốt

1. Một preset điều khiển **cả** tầng phân tích lẫn tầng pilot.
2. Vòng lặp về máy: trang ghi vào `db` của Artifact; một cron Claude đọc `db` rồi chạy `scripts/automation.py`.
   Trang Artifact không ghi được vào repo; chỉ phiên Claude đọc được `db` của nó.
3. Preset lọc runner method nào được phép bắn. Preset không khớp method nào → pilot không đặt lệnh mới nào.
4. Sáu preset, **chọn riêng từng market**: `wyckoff`, `ict`, `wyckoff+ict`, `wyckoff+footprint`,
   `wyckoff+ict+footprint`, `full`. cfd chỉ hiện ba preset đầu (không có nguồn CoinGlass cho hàng hoá, §12 item 3).
5. **Không chặn theo môi trường.** Cron áp dụng ở cả `demo` lẫn `real`. Người dùng đã được cảnh báo và chọn như vậy.
6. Hai preset một-phương-pháp (`wyckoff`, `ict`) **giữ lại**, nằm nhóm riêng "chỉ nghiên cứu": dưới tối thiểu 2
   dimension của NORMAL (§6.1) nên `/analyze` không bao giờ ra được TRADE, trong khi pilot cơ học vẫn bắn.
   Điều này được in thẳng lên thẻ preset, không giấu.
7. Đổi sang preset hẹp hơn: **giữ nguyên tất cả lệnh in-flight** (grandfather). Vị thế và lệnh limit đang chờ chạy
   tiếp tới khi đóng tự nhiên theo luật của chính nó; preset chỉ lọc tín hiệu **mới**.
8. Phạm vi market: **crypto và cfd, hết**. Họ thị trường thứ ba nằm ngoài lần này (§9).

---

## 2. Hai lỗi của bản nháp đầu, và cách bản này tránh

Ghi lại vì cả hai đều là bẫy sẽ tái diễn nếu ai đó "đơn giản hoá" lại.

**2.1 Cờ `wyckoff` và `ict` hôm nay là cờ chết.** `.claude/commands/analyze.md:27` ghi *"structure-agent — always
dispatched (Wyckoff + ICT)"*; `scripts/build-artifact.py:281` hardcode `cols = ["wyckoff", "ict"] + [...]`. Không
chỗ nào đọc hai cờ đó. Nên hôm nay `wyckoff`, `ict`, `wyckoff+ict` **giống hệt nhau** ở tầng phân tích. Muốn công
tắc có nghĩa thì phải làm hai cờ đó có thật — đây là thay đổi hành vi của tầng phân tích, nêu rõ chứ không lén (§4.2).

**2.2 Lọc method ở `load_setups()` sẽ bỏ rơi lệnh đang mở.** `scripts/strategy-runner.py:718-719`:

```python
s = load_state(); setups_cfg = load_setups()
if not setups_cfg:
    log("halt", why=...); return
```

`return` này nằm **trước** khối huỷ pending của STOP file (`:720`), trước `automation_gate()` (`:728`), trước quản lý
vị thế (`:781`) và trước quản lý pending (`:786`). Một preset không khớp method nào sẽ làm tick thoát sớm:

- `manage_position` không chạy → mất breakeven, mất time stop, không ghi `close_record`, không cộng `consec_losses`.
- Lệnh limit futures đang chờ **không có stop đi kèm**: `place_limit:543` chỉ gửi `open-long-limit`; SL/TP mãi tới
  `open_position:596-597` mới đặt sau khi `manage_pending` thấy khớp. Tick thoát sớm → limit khớp thành vị thế đòn
  bẩy **không stop, không TP**, vô thời hạn.

Vì vậy bộ lọc preset **chỉ đặt ở bước 3 của tick**, không bao giờ ở `load_setups()` (§4.3).

---

## 3. Registry — `docs/architecture/methods.json`

Nguyên tắc phạm vi: **chỉ đưa lên JSON thứ hôm nay đã có từ hai bản sao trở lên.** `STYLE`, `MARKET_TIMEFRAMES`,
`DATA_DIR`, thang `TIERS` trong `automation.py` mỗi thứ chỉ một bản và mọi script đã import từ đó — không đụng.

Hôm nay đang lệch:

| Thứ | Các bản sao |
|---|---|
| tập dimension | `automation.py:80 MARKET_DIMENSIONS`, `schemas/automation-config.schema.json` (chép tay), `build-artifact.py:90 LANES` |
| tập runner method | `strategy-runner.py:86 METHODS`, `rank-setups.py:35 RUNNABLE` |

### 3.1 Hình dạng

```jsonc
{
  "schema_version": 1,
  "dimensions": {
    "wyckoff": {
      "label": "Wyckoff", "markets": ["crypto", "cfd"],
      "skill": "wyckoff-skill", "agent": "structure-agent",
      "data_sources": ["ohlcv"], "max_points": 25, "lane": "wyckoff"
    },
    "ict":       { "markets": ["crypto", "cfd"], "agent": "structure-agent", ... },
    "footprint": { "markets": ["crypto"], "agent": "flow-agent",      "data_sources": ["coinglass_footprint"], ... },
    "heatmap":   { "markets": ["crypto"], "agent": "liquidity-agent", "data_sources": ["coinglass_heatmap"],  ... }
  },
  "runner_methods": {
    "WYCKOFF":       { "requires": ["wyckoff"],        "runnable": true,  "scan": "wyckoff", "entry": "market" },
    "WYCKOFF-BOOK":  { "requires": ["wyckoff"],        "runnable": true,  "scan": "wyckoff", "entry": "market" },
    "ICT":           { "requires": ["ict"],            "runnable": true,  "scan": "ict",     "entry": "limit"  },
    "COMBINED":      { "requires": ["wyckoff","ict"],  "runnable": true,  "scan": "ict",     "entry": "limit"  },
    "COMBINED-BOOK": { "requires": ["wyckoff","ict"],  "runnable": false, "scan": "wyckoff", "entry": "market" },
    "PARTIAL":       { "requires": ["wyckoff","ict"],  "runnable": false, "scan": "ict",     "entry": "limit"  }
  },
  "presets": [
    { "id": "wyckoff",              "label": "Wyckoff",               "dimensions": ["wyckoff"],                                  "tier": "research" },
    { "id": "ict",                  "label": "ICT",                   "dimensions": ["ict"],                                      "tier": "research" },
    { "id": "wyckoff+ict",          "label": "Wyckoff + ICT",         "dimensions": ["wyckoff","ict"],                            "tier": "trade"    },
    { "id": "wyckoff+footprint",    "label": "Wyckoff + Footprint",   "dimensions": ["wyckoff","footprint"],                      "tier": "trade"    },
    { "id": "wyckoff+ict+footprint","label": "Wyckoff + ICT + Footprint","dimensions": ["wyckoff","ict","footprint"],             "tier": "trade"    },
    { "id": "full",                 "label": "Đầy đủ 4 chiều",        "dimensions": ["wyckoff","ict","footprint","heatmap"],      "tier": "trade"    }
  ],
  "history": [ { "date": "...", "change": "...", "reason": "...", "approved_by": "..." } ]
}
```

`runner_methods` định nghĩa trên cả **sáu** method của `backtest-methods.py:528`, không chỉ bốn method chạy được,
để ngày `rank-setups.py RUNNABLE` mở rộng thì không có method nào chưa ánh xạ.

### 3.2 Reader — `scripts/methods.py`

Song sinh với `scripts/instruments.py`. API:

- `DIMENSIONS`, `PRESETS`, `RUNNER_METHODS` — dữ liệu đã nạp
- `dimensions(market)` → tập dimension market đó có (thay `automation.py MARKET_DIMENSIONS`)
- `profile_of(dims)` → id preset hoặc `"custom"`. Nạp file kiểm bất biến: **tập dimension của mọi preset phải phân
  biệt đôi một**, nếu không `profile_of` không còn là hàm → raise ngay lúc import, như `instruments.py` raise khi
  `execution` không phải tập con của `analysis`.
- `runner_methods(dims)` → tập method mà `requires ⊆ dims`. Tra bảng, không phải quy tắc cứng.
- `presets_for(market)` → preset nào hợp lệ cho market (mọi dimension của nó phải khai báo market đó)
- `dispatch_plan(instrument)` → cho `analyze.md`: danh sách agent phải dispatch, và agent bỏ qua kèm lý do

### 3.3 Sync — `scripts/sync-methods.py --check|--write`

Song sinh với `sync-instruments.py`, cùng lý do: JSON Schema không `$ref` được enum ra file bất kỳ theo cách mọi
validator đều tôn trọng. Chỗ sinh lại:

- `schemas/automation-config.schema.json` → `properties.markets.properties.<m>.properties.dimensions.properties`
  và `.required`, sinh từ chính trường `markets[]` của mỗi dimension.

Nhờ sinh từ `markets[]`, tính chất §12 **"trạng thái bất khả thi vắng mặt khỏi hình dạng schema"** được giữ tự động:
cfd chỉ nhận dimension nào tự khai có cfd, và `additionalProperties: false` biến cấu hình sai thành lỗi validate chứ
không phải cờ bật rồi bị lờ đi lúc chạy.

`scripts/tests/test_methods_sync.py` chạy `--check` để lệch là fail build, y hệt `test_instruments_sync.py`.

### 3.4 Chỗ rò của instruments phải vá luôn

`scripts/build-artifact.py:35-45` giữ `CRYPTO_META` — danh sách song song chép tay (id ngắn, tên hiển thị, số lẻ giá)
— và `:46` làm `CRYPTO = [(sym, *CRYPTO_META[sym]) for sym in I.analysis("crypto")]`. Thêm token vào `instruments.json`
mà quên sửa chỗ này thì **build artifact KeyError**, và `sync-instruments.py` không phủ chỗ đó.

Sửa: chuyển metadata hiển thị vào `instruments.json` thành khối `display` **tuỳ chọn** (`{id, label, price_decimals}`),
`instruments.py` trả về giá trị suy ra khi thiếu (id = symbol viết thường bỏ hậu tố `USDT`, label = symbol, số lẻ = 2),
và đưa vào phạm vi `test_instruments_sync.py`. Sau đó thêm token thật sự là sửa đúng một file.

---

## 4. Thay đổi theo file

### 4.1 `scripts/automation.py`

- Bỏ hằng `MARKET_DIMENSIONS`, `DIMENSIONS` → dùng `methods.dimensions(market)`.
- Subcommand mới `method <preset> [--market crypto|cfd]`: đặt bốn cờ theo preset, ghi `history`. Từ chối (exit 2)
  preset không hợp lệ cho market đó, kèm lý do như `cmd_dimension` đang làm (`:957-981`).
- `status` in nhãn preset suy ra được, hoặc `custom` kèm bốn boolean thật.
- Subcommand mới `allows master`: chỉ kiểm `cfg["enabled"]`. Hôm nay `allows` chỉ nhận `scanner|local_read|pilot`
  (`:1272`), nên cron applier không có cách nào gate mà không chết theo một layer.
- `apply_preset` (`:867`) **thôi ghi đè** `dimensions`. Hôm nay `demo`/`real` làm `mk["dimensions"] = {d: True ...}`,
  tức là xoá sạch preset người dùng chọn. Thay bằng giữ nguyên và in `preset giữ nguyên: <id>`.
  `.claude/commands/automation.md:14` phải sửa theo.
- Ghi file nguyên tử: `load()` → sửa → `save()` (`:296-301`) hiện truncate-ghi-đè tại chỗ, không khoá. Giờ có thêm
  một tiến trình ghi (cron) nên: ghi ra `<path>.tmp` rồi `os.replace`, và `fcntl.flock` suốt quãng load→save.

### 4.2 Tầng phân tích — làm hai cờ có thật

- `.claude/commands/analyze.md` bước 5: thay danh sách agent chép tay bằng "chạy `python3 scripts/methods.py
  --dispatch-plan <instrument>`, dispatch đúng những agent nó liệt kê, nêu rõ agent bị bỏ qua và lý do nó in ra".
  Prompt vẫn cụ thể và ngắn; logic gating nằm trong script. Thêm dimension mới không phải sửa prompt.
- `scripts/build-artifact.py`: `LANES` (`:90`) đọc từ registry; `matrix()` (`:281`) lọc `cols` theo `dims` cho cả
  bốn lane thay vì hardcode `["wyckoff","ict"]`.

### 4.3 `scripts/strategy-runner.py` — lọc ở bước 3, grandfather

- `METHODS` (`:86`) import từ registry; `rank-setups.py:35 RUNNABLE` cũng vậy.
- `load_setups()` (`:142-146`) **không đụng tới**. Nó được gọi từ năm chỗ: `tick:718`, `replay:887`,
  `report_state:929`, `--tick-seconds:949`, `--list:952`. Lọc ở đó sẽ:
  - phá parity replay — `replay():893-895` có chú thích rõ *"Not config-gated — a market switched off still
    deserves its parity check"*;
  - đổi chu kỳ vòng lặp giữa chừng: `--tick-seconds` nuôi `scripts/pilot-loop.sh:37` vốn tính lại chu kỳ mỗi vòng,
    và danh sách rỗng cho `[] or ["30m"]` → 1800 giây;
  - làm `--list` in khác `pilot-top5.json`.
- Bộ lọc đặt ở **bước 3 của `tick()`** (`:833 for st in setups_cfg:` → lặp trên danh sách đã lọc), sau khi bước 1
  (vị thế) và bước 2 (pending) đã chạy. Mỗi setup mang sẵn `st["market"]` (`:834 due(st["tf"], t, st["market"])`)
  nên tra tập dimension theo market ngay tại đó được. Log dòng `preset_filtered` nêu tên setup và method bị chặn,
  để nhật ký giải thích vì sao một khung giờ im lặng.
- Early-return `if not setups_cfg` (`:718-719`) chuyển xuống **sau** bước 1 và 2, hoặc bỏ hẳn và để bước 3 lặp trên
  danh sách rỗng. Đây là bản vá cho §2.2.
- `--list` in `[preset: blocked]` cạnh setup bị chặn thay vì giấu dòng.
- **Grandfather** là hệ quả trực tiếp của chỗ đặt bộ lọc, ghi thành chú thích ngay tại đó: preset chỉ lọc tín hiệu
  mới; vị thế và pending cũ được quản lý tới khi đóng tự nhiên. Khớp triết lý reconcile sẵn có (`:818-831`, log
  `"no new entries there"`: không mở thêm ở đó, chứ không đóng cái đang có).

### 4.4 Trang điều khiển — `scripts/method-panel.py` → `data/live/.method-panel.html`

`capabilities: {db: {}}`. Hai cột market. Mỗi cột hai nhóm: **"đủ điều kiện vào lệnh"** (`tier: trade`) và
**"chỉ nghiên cứu"** (`tier: research`). cfd khoá ba preset có footprint/heatmap kèm lý do §12 item 3.

Mỗi thẻ preset in:
- tập dimension của nó;
- runner method được phép (từ `runner_methods()`);
- với `tier: research`: *"/analyze luôn NO TRADE — dưới tối thiểu 2 dimension của NORMAL (§6.1); chỉ pilot cơ học còn bắn"*;
- một dòng trung thực về tầng pilot: *"pilot chạy luật cơ học `scripts/wyckoff_rules.py` (CHoCH, TR từ SC/AR,
  Spring vs Shakeout, VP veto), không phải bài đọc Wyckoff đầy đủ của skill."* Dimension `wyckoff` trong `/analyze`
  và method `WYCKOFF` của runner là **hai thứ trùng tên**, không phải một; nói "pilot không kiểm chứng được
  footprint/heatmap" mà im về hai cái kia sẽ hàm ý sai rằng hai cái kia được pilot kiểm chứng.

Tương tác và trạng thái:
- Chạm → `db.doc("control/request.<market>").set({preset, requested_at})`.
- Trạng thái **đã áp dụng** đọc live từ `control/applied.<market>` (cron ghi), nên cron không phải publish lại trang.
- `custom` → không thẻ nào sáng, in bốn boolean thật kèm *"đặt từ terminal — chạm một preset để ghi đè"*.
  Trạng thái này bình thường và tới được, vì `dimension x on|off` vẫn còn (`:957-981`) và 10/16 tổ hợp là `custom`.
- Banner khi `control/heartbeat` cũ hơn 12 phút: *"không có tiến trình áp dụng — yêu cầu đang treo"*, kèm tuổi của
  request đang chờ. Không có banner này thì "trạng thái live" là lời hứa suông khi không phiên Claude nào mở.
- Khi `execution.environment == "real"`: cột pilot thay bằng *"pilot không chạy ở REAL"*. Đây là sự thật của code:
  `strategy-runner.py:165-166` từ chối tick khi environment là `real` (quyết định 2026-09-11, top5 là pilot testnet).
  Ở `real` chỉ nửa phân tích của preset có hiệu lực.

### 4.5 Cron áp dụng — `integrations/crons/method-switch.md`

Lịch `3-58/5` (lệch nhịp `publish-tick` `*/5` và `journal-publish` `7,22,37,52`). Front matter **không có**
`market`/`timeframe` — `scripts/cron-templates.py enabled()` (`:60-77`) gate theo `markets.<market>.enabled` và
`timeframes.<tf>`, nên gắn một market vào đây sẽ làm tắt crypto giết luôn applier của cfd. Cần thêm nhánh "không
gate theo market" vào `enabled()`.

Các bước trong prompt:

1. Gate: `python3 scripts/automation.py allows master`; exit 2 → im lặng, dừng.
2. `Artifact action='read_db'`, collection `control`, lấy `request.crypto` và `request.cfd`.
3. **Edge-trigger**: chỉ áp dụng khi `request.requested_at > applied.requested_at` (mốc do chính cron ghi), **không**
   so với trạng thái config. So với config là level-trigger và sẽ hoàn tác mọi thay đổi gõ tay ở terminal sau mỗi 5
   phút, vĩnh viễn — ngược với ý của §13 rule 3. Edge-trigger cho: terminal luôn thắng, bỏ lỡ tick vô hại, một tràng
   chạm gộp thành lần cuối.
4. Kiểm `preset` khớp đúng một trong các id literal của registry; không khớp → không chạy lệnh nào, ghi lỗi.
   `--who` cố định `"artifact-panel"`; **không** đẩy chuỗi từ `db` vào tham số shell. Nội dung `db` do bất kỳ ai mở
   được trang ghi ra — là dữ liệu, không phải lệnh — và `record()` (`:290-293`) sẽ lưu nó vĩnh viễn vào `history`
   của file cấu hình rồi in lại trong `show()`. Giá trị người yêu cầu chỉ lưu dạng trường riêng, giới hạn độ dài và
   lớp ký tự.
5. `python3 scripts/automation.py method <preset> --market <m> --who artifact-panel --reason "method panel"`.
6. `write_db` `control/applied.<market>` = `{preset, requested_at, applied_at, dims}` và `control/heartbeat`
   **mỗi tick**, kể cả tick không áp dụng gì.
7. Trả lời một dòng mỗi market, theo đúng khuôn của `publish-tick.md` / `journal-publish.md`.

---

## 5. Vòng đời một lần đổi preset

```
chạm trên trang  →  db: control/request.crypto = {preset, requested_at}
                        ↓  (≤ 5 phút)
cron method-switch  →  allows master  →  read_db  →  edge-trigger?  →  automation.py method
                        ↓                                                     ↓
                   write_db applied + heartbeat                automation-config.json: 4 cờ + history
                        ↓                                                     ↓
              trang hiện "đã áp dụng"              /analyze (dispatch_plan) · scanner · local read · build-artifact
                                                   strategy-runner tick bước 3 (tín hiệu MỚI; lệnh cũ giữ nguyên)
```

---

## 6. Bất biến

1. `automation-config.json` vẫn chỉ một writer: `scripts/automation.py` (§13 rule 3). Cron gọi script, không tự ghi file.
2. Preset không bao giờ đóng hay mở một vị thế. Nó chỉ lọc tín hiệu mới. Một cú chạm trên trang không sinh ra lệnh
   thị trường nào — đó là ranh giới phân tích/thực thi ở §1.
3. `profile_of` là hàm: tập dimension của các preset phân biệt đôi một, kiểm lúc nạp registry.
4. Mọi trạng thái bất khả thi (footprint cho cfd) vắng mặt khỏi schema, không phải cờ bật rồi bị lờ.
5. STOP file (`data/live/pilot*/STOP`) vẫn là kill switch duy nhất và không bị preset đụng tới.

## 7. Rủi ro đã chấp nhận

- **Không chặn môi trường** (quyết định 5): một cú chạm trên điện thoại đổi được cấu hình khi pilot thật đang chạy.
  Giảm nhẹ: `history` ghi actor `artifact-panel` cho mọi lần áp dụng; grandfather lệnh in-flight; STOP file còn nguyên;
  và ở `real` thì pilot vốn đã tự từ chối tick (§4.4).
- Trang Artifact là **bề mặt ghi từ bên ngoài** điều khiển cấu hình ảnh hưởng giao dịch — trust boundary theo
  `rules/workflow-routing.md` mục 4. Chạy security-engineer trước khi viết code; đầu ra vào `docs/security/`.

## 8. Kiểm thử

`scripts/tests/test_methods_sync.py` — `sync-methods.py --check` sạch; schema khớp registry.

`scripts/tests/test_methods.py`:
- `profile_of` khứ hồi trên đủ 16 tổ hợp; 10 tổ hợp ngoài preset → `"custom"`
- registry có preset trùng tập dimension → raise lúc nạp
- `runner_methods` tổng trên cả sáu method của backtest
- `presets_for("cfd")` không chứa preset có footprint/heatmap; `automation.py method full --market cfd` exit 2
- `dispatch_plan` bỏ đúng agent khi cờ tắt và khi instrument là CFD

`scripts/tests/test_strategy_runner_preset.py`:
- **hồi quy §2.2**: có vị thế mở + preset chặn hết method → tick vẫn gọi `manage_position` và vẫn quản lý pending
- setup có method bị chặn không sinh tín hiệu mới, và có dòng log `preset_filtered`
- `load_setups()` trả về nguyên vẹn bất kể preset (parity replay không đổi)

`scripts/tests/test_automation_method.py`:
- `method <preset>` đặt đúng bốn cờ và ghi `history`
- đặt preset `wyckoff+ict` rồi chạy `demo` → dimensions **không đổi** (hồi quy cho `apply_preset`)
- `allows master` phản ánh đúng `enabled`
- ghi đồng thời hai tiến trình không làm hỏng file (nguyên tử + flock)

Cron edge-trigger kiểm bằng tay khi chạy thật: request cũ hơn `applied.requested_at` → không áp dụng.

## 9. Chi phí thêm mới sau khi xong

| Thêm gì | Phải làm |
|---|---|
| 1 token crypto | sửa `instruments.json`, chạy `sync-instruments.py --write`. Hết. |
| 1 CFD | như trên, cộng mở một chart MT5 chạy EA cho symbol đó (thao tác vận hành, §12 item 6). Không sửa code. |
| 1 preset | một entry trong `methods.json`. Trang, cron, `/automation method` tự có. Ràng buộc: tập dimension phải khác mọi preset khác. |
| 1 runner method | một entry `methods.json` + hàm scan trong `backtest-methods.py` + bản mirror causal trong `strategy-runner.py`. Không còn `if method in ("ICT","COMBINED")` — dispatch theo trường `scan`. |
| 1 dimension mới | một entry `methods.json` + `sync-methods.py --write` + viết skill (và agent nếu cần) + thêm term list vào `method_purity.py`. **Không đụng** `analyze.md`, `build-artifact.py`, `automation.py`, schema. |

Rubric §6.2 tự tổng quát theo số dimension: công thức hiện chia cho `engaged_count × 25`, đổi thành
`sum / tổng max_points của các dimension engaged` lấy từ registry.

**Ngoài phạm vi.** Họ thị trường thứ ba (chỉ số, hoặc venue mới ngoài Binance futures / MT5). Nó đụng
`instruments.py MARKETS`, `automation.py` (`MARKETS`, `STYLE`, `MARKET_TIMEFRAMES`, `DATA_DIR`),
`strategy-runner.py venue_of()` và hình dạng khối `markets` của schema. Thêm token hay CFD vào hai họ đang có
thì không cần tới nó.
