# Audit: code ↔ knowledge (Wyckoff + ICT) — 2026-09-19

Người dùng đặt yêu cầu: *"Tao có thể chấp nhận phương pháp giao dịch hiện tại đang không tốt, nhưng không chấp
nhận việc dùng kiến thức bị sai."* Bản audit này đối chiếu **từng luật trong code** với **sách/deck đã ingest**
trong `knowledge/`, mỗi phát hiện bắt buộc trích dẫn **cả hai phía** (file kiến thức + `path:line` của code).

Phương pháp: 2 agent đọc-only chạy song song (một Wyckoff, một ICT), phiên chính mở lại từng dòng được trích để
xác nhận trước khi sửa. Không tin kết luận nào chỉ có một phía.

Mức độ: **WRONG-KNOWLEDGE** = code nói sai điều sách nói · **UNLABELLED-INVENTION** = số/luật của dự án nhưng
gắn trích dẫn như thể lấy từ sách · **FAITHFUL-SIMPLIFICATION** = giản lược có khai báo · **ABSENT** = sách có,
code không có (và điều đó được nói ra).

---

## 1. Đã sửa trong phiên này

| # | Phát hiện | Mức | Sách | Code | Trạng thái |
|---|---|---|---|---|---|
| 1 | **Upthrust bị gán type bằng thang của Spring.** Sách có **hai bảng**: Bảng 2.1 (WMT p049, Spring) thấp→1/vừa→2/cao→3; Bảng 2.2 (WMT p064, Upthrust) tăng-khi-chạm→1 / **rất cao (UTAD)→2** / mạnh-nhưng-thấp-hơn-type-2→3. `vtype()` chạy thang Spring cho cả short: nến dưới trung bình thành "type 1" và **được vào lệnh ngay tại reclaim**, còn UTAD thật (khối lượng cao nhất) bị dán nhãn type 3. Sách **không có** Upthrust khối lượng thấp. | WRONG-KNOWLEDGE | `knowledge/wyckoff/modern-tools.md:55-72` | `scripts/backtest-methods.py:328`, `scripts/strategy-runner.py:803,854` | **Đã sửa**: `vtype(ratio, side)` tách hai bảng; short dưới `upthrust_min_ratio` bị từ chối. Test `test_bias_methods.py::VolumeTypingFollowsTheBooksTwoTables` |
| 2 | Docstring R7 trích **WMT p049 cho typing Upthrust**; p049 là bảng Spring (Upthrust là p064) | WRONG-KNOWLEDGE (trích dẫn) | `modern-tools.md:61` vs `:72` | `scripts/wyckoff_rules.py:22` | **Đã sửa** |
| 3 | Breakeven "+1R (WMT p272)": sách nói *"consider moving stop to entry once price has moved favorably or consolidated"* và **không in con số R nào**. Trích dẫn làm một tham số dự án trông như có nguồn | UNLABELLED-INVENTION | `modern-tools.md:185` | `backtest-methods.py:296`, `wyckoff_rules.py:32` | **Đã sửa** (ghi rõ là tham số dự án) |
| 4 | **Mép cửa sổ quét bị gọi là "ERL".** Sách: ERL = swing high/low (`core-b.md §2.13`). Code lấy `window_hi`/`window_lo` làm target khi không có pool, dán nhãn `(ERL)`. Vì target quyết định R → sàn 3R → khối lượng lệnh, **planned R đổi theo `SCAN_WINDOW` dù thị trường không đổi** | WRONG-KNOWLEDGE | `knowledge/ict/core-b.md:121-125` | `scripts/ict-scan.py:308,316` | **Đã sửa**: pool → dự phóng −2σ (`models.md §2.1.5`) → **từ chối setup**. Đo thực tế: 0/113 setup từng rơi vào nhánh này |
| 5 | Trang chart in "premium/discount" trần, không nói dealing range lấy từ đâu. Đo trên XAUUSD/BTCUSDT/ETHUSDT: **52% mẫu point-in-time có một biên là mép cửa sổ** (`dr_source = mixed`), 5% cả hai biên | WRONG-KNOWLEDGE (over-claim) | `core-a.md §2.18` | `build-artifact.py:400,975` | **Đã sửa**: `dr_qualifier()` ghi rõ "(một biên là mép cửa sổ)". Test trong `test_build_artifact.py` |

Cả hai thay đổi làm đổi ngữ nghĩa quyết định nên đã ghi vào `docs/architecture/policy.json` → `change_safety.recorded_changes` theo §59.

## 2. Chưa sửa — cần bạn quyết vì đây là thay đổi lớn

| # | Phát hiện | Mức | Sách | Code |
|---|---|---|---|---|
| 6 | **"Trading range" của engine proxy là `min(low)`/`max(high)` trên R nến** — không SC, không AR, không CHoCH, không xu hướng giảm trước đó. Sách: chỉ được vẽ TR **sau** khi 3 CHoBEV tạo CHoCH, biên = đáy SC/ST và đỉnh AR. Hệ quả: proxy bắn "Spring" **giữa xu hướng, không có Phase A/B nào** | WRONG-KNOWLEDGE | `advance.md:280,283,302` (WA p68–72), `:331` (WA p79–80) | `backtest-methods.py:541,548-558`; `strategy-runner.py:837-850` |
| 7 | Engine BOOK (`wyckoff_rules.py`) **làm đúng**: downtrend → SC → 3×CHoBEV → AR → ST → ≥2 swing Phase B → mới tới Spring. Nhưng pilot đang chạy engine **proxy** | — | `advance.md:274-283` | `wyckoff_rules.py:144-209` vs `pilot-top5.json` |
| 8 | **Tick volume của MT5 được dùng như volume thật.** Mọi cổng volume (vol_type, SOS "V ≥ avg", Test "V < Spring V") chạy nguyên trên feed CFD; `tick_volume_credit_multiplier` có khai báo nhưng **không script nào đọc** | WRONG-KNOWLEDGE | `modern-tools.md:234` (WMT p131-132) | `wyckoff_rules.py:238-266`; `backtest-methods.py:560` |
| 9 | **Các test "đối nhãn" gần như vắng mặt** ở đường cơ học. `st_min` có nhưng mặc định TẮT và cài ở mức 50% trong khi §2.11.1 nói **1/3**; Dấu hiệu 2 và 4 không có; `sloped_gate` mặc định TẮT | ABSENT + WRONG-KNOWLEDGE (ngưỡng) | `advance.md:457-484` (WA p150-165) | `wyckoff_rules.py:16,189`; `backtest-methods.py:83` |
| 10 | **Pool ICT chỉ nhận equal highs/lows.** Sách có **hai loại** thanh khoản; một đỉnh/đáy cũ đơn lẻ — loại thứ nhất — không bao giờ thành BSL/SSL, không thành target, không neo dealing range. Đây chính là lý do dealing range hay phải lùi về mép cửa sổ | WRONG-KNOWLEDGE (thu hẹp) | `core-a.md:74-75 §2.7` | `ict-scan.py:129-134` |
| 11 | **`--ict-pd` và `--std-origin` là cờ chết** — khai báo, in ra header báo cáo, ghi vào `pilot-top5.json`, tinh chỉnh trong `ict-flags-1y.py`, **không ai đọc** | UNLABELLED-INVENTION (research integrity) | `core-a.md:207 R13` | `backtest-methods.py:84,1014` |
| 12 | Bias HTF của ICT đọc `last_mss` **không kiểm tra `disp`**: một nến đóng vượt thân nhỏ cũng cấp phép hướng cho mọi lệnh ICT live | UNLABELLED-INVENTION | `core-a.md:131-134 §2.17` | `htf_context.py:209-211` |
| 13 | Luật "FVG phải hoàn tất **trước** MSS" là luật dự án, không có trong deck — và nó **loại đúng FVG kinh điển** (cái nằm *trong* nến displacement). Engine live **không** áp luật này, engine backtest thì có → hai engine lấy khác setup | UNLABELLED-INVENTION + lệch engine | `core-a.md:126 §2.16` | `backtest-methods.py:353-357` vs `ict-scan.py:293-296` |

## 3. Đối chiếu đúng (không cần sửa)

ICT: MSS body-close (`core-a.md §2.17`), entry tại mép gần FVG = IOFED (`§2.23`), OTE .62/.705/.79 đúng mức và đúng chân đo, neo STDEV đúng (`core-b.md §2.12`), **không** killzone nào bị áp lên crypto/CFD và mọi bề mặt đều nói rõ điều đó, **không** object nào của Mentorship-2024 (NDOG/NWOG/ORG/BPR/Turtle Soup) bị dùng cho crypto — đúng scope header. Wyckoff: thang Spring, stop tại cực trị Spring (WMT p271), target biên đối diện (WMT p273 + quy tắc 80%), cổng CHoCH = 3 CHoBEV, luật bỏ kế hoạch theo Volume Profile, SOT 3–4 nhịp. Hai file SKILL của Wyckoff và ICT không mâu thuẫn sách.

## 4. Kết luận

Cái sai nặng nhất đã sửa: **mọi lệnh SHORT của Wyckoff đều bị gán type bằng bảng của Spring** — nghĩa là mọi
backtest short trước hôm nay đo một luật không có trong sách. Cái nặng thứ hai chưa sửa: **engine proxy mà pilot
đang chạy không có khái niệm Phase A/B**, nên "Spring" của nó có thể là một đáy bất kỳ trong xu hướng giảm; engine
đúng sách (`wyckoff_rules.py`) đã tồn tại trong cùng repo nhưng không phải cái đang được chọn.


---

## 5. Hành động sau audit (cùng ngày, theo quyết định của người dùng)

**Gỡ engine Wyckoff proxy.** `WYCKOFF`, `COMBINED`, `PARTIAL` bị xoá khỏi registry và khỏi cả hai engine.
Chúng dùng chung một "trading range" là `min(low)/max(high)` trên N nến — không SC, không AR, không CHoCH —
nên "Spring" của chúng có thể nằm giữa một xu hướng giảm, điều sách cấm (`advance.md:280,331`). Dữ liệu đồng ý:
dưới luật FTMO, `WYCKOFF` **fail 9/9** hàng, còn `WYCKOFF-BOOK` (engine đúng sách, đã có sẵn trong repo) giữ
hàng tốt nhất bảng. Bộ chạy được còn đúng hai: **ICT** và **WYCKOFF-BOOK**. `COMBINED-BOOK` giữ nguyên trạng
thái không chạy được: nó gần như không phát tín hiệu (median n = 0 trên mọi hàng stability).

**Đổi tiêu chí chọn setup sang prop-pass.** `rank-setups.py --rank-by prop-pass --account-rows <file>`:
sống sót qua luật tài khoản → `prop_pass_probability` → `account_failure_probability` → sụt giảm → expectancy.
Tiêu chí cũ (tỉ lệ quý dương) mù tài khoản và đã chọn đúng hai luật CFD **đều phá** thử thách FTMO.

**Hai lỗi phương pháp luận tự phát hiện trong lúc làm, đã sửa:**

1. Khi có `--account`, mô phỏng dừng ở lần vi phạm đầu tiên, nên mẫu chỉ còn "các lệnh trước khi vỡ" (5–16 lệnh
   trên profile crypto). Bootstrap trên đó là lấy mẫu lại một chuỗi đã bị điều kiện hoá bởi chính thất bại.
   Nay: xác suất ước lượng trên **toàn bộ** mẫu với luật tài khoản áp cho từng đường đi; `failed_by` và
   `n_until_account_failure` giữ phán quyết của đường đi thật.
2. `spread` của ước lượng "rộng" ban đầu chỉ đổi seed — tức đo nhiễu Monte-Carlo, ra 3 điểm phần trăm cho mẫu
   14 lệnh, trong khi nhãn ghi "WIDE". Nay là **bootstrap lồng** (lấy mẫu lại chính các lệnh đã quan sát):
   với 14 lệnh khoảng chạy từ **0% đến 100%**, đúng bản chất. Và bộ chọn xếp hạng theo **cận dưới** khi ước
   lượng bị đánh dấu rộng, nên một hàng 14 lệnh đo 66% không còn thắng hàng 51 lệnh đo 60%.

**Tài khoản crypto.** Người dùng nêu: crypto không giao dịch theo luật quỹ nên chỉ áp luật tài khoản riêng,
nhưng cũng có thể áp luật quỹ để đo tính bền vững. Hai profile nghiên cứu được thêm (`environment: research`,
không đường lệnh nào chạm tới được): `crypto-personal-v1` (PERSONAL, 10 000 USDT, chỉ thua khi mất nửa tài
khoản, **không** có mục tiêu nên không "pass" được — đúng bản chất) và `crypto-prop-discipline` (CUSTOM, cùng
bốn con số của FTMO để so sánh được với CFD).

**Selection mới** (`docs/architecture/pilot-top5.json`, `rank_by: prop-pass`):

| Thị trường | Khung | Luật | TF | cfg | n | Pass | Fail | Expectancy |
|---|---|---|---|---|---|---|---|---|
| crypto | scalping | ICT | 15m | B | 64 | **76.3%** | 8.4% | +0.24R |
| cfd | scalping | ICT | 15m | A | 74 | **72.5%** | 24.9% | +0.21R |
| cfd | swing | WYCKOFF-BOOK | 4H | B | 51 | **60.5%** | 27.7% | +0.22R |

Không có ô `day` nào được chọn: không luật nào đủ 60 lệnh sau khi qua được luật tài khoản. Đó là "chưa xứng
đáng được chọn", không phải "bị loại".

---

## 6. Đợt sửa thứ hai — findings 8–11 (cùng ngày, theo yêu cầu "nếu sai lệch với kiến thức thì sửa")

### 6.1 Finding 11 — hai cờ chết: **xoá**, không đấu dây

Kiểm tra lại từng cờ trước khi sửa, và kết luận **ngược với giả định ban đầu**: cả hai luật mà chúng đặt tên
đều là luật thật của deck, và **cả hai đã được thực thi ở chỗ khác** — nên cái sai không phải "thiếu luật" mà
là "một cái công tắc giả vờ mình bật/tắt được một luật bắt buộc".

| Cờ | Luật deck | Thực tế trong code | Xử lý |
|---|---|---|---|
| `--ict-pd` | R13: long ở discount, short ở premium (`core-a.md:207`) | `scripts/ict-scan.py:287` tính `pd_ok`; `backtest-methods.py` `ict_setups_live()` từ chối mọi ứng viên không có `pd_ok`. Cờ không được đọc ở đâu cả | Xoá cờ |
| `--std-origin` | Neo fib 0 = "the previous high which made the highest high" (`models.md §2.1.5`, Model11 p20) | `ict-scan.py:167,173` tính `origin` đúng như deck. `'pivot'` là proxy tiền-2026-09-12, deck **không** cho lựa chọn | Xoá cờ |
| `--ict-disp` | R10/R11: đóng thân vượt cấu trúc **có** displacement = MSS; **không** displacement = liquidity grab, đọc ngược lại | `find_ict()` để `O=None` mặc định → mọi caller quên truyền `O` đều tắt kiểm tra | Bắt buộc: `O` thành tham số **bắt buộc**, cờ bị xoá |

`scripts/ict-flags-1y.py` bị **xoá**: nó chạy 8 tổ hợp của ba cờ này trên 365 ngày cho từng setup ICT rồi ghi
"quyết định" vào `pilot-top5.json`. Không cờ nào đổi được một setup ICT, nên cả năm đó đo nhiễu. Kéo theo:
`rank-setups.FLAG_KEYS = ()`, `setup_version.FLAG_FIELDS = ()`, `trader_constraints.BOOL_TRUE_ONLY` còn
`("htf", "sloped_gate")`, `snapshot.py` bỏ ba khoá, `strategy-runner.setups()` bỏ ba tham số.

### 6.2 Finding 10 — ICT thiếu **loại thanh khoản thứ nhất**

`core-a.md §2.7` liệt kê **hai** loại: *"Old Highs & Lows are previous highs and lows"* (Old High → BSL,
Old Low → SSL) và *"Equal Highs & Lows"*. `ict-scan.py` chỉ dựng loại thứ hai. Hệ quả: một đỉnh/đáy swing đơn
lẻ không bao giờ là BSL/SSL — không bị quét, không làm target, không làm biên dealing range.

Đã thêm loại `"old"`; mỗi pool nay khai báo `type` (`"equal"` | `"old"`), cặp equal được thêm **trước** để
đọc mạnh hơn giữ dòng. Đo lại ngay sau khi sửa: `dr_source` chuyển từ `mixed` (52 % mẫu trước đây) sang
`pools` trên **mọi** mẫu thử (BTCUSDT/ETHUSDT/XAUUSD 15m, BTCUSDT 4H) — đúng nguyên nhân đã dự đoán ở §2.

### 6.3 Finding 9 — đối nhãn: sai **con số**, và vắng **Dấu hiệu 2**

Sách chia biên độ thành **ba** phần (`advance.md` WA p150: *"chia biên độ của cấu trúc thành 3 phần"*).
Code dùng **một nửa** và docstring R3 ghi *"ST above 50% = supply thinned"* — con số sách không hề đưa ra.

- **Dấu hiệu 1** (WA p150–153) nay là `st_sign` ∈ `supports` (1/3 trên) / `neutral` / `contradicts` (1/3 dưới).
- **Dấu hiệu 2** (WA p154–159) nay là `phase_b_tests = {upper, lower}` + `phase_b_sign`, đếm các swing Phase B
  chạm 1/3 trên so với 1/3 dưới.
- Tên `supports`/`contradicts` chứ không phải `upper`/`lower`: `detect_distributions()` chạy engine trên giá
  **đảo dấu**, nên chỉ có cách gọi theo nhãn mới sống sót qua phép soi gương.
- **Cả hai dấu hiệu đều được GHI, không dấu hiệu nào PHỦ QUYẾT mặc định** — và sự đối xứng đó là kết luận sau
  khi tôi đã làm sai một lần. Dấu hiệu 1 từng bật mặc định trong chính đợt sửa này, với lý do WA p150 nói
  thẳng 1/3 dưới là *"dấu hiệu để nhận dạng sớm tái phân phối hoặc phân phối"*. Đã tắt lại trong cùng ngày:
  mục này có tên là *"những thử nghiệm trong các Phase"* — thử nghiệm để **đánh giá một cấu trúc đang hình
  thành** — và khép lại bằng *"trong diễn biến thực tế của thị trường, chúng ta không thể thực sự biết đó là
  tích lũy hay phân phối"* (WA p167). Sách đưa ra một **dấu hiệu**; "nên không vào lệnh" là một suy luận đặt
  lên trên nó. Một suy luận khoác thẩm quyền của sách chính là loại UNLABELLED-INVENTION mà bản audit này lập
  ra để gỡ. Cái **thuộc về sách** là các mốc 1/3 và 2/3 — và đó là thứ đã được sửa (trước đây là một nửa).
  Có nên gác hay không là một **giả thuyết §41 đo được**, không phải một mặc định: `--st-gate` và
  `--phase-b-gate` vẫn còn để đo. **Giá đã đo** khi bật Dấu hiệu 1: BTCUSDT 4H WYCKOFF-BOOK **11 → 9** cấu
  trúc và COMBINED-BOOK **1 → 0**; BTCUSDT 15m (20 000 nến) WYCKOFF-BOOK **6 → 5**.
- `sloped_gate` **giữ nguyên mặc định TẮT**, cùng lý do và cùng một lần tự sửa. Ba luận điểm: (1) sách **dạy**
  bốn biến thể dốc suốt WA p167–181 kèm điểm vào và kết lại *"tất cả đều là biến thể của cấu trúc nằm ngang"*
  (WA p180–181); (2) lời khuyên can **có phạm vi** — bản trích của repo đọc nó thành WA2-42 *"IF you are a
  first-time Wyckoff operator"* (`advance.md:1113`); (3) ngưỡng `slope_max_tr = 0.35` là **tham số dự án**,
  trong khi sách nói ngay trong cùng câu rằng *"không có một quy chuẩn nào về độ dốc"* (WA p170). **Giá đã
  đo**: bật mặc định làm WYCKOFF-BOOK **23 → 5** cấu trúc (−78 %) và COMBINED-BOOK **1 → 0** trên BTCUSDT 15m.

**Kết quả ròng của mục 9:** phát hiện Wyckoff **không đổi** so với trước đợt sửa; cái đổi là (a) ngưỡng đối
nhãn từ một nửa sang đúng ba phần của sách, (b) hai dấu hiệu nay có mặt trên mọi bản ghi và mọi lệnh, (c) ba
cờ để đo giả thuyết "có nên gác" thay vì đoán.

Cả ba cổng được thêm vào **đường live** (`strategy-runner.setups_wyckoff`) đọc cùng `bt.OPTS`. Trước đó chỉ
backtest có cổng: hai engine, một lựa chọn (CLAUDE.md §37).

### 6.4 Finding 8 — tick volume: **khai báo**, không từ chối

Sách nói tick-based data không phải volume thật và nêu real-volume là yêu cầu cứng của phương pháp
(WMT p131–133). Feed MT5 cho CFD đếm **số lần đổi giá**. Không có chỗ nào trong đường cơ học phân biệt điều đó.

Đã thêm `volume_kind` ∈ `"traded"` | `"tick"` vào **mọi** record của `wyckoff_rules`, truyền từ
`instruments.is_tick_volume(symbol)` ở cả hai engine, và mang lên bản ghi lệnh của backtest. Engine **không**
từ chối feed tick — đó là quyết định phương pháp, không phải điều sách nói — nhưng không bề mặt nào còn có thể
in một "loại khối lượng" như thể bảng của sách đã được cho ăn đúng thứ nó đòi. `tick_volume_credit_multiplier`
giữ nguyên: nó **có** người đọc, là `.claude/skills/wyckoff-skill/SKILL.md:59` (đường LLM), không phải script.

### 6.5 Hệ quả phải đo lại

Ngữ nghĩa phát hiện đã đổi ở cả hai engine, nên toàn bộ `data/history/stability/*.json` và
`docs/architecture/pilot-top5.json` được sinh lại. Bảng chọn cũ đo trên engine cũ và không còn hiệu lực.

---

## 7. Phát hiện nặng nhất, tìm ra cuối phiên: **85 % lệnh ICT trong backtest là lệnh không ai vào được**

Không phải lỗi kiến thức — lỗi **giả định khớp lệnh** (CLAUDE.md §37, §38).

`ict_setups_live` tính điểm khớp bằng `fvg_fill(..., mss_i, ...)`, tức **giả định lệnh LIMIT đã nằm sẵn từ
nến MSS**. Không ai làm được điều đó: setup chỉ *nhìn thấy được* ở nến `i` — nến đầu tiên mà nó
`complete` + `pd_ok` + khớp bias — và `i` thường là `mss_i + 1` trở đi.

Đường live **đã làm đúng** từ trước: `strategy-runner.ict_live_setups` từ chối những cái đó
(*"already triggered on an earlier bar ... not a NEW order to place"*). Nghĩa là hai engine đo hai hệ thống
khác nhau, đúng thứ §37 cấm.

**Cách tìm ra.** Sửa bộ kiểm parity `replay()`: nó đưa cho scanner ICT cửa sổ **300 nến** trong khi scanner
live đọc **576** nến trên 15m, và `read_at` từ chối cửa sổ thiếu *theo thiết kế*. Nên mọi lần replay ICT đều
nhận 0 tín hiệu của runner, và phép so sánh "pass" chỉ vì backtest cũng không có gì trong khoảng đó.
**Parity của ICT chưa từng được kiểm tra thật.** Sửa cửa sổ xong, nó fail ngay ở lệnh đầu tiên.

**Ca cụ thể** (BTCUSDT 15m, 2026-09-09): MSS lúc 11:45; setup complete + bias đồng ý lần đầu lúc 12:00; mép
gần FVG bị chạm **ngay trong nến 12:00**. Luật cũ ghi nhận một lệnh 2,06R; runner từ chối, và runner đúng.

**Đã sửa**: backtest nay hỏi đúng hai câu của runner, theo đúng thứ tự — (1) runner có từ chối vì lệnh đã
xuyên qua trước khi thấy được không (`fvg_fill` trên `mss_i+1 .. i`)? (2) khớp ở đâu, tính từ `i+1`, vì lệnh
chưa tồn tại trước khi nến `i` đóng.

**Quy mô** (30 000 nến 15m gần nhất):

| Mã | Luật cũ | Luật đúng | Không vào được |
|---|---|---|---|
| BTCUSDT | 19 | 6 | 68 % |
| ETHUSDT | 17 | 1 | 94 % |
| SOLUSDT | 11 | 0 | **100 %** |
| **Tổng** | **47** | **7** | **85 %** |

**Hệ quả**: mọi con số ICT từng có trong repo này đều vô hiệu. Hai setup ICT đang được chọn
(crypto scalping n=64 pass 76,3 %; cfd scalping n=74 pass 72,5 %) được chọn trên tập đó. WYCKOFF-BOOK **không**
bị ảnh hưởng: nó vào lệnh market tại giá đóng, không dùng limit chờ.

---

## 8. Kiểm chứng lại theo yêu cầu: "kết quả tệ là do hệ thống, do chưa lọc, hay do phương pháp?"

Đo phễu ICT từng cổng trên BTCUSDT và XAUUSD 15m (30 000 nến gần nhất), sau khi đã sửa luật khớp lệnh (§7):

| Cổng | BTCUSDT | XAUUSD | Nguồn của cổng |
|---|---|---|---|
| Ứng viên (có sweep) | 1 119 | 836 | — |
| Rớt: chưa complete (không displacement / không FVG) | 786 | 630 | deck R10–R12; **ngưỡng số là của dự án** |
| Rớt: sai nửa range (R13) | 270 | 167 | deck |
| Complete + đúng nửa, riêng biệt | 23 | 20 | — |
| Rớt: bias không đồng ý | 7 | 7 | dự án (giảm khung) |
| Rớt: limit đã xuyên trước khi thấy được | 9 | 7 | §7 |
| **Khớp thật** | **6** | **4** | — |
| Qua sàn 3R | **0** | **0** | **dự án** (quyết định người dùng, chặt hơn 2R của deck) |

Tức là: sau khi cắt hết cái hư cấu, **mọi lệnh thật đều bị chính sàn 3R của ta từ chối**. Đó không phải phương pháp thua.

Tra tiếp thì ra **nguyên nhân gốc là luật chọn target**, và nó là lỗi kiến thức: `ict-scan.py` lấy **pool chưa quét gần nhất** làm target, dự phóng σ chỉ là dự phòng. Deck nói ngược lại — `models.md §2.1.5`: *"the main focus for identifying targets is using standard deviation projections"*; thanh khoản là *draw* (`core-a.md §2.8`), không phải target; sơ đồ R13 vẽ target ở **biên đối diện của range**. Việc thêm Old Highs & Lows sáng nay (§6.2, đúng cho sweep và dealing range) làm "pool gần nhất" gần như luôn là swing kế tiếp, và R kế hoạch sập.

**Cùng 20 điểm vào** (5 mã × 60 000 nến 15m), hai luật target:

| Luật target | R kế hoạch (median) | Thắng | Ròng | Kỳ vọng | Qua sàn 3R |
|---|---|---|---|---|---|
| Pool gần nhất (trước) | 0,55 | 17/20 | +12,9R | +0,64R | 1 |
| **Dự phóng −2σ (deck)** | **2,91** | 10/20 | **+19,1R** | **+0,95R** | **9** |

Đã sửa trong đúng một seam (`setup_candidate`) mà cả backtest lẫn runner cùng đọc; pool gần nhất giữ lại dưới tên
`objective` để hiển thị. Ghi §59. Bảng xếp hạng chạy lại.

**n = 20 vẫn quá nhỏ để kết luận gì về phương pháp.** Điều duy nhất mục này chốt được là: sự trống rỗng của lần
xếp hạng trước là do luật target của ta, không phải do phương pháp và không phải do sửa khớp lệnh.

---

## 9. Cổng vào lệnh bằng LLM — đo, không tranh luận (đề nghị người dùng, cùng ngày)

Người dùng đề xuất một bước tuỳ chọn: sau khi mọi cổng cơ học đã qua, LLM quyết định vào hay bỏ, để lấp
"khoảng trống phán đoán" giữa sách và người thực hành. Thay vì tranh luận, đo theo hình dạng §49: A = không
cổng, B = có cổng, cùng 20 lệnh ICT vào được, cùng dữ kiện point-in-time (chỉ những gì `read_at` dựng từ
`candles[:i+1]`, không có kết quả), từ vựng đóng ENTER/SKIP, một lời gọi mỗi ca, ba model.

| | n | thắng | ròng | kỳ vọng |
|---|---|---|---|---|
| **A — không cổng** | 20 | 10 | +19,1R | **+0,95R** |

| Model | ENTER | SKIP | không đúng định dạng | bỏ đúng lệnh thua | **bỏ nhầm lệnh thắng** | độ trễ TB |
|---|---|---|---|---|---|---|
| sonnet | **0** | 14 | 6 | 5 | **9** | 15,3 s |
| opus | **0** | 20 | 0 | 10 | **10** | 12,0 s |
| fable | **0** | 14 | 6 | 5 | **9** | 14,2 s |

**Không model nào vào một lệnh nào.** Cổng LLM, đặt ở vai "người gác cuối", không thêm phán đoán — nó thêm
**từ chối toàn bộ**, và trong đó có tất cả lệnh thắng. Ba model không khác nhau về kết cục; Opus tuân định
dạng tốt nhất (0 ca không đọc được). Câu hỏi "chuyển lớp đọc cục bộ sang Opus hay Fable" vì thế **chưa có
căn cứ để trả lời bằng phép đo này** — cả ba đều không phân biệt được lệnh thắng với lệnh thua trên cùng dữ
kiện mà luật cơ học đã thấy.

**Giới hạn của phép đo, nói thẳng**: n = 20; prompt đặt model vào vai "cổng cuối" có thể đẩy về SKIP; model
chỉ nhìn bản tóm tắt bằng chữ của cùng những con số. Không kết luận nào về "phán đoán của người thực hành"
rút ra được từ đây. Kết luận rút ra được: **phán đoán ấy không nằm trong việc cho một LLM đọc lại dữ kiện
của scanner.** Ba bản ghi §42 niêm phong dưới `docs/experiments/`, `decision: PENDING`.

**Bảng xếp hạng sau khi sửa target (−2σ)**: vẫn **một** dòng, CFD swing WYCKOFF-BOOK 4H, n = 5. ICT có kỳ vọng
dương trên 20 lệnh nhưng **quá thưa** để qua ngưỡng chọn theo cửa sổ 1 năm (scalping cần 20 lệnh/năm). Vấn
đề của ICT hôm nay không còn là "sai" — là **hiếm**.
