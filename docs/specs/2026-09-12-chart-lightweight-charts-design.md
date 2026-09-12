# Chart pages: thay lớp vẽ SVG bằng Lightweight Charts (thiết kế, duyệt 2026-09-12)

**Vấn đề.** Chart trong `scripts/build-artifact.py` là SVG tự vẽ. Khi kéo, mỗi sự kiện chuột dựng lại toàn bộ chuỗi SVG
và (ở lane ICT) chạy lại engine ICT trên lát cắt đang nhìn (`drawChart`). Hệ quả: giật, trục giá nhảy khi kéo ngang,
không kéo được trục, không có quán tính, không touch/pinch, và overlay ICT đổi theo vùng zoom nên lệch với
`prelim/<style>.facts.json` của scanner.

**Quyết định.** Dùng thư viện mã nguồn mở của TradingView, Lightweight Charts 5.2.1 (Apache-2.0), làm lớp vẽ. Không
đổi nguồn dữ liệu: nến vẫn từ Binance / MT5 bridge do builder nhúng vào trang. Thư viện không gọi mạng. Nhúng widget
TradingView và CoinGecko MCP bị loại: iframe tradingview.com bị CSP của Artifact chặn và không vẽ được overlay của
mình; CoinGecko không có OHLC intraday (`docs/architecture/data-sources.md` dòng 5 đã loại TradingView làm nguồn).

## 1. Kiến trúc

- `scripts/build-artifact.py` vẫn là renderer duy nhất (SYSTEM-DESIGN §15). Nó nhúng hai file JS lúc build:
  - `scripts/vendor/lightweight-charts.standalone.production.js` — bản 5.2.1 pin cứng, kèm `scripts/vendor/LICENSE-lightweight-charts.txt`
    (Apache-2.0) và ghi chú nguồn/phiên bản trong `scripts/vendor/README.md`. Inline vào HTML để trang không phụ thuộc CDN.
  - `scripts/chart.js` — toàn bộ JS chart (engine ICT, thống kê KL, overlay, tương tác, replay, thước) tách khỏi
    chuỗi Python để đọc và test được. Builder thay `__DATA__` / `__PARAMS__` như hiện nay.
- Ghi công theo license (quyết định 2026-09-12, sau khi §1–5 chạy): logo trên canvas TẮT (`layout.attributionLogo:false`);
  thay vào đó dòng NOTICE của thư viện (tên, bản quyền TradingView, Inc., link tradingview.com, Apache-2.0) in ở footer
  mọi trang nhúng thư viện. Apache-2.0 §4(d) yêu cầu kèm NOTICE khi phân phối; tài liệu thư viện yêu cầu ghi công + link
  trên một trang công khai của ứng dụng — footer đáp ứng cả hai. Bản NOTICE gốc: `scripts/vendor/NOTICE-lightweight-charts.txt`.
- Kích thước: thư viện ~198 KB; trang vẫn xa giới hạn 16 MB của Artifact.

## 2. Luồng dữ liệu

- Hàng nến `[label, o, h, l, c, v, isoUTC]` không đổi. `chart.js` chuyển `isoUTC` → unix giây cho thư viện.
- Mỗi chart: series nến (pane 0) + series histogram khối lượng (pane 1). Lane ICT không vẽ khối lượng nhưng giữ
  pane 1 với chiều cao cố định (để trống, có chú thích như hiện nay) để trang không nhảy khi đổi phương pháp.
- **Thay đổi hành vi có chủ ý:** `ictAnalyze` và `volStats` chạy MỘT lần trên toàn bộ cửa sổ tier, không chạy lại theo
  vùng zoom. Overlay cố định theo cửa sổ tier và khớp với số liệu trên trang. Ngoại lệ duy nhất là chế độ replay (§5).

## 3. Lớp overlay

Một pane primitive `Annotations` mỗi chart nhận danh sách hình trong toạ độ (thời gian, giá) và vẽ lên canvas qua
`timeScale().timeToCoordinate` / `series.priceToCoordinate`; thư viện gọi vẽ lại khi pan/zoom/resize.

| Loại hình | Dùng cho |
|---|---|
| `rect` {t1,t2,p1,p2, fill, stroke, label} | FVG (kèm nét CE 0.5), OB (open + 0.5 MT), killzone, pha A–E, TR, cửa sổ vào lệnh, hộp risk/reward |
| `hseg` {t1,t2,price, stroke, dash, label} | CISD, EQ, OTE .62/.705/.79, −2σ/−2.5σ/−4σ, mức PDH/PDL/PWH/PWL/ASIA/LDN, BSL/SSL |
| `label` {t,price, text, anchor} | nhãn cạnh hình, `now xx%` |
| `mark` {t,price, glyph ×/✓/●} | quét, đóng qua, sự kiện Wyckoff |

- Mức ngang có nhãn (TR AR/SC, EQ, σ, anchors, kế hoạch lệnh, `invalidation.level`) gắn nhãn lên trục giá qua
  `priceAxisViews` của primitive (kiểu tag giá TradingView); các nhãn trùng giá được gộp thành một tag. Sự kiện Wyckoff
  là hình `flag` của primitive với thuật toán tránh chồng nhãn (giữ nguyên từ bản SVG) — không dùng `createSeriesMarkers`
  vì marker của thư viện không tránh chồng chữ.
- Màu đọc từ CSS variables (`scripts/artifact_theme.py`) bằng `getComputedStyle` lúc tạo chart; đổi theme qua
  `MutationObserver` trên `data-theme` và `matchMedia('(prefers-color-scheme: dark)')` → `applyOptions` + vẽ lại.
- Quy tắc method purity không đổi: lane Wyckoff = nến + KL + TR/pha/sự kiện; lane ICT = engine chỉ giá.

## 4. Tương tác

- Mặc định thư viện: kéo có quán tính, lăn chuột zoom quanh con trỏ, pinch, kéo trục giá/trục thời gian, crosshair magnet.
- Giữ: nút −/+/⟲ (⟲ = `fitContent`), phím 1–4 đổi phương pháp, trạng thái zoom/pan mỗi chart (visible logical range)
  giữ qua lần đổi phương pháp, tooltip `.tip` với O/H/L/C, %, KL so TB, % dealing range (nuôi bằng `subscribeCrosshairMove`).
- Thêm: phím `End` về nến cuối (`scrollToRealTime`).

## 5. Phần mở rộng (cùng đợt, sau khi §1–4 chạy)

1. **Kế hoạch lệnh lên chart.** Nguồn: `trades/index.jsonl` (bản ghi `status` ∈ {PLANNED, OPEN}, `instrument` trùng
   symbol) → đường entry / stop / từng target, hộp risk (entry↔stop) và reward (entry↔target1) tô màu `--down-soft` /
   `--up-soft`, nhãn `R:R x.x` (= `planned_rr` nếu có, không thì tính). `rehearsal_mode: true` ghi rõ "diễn tập" trên nhãn.
   `invalidation.level` của narrative vẽ nét đứt với nhãn `vô hiệu · <owner>`. Chỉ đọc, không ghi trades/.
2. **Thước R:R.** Phím `R` hoặc nút bật chế độ thước: click 1 = entry, kéo/click 2 = stop; vẽ hộp risk và thang
   1R/2R/3R ở phía đối diện, nhãn khoảng cách (giá, %, R). `Esc` xoá. Không lưu, không ghi gì (tách phân tích/thực thi).
3. **Bar replay.** Phím `P` hoặc nút bật replay: click chọn nến bắt đầu; `←`/`→` lùi/tiến một nến, `Space` chạy tự
   động, `Esc` thoát. Trong replay engine ICT chạy trên tiền tố `rows[0..cursor]` (không rò dữ liệu tương lai);
   overlay Wyckoff từ narrative có `time > cursor` bị ẩn; tooltip và số `now xx%` theo cursor. Thoát replay = về §2.
4. **Trang nhật ký.** `journal_render.py` `r_curve` chuyển sang area series của thư viện theo thời điểm đóng lệnh, marker
   mỗi lệnh (xanh/đỏ theo R) và tooltip (id, setup, R, R tích lũy); dùng cùng file vendor. Không thêm chart nến vào nhật ký (không có nến lưu theo lệnh).

## 6. Kiểm chứng

- `scripts/tests/test_build_artifact.py` (unittest, như các test hiện có): build một style từ `--snapshot-dir` cố định
  trong test → HTML có thư viện inline và `chart.js`, không còn `<svg class="chart"`, `__DATA__` là JSON hợp lệ,
  `__ROWS__` đã thay hết. Thêm test thuần JS chạy bằng `node` cho `ictAnalyze` (kết quả trên cửa sổ đầy đủ không đổi
  khi đổi vùng nhìn) nếu `node` có trên máy; nếu không, ghi rõ trong kết quả.
- Runtime bằng Playwright headless (Python `playwright` nếu có, hoặc MCP playwright): mở trang build ra, không lỗi
  console, mỗi `.chart-block` có `canvas`, kéo và lăn chuột đổi `getVisibleLogicalRange`, đổi lane giữ vùng nhìn,
  `R`/`P` bật đúng chế độ.
- `check-model-prose.py`, `check-narrative.py`, `test_method_purity.py` chạy như cũ.
- Publish một style lên Artifact để người dùng kéo thử thật.

## Trạng thái
Triển khai 2026-09-12 cùng phiên: §1–§5 xong; kiểm chứng §6 bằng unittest (10 test) và Playwright headless
(scratchpad `smoke.py`: 0 lỗi console, 9 chart × 11 canvas, zoom/pan/lane-switch/thước/replay/theme đều đạt).

## Ngoài phạm vi
Chart nến trong nhật ký; crosshair đồng bộ giữa ba chart; lưu thước/kế hoạch do người dùng vẽ; mọi thay đổi engine ICT
hay quy tắc phân tích.
