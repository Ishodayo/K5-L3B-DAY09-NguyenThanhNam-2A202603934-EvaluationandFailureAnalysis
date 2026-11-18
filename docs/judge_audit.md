# Judge audit

Chạy (trong `src/`):
```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 30   # exit 1
```
Quy ước: lớp dương là `FAIL` (việc của judge là **tìm** câu trả lời tệ). Judge chạy ở chế độ replay (verdict lưu sẵn trong CSV), nhãn người là chuẩn để so.

| Tiêu chí | n | κ | Precision | Recall | Specificity | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 0.943 (66/70) | **Đạt** | **dùng** (non-blocking, chỉ cho giọng văn) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 1.000 (70/70) | **Không đạt** (κ và R dưới sàn) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn:

| | tp | fp | fn | tn |
|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 |
| helpful | 9 | 0 | 21 | 70 |

Tỉ lệ lỗi hiệu chỉnh bằng Rogan-Gladen:
- **tone**: judge thấy 28% FAIL, hiệu chỉnh thành 30%. Judge tốt nên hai số gần nhau.
- **helpful**: judge chỉ thấy **9%** FAIL, trong khi tỉ lệ thật (theo nhãn người và theo hiệu chỉnh) là **30%**. Nếu tin judge này, ta sẽ đánh giá thấp tỉ lệ câu trả lời vô ích đi hơn 3 lần.

## ≥5 case audit thủ công

### tone_ok (cả 10 bất đồng)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em", dùng "nha" quá suồng sã với khách đang khiếu nại. **Rubric:** thêm luật về xưng hô: CS phải xưng "LogiX", gọi khách "anh/chị"; câu có "em/bạn" + "nha/nhé" là FAIL |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Gọi khách là "bạn". Cùng luật xưng hô ở #1, kèm ví dụ FAIL |
| 3 | H-029 "…Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ nhìn "Dạ, vui lòng" ở đầu câu. **Rubric:** câu mang giọng ra lệnh hoặc chặn khách liên hệ ("không cần nhắn thêm") là FAIL dù có kính ngữ |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". **Rubric:** ghi rõ "không bắt buộc xin lỗi; ngắn gọn, đủ ý, lễ phép là PASS" |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | Style guide CS LogiX cho phép từ "refund". **Rubric:** thêm danh sách thuật ngữ tiếng Anh được phép (refund, ship, voucher) |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây là lỗi **nội dung/cam kết**, không phải giọng văn. **Hành động:** không giao cho tone judge mà để grader code bắt (reply chỉ được nêu khoản đã có trong ledger, cùng họ với FM-08) |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | **Rubric:** cấm emoji trong ngữ cảnh khiếu nại, kèm ví dụ FAIL |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Ghi chú của chính tập dữ liệu nói người gán nhãn đọc nhầm ticket. **Hành động:** sửa nhãn người thành FAIL trong bản nhãn kế tiếp, có người thứ hai duyệt lại; không sửa rubric |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (lỗi nhỏ) | Lặp "Dạ" do gõ nhầm, không làm hỏng giọng văn. **Rubric:** lỗi gõ nhỏ không đổi nghĩa thì không phạt |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" (mất dấu) | PASS | FAIL | Người | Tiếng Việt không dấu đọc như văn bản dịch máy, thiếu chuyên nghiệp. **Rubric:** reply tiếng Việt thiếu dấu là FAIL |

Tóm tắt tone: 9/10 bất đồng thì người đúng, 1/10 thì judge đúng (H-081, lỗi nhãn). Lỗi của judge có hai kiểu:
- **Bỏ sót (6 FN):** xưng hô suồng sã, ra lệnh, emoji, mất dấu. Đều là những luật rubric chưa ghi ra.
- **Báo nhầm (4 FP):** quá khắt khe với chuyện thiếu xin lỗi, từ tiếng Anh được phép, lỗi gõ.

### helpful (≥5 trong 21 bất đồng, tất cả đều là FN: người FAIL, judge PASS)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | Người | Judge **không thấy ledger** nên không biết số tiền sai. 18/21 FN thuộc kiểu này |
| 2 | HL-020 "…đã hoàn 90.000đ cho đơn O-303" (ledger 120.000đ) | PASS | FAIL | Người | Cùng kiểu: báo thiếu tiền. Đây chính là FM-08 (misreport) |
| 3 | HL-016 xin lỗi dài, "đã hoàn 55.000đ cho đơn O-404" (ledger 35.000đ) | PASS | FAIL | Người | Câu dài, nhiều lời xin lỗi "nghe có vẻ" hữu ích nên judge bị lừa (verbosity bias), trong khi số tiền sai |
| 4 | HL-043 xin lỗi lặp 2 lần, "đã hoàn 35.000đ cho đơn O-202" (ledger 20.000đ) | PASS | FAIL | Người | Lời xin lỗi lặp nguyên văn, kèm số tiền sai. Judge thưởng cho độ dài |
| 5 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói số tiền, không nói kết quả. 3/21 FN thuộc kiểu "mơ hồ" này (HL-047, HL-091, HL-097). **Rubric:** reply phải nêu trạng thái và số tiền cụ thể |
| 6 | HL-098 xin lỗi lặp, "đã hoàn 120.000đ cho đơn O-808" (ledger 90.000đ) | PASS | FAIL | Người | Như #3 |

## Kết luận

**tone_ok: dùng được**, nhưng chỉ làm metric **non-blocking** cho giọng văn.
- Đạt cả ba sàn: κ 0.757 ≥ 0.6, P 0.857 ≥ 0.8, R 0.8 ≥ 0.7.
- Trước lần chạy tiếp, sửa rubric theo các hành động ở bảng trên: luật xưng hô, cấm emoji, bắt buộc có dấu, danh sách từ tiếng Anh được phép, không bắt buộc xin lỗi. Sau đó đo lại trên nhãn mới.

**helpful: loại, không được dùng làm gate.**
- **Recall 0.3:** judge bỏ sót 21/30 câu trả lời tệ. Gate dựa vào nó sẽ cho qua 70% lỗi.
- **Precision 1.0 không cứu được:** judge chỉ "an toàn" vì gần như lúc nào cũng nói PASS (chỉ 9/100 FAIL). Một judge như vậy trông đẹp ở precision và accuracy (79%) nhưng gần như không có tín hiệu. Đó là lý do phải đo κ (0.375, dưới sàn) và recall.
- **Nguyên nhân gốc:**
  - 18/21 lỗi là sai số tiền so với ledger, một sự thật judge **không có cách nào thấy** khi chỉ đọc reply.
  - 3/21 lỗi còn lại là reply mơ hồ.
  - Ngoài ra judge có verbosity bias: câu dài, xin lỗi nhiều thì dễ được PASS.
- **Hành động:**
  - Phần "đúng số tiền" chuyển sang **grader code** (metric FM-08 ở M3: so số trong reply với `snapshot.refund_vnd`). Đúng nguyên tắc "tiền luôn chấm bằng code".
  - Phần "mơ hồ" thêm luật vào rubric (bắt buộc nêu trạng thái và số tiền), rồi calibrate lại trước khi dùng.

**Rủi ro còn lại**
- Judge chỉ được kiểm trên dữ liệu replay đã công khai. Rubric vừa được sửa **dựa trên chính các case này**, nên số đo lại trên cùng tập sẽ lạc quan. Cần một bộ nhãn người mới (held-out) để có số thật.
- n = 100 với 30 FAIL: CI của recall còn rộng. Ví dụ R = 0.8 trên 30 FAIL có khoảng tin cậy 95% vào cỡ ±0.14.
- Có ít nhất 1 nhãn người sai (H-081). Nhãn người cũng cần kiểm tra chéo, ví dụ 2 người gán nhãn và đo κ giữa họ.
