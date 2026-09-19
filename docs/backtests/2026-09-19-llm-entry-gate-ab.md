# Cổng vào lệnh bằng LLM — A/B trên 20 lệnh ICT vào được (PIT) — 2026-09-19

A = không cổng (baseline): {"n": 20, "wins": 10, "win_rate": 0.5, "net_R": 19.08, "expectancy": 0.954}

| Model | ENTER | SKIP | unparsed | kỳ vọng ENTER | ròng ENTER | thắng/ENTER | bỏ đúng lệnh thua | bỏ nhầm lệnh thắng | độ trễ TB |
|---|---|---|---|---|---|---|---|---|---|
| sonnet | 0 | 14 | 6 | — | — | — | 5 | 9 | 15.3s |
<!-- sealed: docs/experiments/2026-09-19-an-llm-sonnet-entry-gate-pit-correct-and.json -->
| opus | 0 | 20 | 0 | — | — | — | 10 | 10 | 12.0s |
<!-- sealed: docs/experiments/2026-09-19-an-llm-opus-entry-gate-pit-correct-and-c.json -->
| fable | 0 | 14 | 6 | — | — | — | 5 | 9 | 14.2s |
<!-- sealed: docs/experiments/2026-09-19-an-llm-fable-entry-gate-pit-correct-and-.json -->

_n = 20 là hiệu chuẩn, không phải kiểm định. Mọi bản ghi ở trên đều `decision: PENDING` (§41 stage 11 là của con người)._
