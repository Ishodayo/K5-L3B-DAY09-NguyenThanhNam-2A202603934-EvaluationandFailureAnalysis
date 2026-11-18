# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` = item `E-014` seed 11, run ID `E-seeded_regression-20261118-d8a3` (`src/reports/eval_seeded_regression.json`). Dòng đó có `refund_amount_correct=false`, `pass_rate=false`, `reply_matches_ledger=false` |
| Triệu chứng | Grader Lab 8 FAIL `proposal_mismatch`. **Ledger ghi 90.000đ**, nhãn 120.000đ. Reply #6 nói "đã hoàn 120.000đ", tức là reply cũng lệch ledger (kéo theo cả triệu chứng FM-08) |
| Bước sai đầu tiên | #5 `proposal {"amount_vnd": 120000}`: agent tự trừ 30.000đ đã hoàn trước khi gọi host |
| Vì sao là bước *đầu tiên* | #2 investigator đọc đúng O-515 (trễ 5 ngày, đã xác minh hỏng). #3 `quote` 150.000đ đúng chính sách (SHIP-LATE-03 + DMG-04, cap 150.000đ). #4 `refund_history {refund_count: 1, refunded_vnd: 30000}` đúng dữ kiện. Đến #5 agent mới đổi số: host vốn đã tự trừ khoản đã hoàn, nên tiền bị trừ hai lần (150.000 − 30.000 − 30.000 = 90.000) |
| Failure mode | FM-05 pre_deducted (hệ quả phụ: FM-08 vì reply báo số tự tính) |
| Đối chứng | `fixed C-014@11`: chỉ có #1 handoff, #2 investigator, #3 quote 150.000đ, #4 reply 120.000đ. **Không có** event `refund_history`/`proposal`; host tự trừ một lần nên ledger 120.000đ, đúng nhãn |
| Regression test | `tests/test_lab9_trace_case.py`: `test_lab9_fm05_pre_deducted_caught_on_seeded_regression` (có event `proposal` và ledger ≠ nhãn) và `test_lab9_fm05_pre_deducted_absent_on_fixed` (không có `proposal`, ledger = nhãn). Đã chạy: 2 passed. Trong report eval, `RefundAmountCorrect` (ledger 90.000 ≠ 120.000) và `ReplyMatchesLedger` (reply 120.000 ≠ ledger 90.000) đều đánh FAIL dòng này |
| Chưa chắc chắn | Trace không có event cho phép trừ của host (chỉ thấy ledger cuối là 90.000đ), nên "host trừ lần hai" là suy ra từ ledger, không đọc được trực tiếp. Mới kiểm seed 11; với `seeded_regression` lỗi là tất định nên các seed khác cho cùng kết quả (đã thấy 5/5 seed ledger 90.000đ) |

Chạy lại:
```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11
python -m pytest -q -m student -o addopts= tests/test_lab9_trace_case.py
```

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
