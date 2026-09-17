# Rà soát lại 30 PDF TTrades/ICT ↔ knowledge/04–06 ↔ ict-skill ↔ code — 2026-09-12

> **Knowledge-path note (added 2026-09-17).** The `knowledge/` citations below use the FLAT numbered
> layout (`knowledge/07-wyckoff-advance.md`, or the `kNN` short codes) that was retired on 2026-09-17 in
> favour of one folder per methodology. They are left exactly as written: this document is a dated record,
> and re-pointing its citations would change what it says it checked. `knowledge/INDEX.md` carries the
> old→new map.

Bổ sung cho `2026-09-11-ict-entry-checklist-audit.md` (bản đó đối chiếu code với knowledge nhưng **không mở PDF**).
Bản này mở toàn bộ 30 PDF trong `docs/TTrades PDFs/` (391 trang vật lý), đọc lớp text (`pdftotext -layout`) và xem
từng trang hình (PNG 70 dpi; 12 trang được vẽ lại 110–200 dpi để quyết định các câu hỏi về hình học nến).

Phương pháp: 4 agent đọc hình theo nhóm deck (báo cáo chi tiết trong thư mục `2026-09-12-ict-pdf-recheck/`), phiên
chính đọc lớp text của cả 30 deck và tự xem lại 7 trang có kết luận mức "high" (ảnh 110 dpi lưu cùng thư mục).
Không sửa file nào ngoài thư mục `docs/audits/`.

| Nhóm | Deck | Trang | Báo cáo |
|---|---|---|---|
| knowledge/04 | 1, 2, 3, 4, 6, 8, 9, 11, 12, 13, 14 | 100/100 | `2026-09-12-ict-pdf-recheck/k04-vs-decks-1-14.md` |
| knowledge/05 | 16–24, IRL-ERL, MSS_vs_CISD, Relative_Strength, Silver_Bullet_AM | 126/126 (2 lượt) | `2026-09-12-ict-pdf-recheck/k05-vs-decks-16-24-run2.md` (lượt 1 bị ghi đè; các phát hiện của lượt 1 được ghi lại ở §2 dưới đây) |
| knowledge/06 | TTrades Model11 | 118/118 | `2026-09-12-ict-pdf-recheck/k06-vs-model11.md` |
| knowledge/06 | Sons, Sons_HTF, TTRS, Timeframe Alignment, Unicorn | 47/47 | `2026-09-12-ict-pdf-recheck/k06-vs-sons-ttrs-tfa-unicorn.md` |

---

## 1. Kết luận về mức phủ của knowledge

1. **Không có khái niệm, luật, con số hay cửa sổ thời gian nào trong 30 PDF bị bỏ sót** khỏi `knowledge/04`, `05`, `06`.
   Mọi câu text trong PDF đều tìm thấy nguyên văn ở trang được trích; mọi trang hình đều có mô tả tương ứng.
   Model11 (deck dài và nhiều luật nhất): 118/118 trang khớp, không MISSING, không UNSOURCED.
2. **"BOS", "CHoCH/Change of Character", "Break of Structure", "BMS" không xuất hiện trong bất kỳ PDF nào** (grep lớp text
   30 deck: 0 kết quả). Quyết định 7 trong `knowledge/10 §7` (từ chối hai token này ở chiều ICT cho tới khi có nguồn) vẫn đúng.
3. Các mơ hồ mà knowledge đã tự ghi ở mục §6 mỗi file (ranh giới phiên Á/London không định nghĩa, hai bộ killzone, EST/DST,
   OTE không in "0.62–0.79", PO3 Entries chỉ có mũi tên, Sons/TTRS/Unicorn không có stop/target…) đều được xác nhận là mơ hồ
   thật trong PDF, không phải lỗi trích xuất.
4. **Sai lệch có ảnh hưởng tới luật/mức giá: 6 chỗ, tất cả về hình học vẽ box/stop trên chart** (mục 2). Đây đúng là phần
   bạn nhấn mạnh — "đánh dấu chính xác trên chart".

## 2. Sai lệch cần sửa trong knowledge (đã tự xem lại ảnh 110 dpi, xác nhận)

| # | File / mục | Knowledge nói | PDF vẽ | Ảnh hưởng |
|---|---|---|---|---|
| S1 | `k05 §2.7` bước 5, `§6.3`, YAML `breaker_block` | Breaker box = **thân** các nến up-close tạo High | `19. Breaker p8, p14, p17–p19`; `Unicorn p5`: box = **toàn bộ biên độ kể cả râu** của nến up-close (bull) / down-close (bear) tại swing; râu nến kề bên bị loại. `TTRS p8, p17`: box còn phủ **cả nến tăng lẫn nến giảm** quanh swing trung gian, từ đỉnh swing xuống đáy đã quét | Box breaker/Unicorn vẽ hẹp hơn deck → entry ở overlap breaker∩FVG và stop "box low" lệch mức |
| S2 | `k05 §2.5` (a), R10, R21, YAML `order_block.stops` | Stop OB = dưới **low nến OB** (không nói thân hay râu) | `17. Orderblocks p8`: vùng đỏ cột "OB" kết thúc đúng tại **đáy thân** (close) nến OB; râu nến còn thò xuống dưới. Cột "Swing Low" kết thúc tại râu nến raid | Stop chặt hơn deck vẽ nếu dùng râu; cần ghi rõ "body low" |
| S3 | `k05 §2.7` stop (a), R11, R22 | Stop breaker = dưới **đáy box** | `19. Breaker p18`: vùng đỏ cột 1 kết thúc **dưới đáy box**, tại low của nến displacement (Higher High); ranh giới xanh/đỏ (mức vào) = **đỉnh box** ở cả hai cột | Stop và mức entry reference chưa được ghi đúng |
| S4 | `k05 §2.9`, YAML `mitigation_block` | Mitigation box = thân nến up-close | `20. Mitigation p3–p4`: box = râu-tới-râu của nến up-close; `p8`: cạnh dưới ~thân — deck **không nhất quán** | Ghi thành tham số dự án, nêu cả hai |
| S5 | `k06 §2.8` "Bias", `§3.6` rule 1, YAML `timeframe_alignment.sequence_steps[0]` | Nến đen quét đỉnh nến xanh rồi đóng thấp (candle-2 giảm) | `TFA p3` panel Bias: **nến xanh** mang râu trên dài (chính nó là candle 2 bị từ chối), nến đen đỉnh **thấp hơn** đỉnh xanh, thân đầy, đóng dưới low nến xanh (= candle 3 expansion), nến xám = candle 4 kỳ vọng | Bias được kết luận sớm 1 nến so với deck |
| S6 | `k06 §2.9`, `§3.4` rules 4–6, YAML `ttrs.entry_trigger` | 3 mốc vào lệnh tuần tự: OB line → FVG → breaker | `TTRS p15–p17`: **một** nhịp hồi duy nhất xuyên FVG (4), qua đường CISD (3), vào box breaker (5) rồi bung — 3 vùng lồng nhau, một lần retest | Nên ghi cả hai cách đọc; không được đếm thành 3 confluence (khớp `k10 §4.3` "LPS ≡ retest pile") |

Sai lệch mức thấp (không đổi luật) — chi tiết trong 4 báo cáo:
`13. Inversion p4` không có SIBI (SIBI xuất hiện cùng nến đóng ở p5); nhãn M/T/W/TH/F chỉ có ở 2/3 trang trích;
`24. AMD_STD p4` không có OHLC/OLHC (chỉ có ở `22. PO3 p3`); các đường "orange" ở `23. STD p5, p9` thực ra xám/đen;
`18. MSS p4–p5` có thêm marker sweep tiếp diễn; `Silver_Bullet p3` "9:30 = NY open" là suy diễn; `MSS_vs_CISD p5` CISD và MSS
bị đóng xuyên bởi **cùng một nến** (thứ tự "CISD trước MSS" là thứ tự mức giá, không phải thời gian); `Sons p5` entry là FVG
(bỏ phương án "OB body" ở `k06 §6.7`), nhịp hồi xuyên hết FVG và vượt xuống dưới; `TTRS p7` râu quét chạm chính "Important
Level"; `TFA p3` panel Entry: có nến **đóng xuyên** OB rồi râu retest; `Model11 p118` nhãn giờ "8:00" không phải "8:30".

Loại bỏ: lượt 2 của nhóm k05 báo "CISD p3 vs p4 không phân biệt được chuỗi nến" ở mức high — xem lại ở 110 dpi: p4 vẽ
rõ chuỗi 2 nến xanh / 3 nến đen với đường CISD tại open nến **đầu** chuỗi. `k05 §2.3` và `§6.1` đúng.

---

## 3. Checklist 7 bước của bạn — đối chiếu 4 lớp

Lớp: **K** = knowledge/04–06 · **S** = `.claude/skills/ict-skill/SKILL.md` · **C** = code (`scripts/ict-scan.py` quét;
`scripts/backtest-methods.py` `find_ict`/`ict_target` = luật ICT mà `scripts/strategy-runner.py` đang chạy pilot;
`scripts/demo-pilot.py` legacy) · **V** = lớp vẽ chart `scripts/build-artifact.py` `ictAnalyze` (dòng 498–536, legend dòng 653).

| Bước | K | S | C | V |
|---|---|---|---|---|
| 1. Daily/H4 bias + Premium/Discount | Đủ: PDH/PDL, PCH/PCL, "failure to displace", Next Day Model (`k04 §2.11–2.15`); candle 2/3 closure, weekly & daily profile (`k06 §2.2, §2.5`); P/D (`k04 §2.18–2.19`) | Bước 1 chỉ hỏi MSS gần nhất theo body close; **không** có PDH/PDL, candle-2 closure, weekly/daily profile. HTF narrative giao cho Wyckoff (`k10 §4.2`) — theo thiết kế | Không script nào tính PDH/PDL/PWH/PWL/PCH/PCL. Lọc HTF là Wyckoff: `htf_allows` = vị trí close trong R-bar range (backtest-methods:221). P/D: `demo-pilot.py:212` có gate; **luật ICT đang chạy pilot (`find_ict`) không có gate P/D**. Dealing range = min/max cửa sổ N nến (`ict-scan.py:72`), không phải cặp BSL↔SSL như `k04 §2.18` | Vẽ EQ + premium/discount **từ range cửa sổ** (dòng 503); không vẽ PDH/PDL |
| 2. Draw on Liquidity (BSL/SSL) | Đủ: swing 1 nến mỗi bên, old H/L, equal H/L, PDH/PDL/PWH/PWL/PMH/PML, session H/L (`k04 §2.5–2.9`); IRL↔ERL luân phiên (`k05 §2.13`) | Có, nêu IRL/ERL | Pool chỉ = **cặp equal highs/lows** (`ict-scan.py:104`) hoặc **pivot 3 nến gần nhất** (`find_ict`); swing 3 nến/bên (deck: 1). Không có old high/low đơn lẻ, PDH/PDL, session H/L. Target: pool đối diện gần nhất / biên cửa sổ / std (`ict_target`) | Vẽ BSL/SSL (cặp equal) + ERL biên cửa sổ; × khi đã quét. Không PDH/PDL/PWH/PWL |
| 3. Đánh dấu OB / FVG / Asian Range | OB = **đường open** nến opposing cuối + mean threshold 0.5 thân (`k05 §2.5`); FVG râu-tới-râu, CE 0.5 (`k04 §2.21, §2.26`); "Asian Session High/Low" có (`k04 §2.9`) nhưng **ranh giới phiên không định nghĩa** (`k04 §6.9`) | OB (open + mean threshold), FVG (edges + CE), Breaker, Mitigation có tên; **Asian range không nhắc** | FVG: đúng deck (`ict-scan.py:84`, `find_ict`). **OB: scanner/pilot không có.** CE: không. Asian range: không có ở đâu (`session-model.md` đặt `asia` 00–06 Asia/Tokyo chỉ để journal) | FVG vẽ đúng. **OB vẽ sai hình học**: zone từ low nến tới đỉnh thân (dòng 526), deck là đường open + mean threshold; thêm S1–S4 ở trên nếu vẽ breaker/mitigation. Không vẽ CE, không vẽ Asian/London H/L |
| 4. Đúng Kill Zone chưa? | Đủ 2 bộ (forex/indices) + 3 Silver Bullet, EST (`k04 §2.1–2.2`); Silver Bullet AM 9:00 hourly (`k05 §2.15`); TTRS p3 lặp lại | Dùng `session-model.md` (exchange-local, DST) — đúng hướng | **Không script nào lọc phiên khi vào lệnh** (`find_ict` "Timing = none"; `demo-pilot` không gate). `local-eval-brief.py:30` và `build-artifact.py:531` vẫn hardcode 06–09Z/11–14Z — `session-model.md:21` đã ghi là sai | Vẽ LDN 06–09Z, NY AM 11–14Z cố định (dòng 531) — sai với session-model (london 08–11 Europe/London; ny_am 08:30–11:00 New York) |
| 5. Có Liquidity Sweep chưa? | Đủ: liquidity grab = râu xuyên, thân không đóng qua (`k04 §2.14, §2.17`) | Có | **Có**, đúng deck: `ict-scan.py:98` (râu qua, close trong), `find_ict` (low xuyên pivot low). Chỉ trên pool đã nêu ở bước 2 | Có (×) |
| 6. MSS / CHoCH + Displacement | MSS = displacement đóng thân qua swing, ưu tiên stop raid trước (`k04 §2.17`, `k05 §2.2`); CISD (`k05 §2.3`, `k06 §2.3`) sớm hơn MSS. **CHoCH không có trong nguồn ICT** → là Wyckoff CHoCH (`k07 §2.6`) | MSS có; **CISD không có trong procedure**; CHoCH/BOS bị từ chối đúng | MSS by close: có (`ict-scan.py:122`, `find_ict`). **Displacement: không có phép thử** (body ratio / FVG bắt buộc) → doji đóng qua pivot 1 tick vẫn là "MSS". **CISD: 0 dòng code**. Stop-raid-trước: bắt buộc (mạnh hơn deck "preferred") | Marker MSS↑/↓ có; không vẽ đường CISD/opposing candle |
| 7. Hồi về PD Array (OTE) → Entry + SL + Target | OTE 0.62–0.79, 0.705, neo swing, lồng swing nhỏ (`k04 §2.20`); 3 mô hình vào FVG (IOFED/CE/Fill) + 3 mô hình stop (`k04 §2.23–2.24`); OB/breaker entry + stop (`k05 §3.3, §3.5`); STD −2/−2.5/−4(−4.5) neo manipulation leg (`k05 §2.12`, `k06 §2.1.5`); 2R tối thiểu, trail (`k06 §3.1` 23–24) | OTE chỉ ở frontmatter, **không ở Procedure**; stop: nêu 4 lựa chọn, yêu cầu 1 chủ sở hữu | Entry: **chỉ IOFED** — LIMIT tại mép gần FVG (`find_ict`, strategy-runner) hoặc **market tại close cuối** (`demo-pilot.py:254`). Không OTE, CE, OB, breaker. Stop: **chỉ** cực trị sweep. Target: `ict_target` có std2/std25/std4 (đúng hướng chiếu) nhưng mốc 0 = **pivot high 3 nến gần nhất trước sweep**, deck: "previous high which made the highest high" (`Model11 p20`); `irl`/`erl_next` có. MIN_RR 1.5 (`demo-pilot.py:83`) vs deck 2R | Không vẽ fib OTE, không vẽ mức −2/−2.5/−4, không vẽ CE; entry/stop/target không vẽ |

**Tóm tắt theo lớp**
- Knowledge: đủ; 6 chỗ hình học cần sửa (S1–S6).
- ict-skill: thiếu 4 mục của checklist ngay trong Procedure — bias theo PDH/PDL + candle-2 closure (hoặc nêu rõ Wyckoff
  giữ bước này), CISD, OTE/3 mô hình vào FVG, STD targets; không nhắc Asian/London H/L.
- Code quét/pilot: có 2/7 bước theo đúng deck (sweep, MSS by close). Không có bias ICT, không OB/OTE/CISD/displacement,
  không lọc phiên, range/pool là tham số cửa sổ.
- Vẽ chart: vẽ đúng FVG, sweep, MSS; **sai** OB geometry và giờ killzone; **thiếu** PDH/PDL/PWH/PWL, Asian/London H/L,
  đường CISD, OTE fib, STD projections, CE, mean threshold — tức là phần lớn những gì cần "đánh dấu chính xác" để phân tích
  đa khung chưa có trên chart.

---

## 4. Thứ tự sửa đề xuất (chưa làm gì — chờ quyết định)

1. **knowledge/05, 06 — S1…S6** (6 chỗ, mỗi chỗ 1–3 dòng + YAML). Nhỏ, không phụ thuộc gì, và mọi lớp dưới trích dẫn từ đây.
2. **ict-skill Procedure** viết lại theo đúng 7 bước của bạn, mỗi bước cite `k04–06` + `session-model.md`; ghi rõ bước 1
   phần HTF narrative là của Wyckoff (`k10 §4.2`) còn PDH/PDL/candle-2 closure là của ICT; thêm CISD là trigger sớm, MSS là
   trigger muộn; thêm OTE + 3 mô hình FVG + 3 mô hình stop + STD target; nêu Asian/London H/L là mức thanh khoản với ranh
   giới phiên lấy từ `session-model.md` (tham số dự án, nguồn không định nghĩa).
3. **Lớp vẽ `build-artifact.py`**: OB = đường open + mean threshold; killzone từ `session-model.md` theo ngày; thêm
   PDH/PDL/PWH/PWL, Asian/London H/L, đường CISD, fib OTE (0.62/0.705/0.79), STD −2/−2.5/−4, CE. Đây là điều kiện để
   "phân tích đa khung, đa góc" bằng mắt có cơ sở.
4. **Scanner/pilot**: dealing range = cặp BSL↔SSL gần nhất; phép thử displacement trước khi in "MSS"; gate P/D trong
   `find_ict`; mốc 0 của STD = pivot cao nhất của nhịp (không phải pivot gần nhất); 2R; gate phiên theo `session-model.md`.
   Mỗi thay đổi luật cần backtest lại (`docs/backtests/2026-09-11-stability-by-timeframe.md` là mốc so sánh).
5. **Asian range**: quyết định ranh giới phiên Á cho crypto và CFD (nguồn không cho; `k04` adaptation notes nêu 2 lựa chọn).
6. **CHoCH**: giữ nguyên quyết định 7; nếu bạn muốn CHoCH là khái niệm ICT thì cần cung cấp tài liệu nguồn định nghĩa nó.

## 5. Giới hạn của bản rà soát này

- Hình được xem ở 70 dpi; 12 trang có tranh cãi được xem lại 110–200 dpi. Màu sắc đường (cam/xám) ở vài trang không chắc.
- Lượt 1 của nhóm k05 (báo cáo đầy đủ hơn, có S1–S4) bị lượt 2 ghi đè trong scratchpad; nội dung S1–S4 đã được phiên chính
  xem lại trực tiếp trên ảnh 110 dpi (`2026-09-12-ict-pdf-recheck/brk8-08.png`, `brk18-18.png`, `ob8-8.png`, `tfa3-3.png`,
  `ttrs17-17.png`, `cisd-3.png`, `cisd-4.png`).
- Code chỉ đọc tĩnh, không chạy backtest hay scanner.

---

## 6. Đã sửa (2026-09-12, cùng ngày)

| Bước | Việc đã làm | Bằng chứng |
|---|---|---|
| 1 | S1–S6 và các sai lệch mức thấp trong `knowledge/04`, `05`, `06`; câu chữ stop ở `knowledge/09 §4.4`, `knowledge/10 §4.4` | `git diff knowledge/` |
| 2 | `ict-skill` Procedure viết lại thành 7 bước đúng checklist (bias PDH/PDL + candle-2 closure, DOL kể cả phiên Á/London, OB/FVG/breaker với hình học đã xác minh, killzone theo session-model, sweep, CISD→MSS + displacement, OTE/entry/stop/STD + 2R) | `.claude/skills/ict-skill/SKILL.md` |
| 2 | Tham số ICT gom về `analysis-params.json → project_defined.ict` (pivot, dung sai, FVG tối thiểu, displacement, dealing range, gốc STD, 2R) | `docs/architecture/analysis-params.json` |
| 3 | Lớp vẽ `build-artifact.py`: dealing range = cặp BSL↔SSL chưa quét gần nhất (ghi rõ khi phải dùng biên cửa sổ); OB = đường open + 0.5 mean threshold; CISD; MSS phân biệt có/không displacement; CE trên FVG; old high/low; PDH/PDL/PWH/PWL/PMH/PML; ASIA/LDN H-L; OTE .62/.705/.79; −2σ/−2.5σ/−4σ; killzone LDN/NY AM/NY PM theo `session-model.md` (đổi giờ theo ngày, trọng số theo thị trường, không vẽ cuối tuần); chú giải và glossary cập nhật | `node --check` toàn bộ script; engine chạy trên nến thật cho 6 cấu hình; 3 trang build OK (`build-artifact.py daytrade|gold|1h`) |
| 4 | `ict-scan.py`: đọc tham số từ config; dealing range theo pool; MSS có cờ displacement + CISD + gốc/cực trị manipulation; PDH/PDL; setup ứng viên đòi displacement, in 3 mô hình entry, 3 mức stop (chủ sở hữu = cực trị cú quét), STD −2/−2.5/−4, cờ P/D và 2R | chạy 4 style trên dữ liệu live, 28 setup hoàn chỉnh trên 2000 nến 1H lịch sử |
| 4 | `backtest-methods.py` + `strategy-runner.py`: cờ `ict_disp`, `ict_pd`, `std_origin` (mặc định tắt); `demo-pilot.py` MIN_RR 1.5 → 2.0; `local-eval-brief.py` dòng killzone theo session-model | `docs/backtests/2026-09-12-ict-deck-faithful.md` |

Chưa làm: bật cờ nào cho pilot (quyết định người dùng, xem backtest); ranh giới phiên Á cho scanner ngoài lớp vẽ (lớp vẽ dùng `session-model.md`); CHoCH giữ nguyên quyết định 7.

## 7. Hai quyết định còn lại (2026-09-12, người dùng giao cho hệ thống quyết theo dữ liệu)

- **Ranh giới phiên Á** → `20:00–00:00 America/New_York` (đúng cửa sổ "Asia" của deck `1. Killzones p3`). Đo bằng `scripts/asia-session-eval.py` trên 365 ngày 15m BTC/ETH/SOL + 70 ngày XAUUSD, 5 ứng viên; cửa sổ này có range phiên hẹp nhất (36% range ngày), tỉ lệ đảo chiều sau khi quét cao nhất (48%), gộp điểm 0.319 so với 0.204 của cửa sổ cũ 00–06 Asia/Tokyo (thực chất là buổi chiều New York). XAUUSD riêng lẻ hơi nghiêng về cửa sổ cũ (0.276 vs 0.268) nhưng chỉ 49 phiên. Áp dụng: `session-model.md` §2, `build-artifact.py`, `journal.py` (`session_of` nay đổi múi giờ theo ngày), `ict-skill`. Bảng: `docs/backtests/2026-09-12-asia-session.md`.
- **Cờ ICT cho pilot** → xem `docs/backtests/2026-09-12-ict-flags-1y.md` (`scripts/ict-flags-1y.py --apply`, kết quả ghi vào `pilot-top5.json`, `rank-setups.py` giữ lại các khoá này khi ghi lại file).
