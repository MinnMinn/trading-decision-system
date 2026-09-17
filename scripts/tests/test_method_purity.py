import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import method_purity as mp
import importlib.util
_s=importlib.util.spec_from_file_location('cn', os.path.join(os.path.dirname(__file__), '..', 'check-narrative.py')); cn=importlib.util.module_from_spec(_s)
try:
    _s.loader.exec_module(cn)
except SystemExit:
    pass


class PurityTests(unittest.TestCase):
    def test_wyckoff_block_rejects_ict_terms(self):
        txt = "Sau SC, giá tạo AR rồi quét thanh khoản SSL và để lại FVG tăng."
        terms = [p for p, _ in mp.violations(txt, "wyckoff")]
        self.assertTrue(any("thanh khoản" in p for p in terms))
        self.assertTrue(any("SSL" in p for p in terms))
        self.assertTrue(any("FVG" in p for p in terms))

    def test_wyckoff_block_pure(self):
        txt = ("Cao trào bán (SC) 76,676 trên khối lượng 7.88x, Automatic Rally (AR) 77,425; Phase B đang xây nguyên nhân, "
               "Nỗ lực–Kết quả hài hoà.<span class=\"cite\">[knowledge/wyckoff/advance.md §2.7; FVG cited only in source name]</span>")
        self.assertEqual(mp.violations(txt, "wyckoff"), [])

    def test_ict_block_rejects_wyckoff_and_volume(self):
        txt = "MSS tăng đóng vượt swing 77,083 với khối lượng 0.2x; đây là SOS trong pha D."
        terms = [p for p, _ in mp.violations(txt, "ict")]
        self.assertTrue(any("khối lượng" in p for p in terms))
        self.assertIn("SOS", terms)
        self.assertTrue(any("pha" in p for p in terms))

    def test_ict_block_pure_with_volume_imbalance(self):
        txt = "Dealing range 76,464–79,760, EQ 78,112, giá ở discount; FVG giảm chưa lấp 77,170–77,325; volume imbalance tại 77,300."
        self.assertEqual(mp.violations(txt, "ict"), [])

    def test_ict_acronyms_are_case_sensitive(self):
        self.assertEqual(mp.violations("giá đang ở vùng discount, sát swing low", "ict"), [])
        self.assertNotEqual(mp.violations("đỉnh AR", "ict"), [])

    def test_footprint_allows_wyckoff_but_not_ict(self):
        self.assertEqual(mp.violations("Hấp thụ tại đáy SC, delta âm mạnh, POC dịch lên", "footprint"), [])
        self.assertNotEqual(mp.violations("Delta xác nhận MSS", "footprint"), [])

    def test_heatmap_keeps_liquidity_words(self):
        self.assertEqual(mp.violations("Cụm thanh lý (liquidation cluster) 76,000; tường orderbook 78,000", "heatmap"), [])
        self.assertNotEqual(mp.violations("cụm thanh lý ngay dưới SC", "heatmap"), [])

    def test_synthesis_allows_everything(self):
        self.assertEqual(mp.violations("SC trùng SSL: một quan sát; MSS và SOS là một.", "synthesis"), [])

    def test_infer_method(self):
        self.assertEqual(mp.infer_method("SC mới (Cao trào bán)"), "wyckoff")
        self.assertEqual(mp.infer_method("BSL chưa quét gần nhất"), "ict")
        self.assertEqual(mp.infer_method("đỉnh AR/MSS đã đóng cửa vượt"), "mixed")
        self.assertEqual(mp.infer_method("đỉnh 9/9"), "neutral")

    def test_no_false_positives_on_ordinary_words(self):
        # short acronyms must not fire inside ordinary words (chart, market, target, start, post, cost)
        ict_txt = "The chart shows the market target at start; cost basis post-sweep; swing low held; scalping"
        self.assertEqual([p for p, _ in mp.violations(ict_txt, "ict")], [])
        wy_txt = "Bối cảnh 4H: đỉnh cũ 82,300 và đáy 62,535; bào mòn suốt đêm; nến 12:30 đóng 77,130 trên khối lượng 7.88×"
        self.assertEqual(mp.violations(wy_txt, "wyckoff"), [])

    def test_narrative_blocks_collects_labels_and_context(self):
        n3 = {"wyckoff": {"text_html": "a", "events": [{"label": "SC"}], "trading_range": {"high_label": "AR", "low_label": "SC"}},
              "ict": {"text_html": "b", "levels": [{"label": "BSL"}]},
              "context": {"wyckoff": {"text_html": "c", "events": [{"label": "ST"}]}, "ict": {"text_html": "d"}},
              "timeline": [{"wyckoff": "w", "ict": "i"}]}
        b = mp.narrative_blocks(n3)
        self.assertIn("SC", b["wyckoff"]); self.assertIn("ST", b["wyckoff"]); self.assertIn("c", b["wyckoff"]); self.assertIn("w", b["wyckoff"])
        self.assertIn("BSL ", b["ict"]); self.assertIn("d", b["ict"]); self.assertIn("i", b["ict"])

    def _grammar(self, phases, events, phase=None):
        bad=[]; cn.phase_grammar("X", {"phases": phases, "events": events, "phase": phase}, bad.append); return bad

    def test_phase_grammar_rejects_skipped_B_and_weak_SOS(self):
        bad=self._grammar([{"from":"2026-09-10T12:30:00Z","to":"2026-09-10T14:45:00Z","label":"Pha A"},{"from":"2026-09-10T14:45:00Z","to":"2026-09-10T16:45:00Z","label":"Pha C"},{"from":"2026-09-10T16:45:00Z","label":"Pha D"}],
                          [{"time":"2026-09-10T13:00:00Z","label":"SC 2,405.85 · KL 4.84x"},{"time":"2026-09-10T14:45:00Z","label":"AR 2,444.45 · KL 1.27x"},{"time":"2026-09-10T16:45:00Z","label":"SOS 2,448.78 · KL 0.99x"},{"time":"2026-09-10T17:30:00Z","label":"Đẩy giá 2,475.03 · KL 2.87x"}], "D")
        txt=" ".join(bad)
        self.assertIn("contiguous from A", txt); self.assertIn("Phase C has no test event", txt); self.assertIn("UA", txt); self.assertIn("Đẩy giá", txt)

    def test_phase_grammar_accepts_textbook_sequence(self):
        bad=self._grammar([{"from":"2026-09-10T12:30:00Z","to":"2026-09-10T14:45:00Z","label":"A"},{"from":"2026-09-10T14:45:00Z","to":"2026-09-10T23:15:00Z","label":"B"},{"from":"2026-09-10T23:15:00Z","label":"C"}],
                          [{"time":"2026-09-10T12:45:00Z","label":"SC 76,676 · KL 4.95x"},{"time":"2026-09-10T14:45:00Z","label":"AR 77,425 · KL 1.00x"},{"time":"2026-09-10T16:15:00Z","label":"ST 76,884 · KL 0.62x"},{"time":"2026-09-10T23:15:00Z","label":"Spring 76,464 · KL 1.47x"}], "C")
        self.assertEqual(bad, [])

    def test_htf_bias_follows_the_book(self):
        import htf_context as h
        self.assertEqual(h.bias_of({"structure":"tái tích lũy","phase":"C"}, {})[0], "long")
        self.assertEqual(h.bias_of({"structure":"phân phối","phase":"D"}, {})[0], "short")
        self.assertEqual(h.bias_of({"structure":"tích lũy","phase":"B"}, {})[0], "neutral")      # Phase B without a TR: cannot place the boundary
        tr={"structure":"tích lũy","phase":"B","trading_range":{"high":110,"low":100}}
        self.assertEqual(h.bias_of(tr, {"last":102})[0], "long")     # lower third of the HTF TR: CO buys here (WA p201), m5 local accumulation (WA p93)
        self.assertEqual(h.bias_of(tr, {"last":105})[0], "neutral")  # mid-range Phase B: no trade (WA p95–96)
        self.assertEqual(h.bias_of(tr, {"last":109})[0], "neutral")  # upper third of an accumulation: CO sells there, not a public long
        dist={"structure":"phân phối","phase":"B","trading_range":{"high":110,"low":100}}
        self.assertEqual(h.bias_of(dist, {"last":109})[0], "short"); self.assertEqual(h.bias_of(dist, {"last":101})[0], "neutral")
        self.assertEqual(h.bias_of({"structure":"chưa xác lập","phase":None}, {})[0], "neutral")
        self.assertEqual(h.bias_of(None, {"anchors":{"verdict":"PHÁ TRÊN AR"}})[0], "long")
        self.assertEqual(h.bias_of(None, {})[0], "unknown")

    def test_htf_check_verdict(self):
        import htf_context as h
        ctx={"tf":"4h","bias":"long"}
        self.assertEqual(h.check_verdict("THEO DÕI LONG", None, ctx, "<p>Bối cảnh 4h: tích lũy pha C.</p>"), [])
        self.assertTrue(any("ngược bối cảnh" in p for p in h.check_verdict("THEO DÕI SHORT", None, ctx, "<p>Bối cảnh 4h: …</p>")))
        self.assertEqual(h.check_verdict("THEO DÕI SHORT", None, ctx, "<p>Bối cảnh 4h: … đây là đọc ngược bối cảnh.</p>"), [])
        self.assertTrue(any("WA p93" in p for p in h.check_verdict("SETUP TIỀM NĂNG", "short", ctx, "<p>Bối cảnh 4h</p>")))
        self.assertTrue(any("chưa cho hướng" in p for p in h.check_verdict("SETUP TIỀM NĂNG", "long", {"tf":"4h","bias":"neutral"}, "<p>Bối cảnh 4h</p>")))
        self.assertTrue(any("mở đầu" in p for p in h.check_verdict("CHỜ", None, ctx, "<p>không nhắc khung lớn</p>")))
        self.assertEqual(h.check_verdict("CHỜ", None, None, "x"), [])

    def test_check_blocks_and_report(self):
        res = mp.check_blocks({"wyckoff": "FVG", "ict": ["ok", "Spring"], "synthesis": "FVG Spring"})
        self.assertEqual(set(res), {"wyckoff", "ict"})
        self.assertIn("wyckoff: 1", mp.report(res))


if __name__ == "__main__":
    unittest.main()
