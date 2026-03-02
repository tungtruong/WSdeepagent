# LangChain Deep Agent (Python)

Agent này tạo workflow nghiên cứu sâu theo 3 bước:
1. Lập kế hoạch nghiên cứu (chia câu hỏi lớn thành các câu hỏi con)
2. Nghiên cứu từng câu hỏi con bằng ReAct agent + web search
3. Tổng hợp thành báo cáo cuối

## 1) Cài đặt

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2) Cấu hình biến môi trường

```bash
copy .env.example .env
```

Điền `OPENAI_API_KEY` vào `.env`.
Điền thêm `TAVILY_API_KEY` vào `.env` để dùng web search.
Project hiện dùng package `langchain-tavily` cho phần Tavily search.

## 3) Chạy

```bash
python src/main.py --query "Phân tích xu hướng AI agent cho SMB trong năm 2026"
```

Tuỳ chọn:

```bash
python src/main.py --query "..." --max-subquestions 6 --print-artifacts
```

## 4) Chạy qua Telegram

1. Tạo bot bằng `@BotFather`, lấy token.
2. Điền `TELEGRAM_BOT_TOKEN` vào `.env`.
3. Chạy bot:

```bash
python src/telegram_bot.py
```

4. Vào Telegram, mở bot và chat trực tiếp hoặc dùng:

```text
/ask Phân tích cơ hội ứng dụng AI agent cho cửa hàng online nhỏ trong 2026
```

Lệnh đổi model trực tiếp trên Telegram:
- `/provider openai|local`
- `/model <ten-model>` (hoặc `/thinking <ten-model>`)

Ví dụ dùng model local trong LAN (OpenAI-compatible API):
- `DEFAULT_LLM_PROVIDER=local`
- `LOCAL_LLM_BASE_URL=http://192.168.1.10:11434/v1`
- `LOCAL_LLM_API_KEY=local`

## 5) Cài nhanh trên Arch Linux (service)

```bash
chmod +x scripts/install_arch_service.sh
./scripts/install_arch_service.sh
```

Sau khi chạy script:
- Kiểm tra trạng thái: `sudo systemctl status wsdeepagent.service`
- Xem log: `journalctl -u wsdeepagent.service -f`
- Nếu vừa tạo `.env`, hãy điền key rồi restart: `sudo systemctl restart wsdeepagent.service`

## 6) Update service trên Arch Linux

```bash
chmod +x scripts/update_service.sh
./scripts/update_service.sh
```

Script sẽ tự pull `main`, update dependencies và restart `wsdeepagent.service`.
Ngoài ra script sẽ tự bổ sung các biến mới còn thiếu từ `.env.example` vào `.env` (không ghi đè giá trị cũ).

### Session memory theo từng user/chat

- Bot tự nhớ lịch sử hội thoại theo từng `chat_id` và dùng làm ngữ cảnh cho câu hỏi mới.
- Giới hạn số lượt nhớ bằng biến `MEMORY_TURNS` (mặc định `3`).
- Memory được lưu xuống file `MEMORY_STORE_FILE` để vẫn giữ sau khi restart bot.
- Khi số lượt vượt ngưỡng, bot tự tóm tắt lịch sử cũ vào `MEMORY_SUMMARY_FILE` (bật/tắt bằng `MEMORY_SUMMARY_ENABLED`).
- Dùng `/reset` để xoá ngữ cảnh của phiên chat hiện tại.

### Mode switch

- Dùng `/mode auto|fast|balanced|deep` để đổi chế độ nghiên cứu theo từng chat.
- `DEFAULT_RESEARCH_MODE` đặt mode mặc định khi chưa chọn riêng.

### Quality gate

- Sau khi tổng hợp, bot tự chấm điểm chất lượng câu trả lời (0-100).
- Nếu điểm dưới `QUALITY_GATE_THRESHOLD`, bot tự refine thêm 1 vòng trước khi trả final.

### Whitelist user ID

- Thiết lập `TELEGRAM_WHITELIST_IDS` dạng danh sách id, cách nhau bởi dấu phẩy.
- Ví dụ: `TELEGRAM_WHITELIST_IDS=123456789,987654321`
- Để trống biến này nếu muốn cho phép tất cả user.

### Startup notify khi restart service

- Đặt `TELEGRAM_NOTIFY_CHAT_IDS` (danh sách chat id, cách nhau dấu phẩy) để bot tự nhắn khi vừa khởi động lại.
- Nội dung notify gồm trạng thái restart và model đang dùng.
- Nếu để trống `TELEGRAM_NOTIFY_CHAT_IDS`, bot sẽ fallback gửi vào các ID trong `TELEGRAM_WHITELIST_IDS` (nếu có).

### Progress report theo nhịp thời gian

- Bot gửi tiến trình research theo nhịp `TELEGRAM_PROGRESS_INTERVAL_SECONDS` (mặc định `10` giây) vào `TELEGRAM_PROGRESS_CHAT_IDS`.
- Nếu để trống `TELEGRAM_PROGRESS_CHAT_IDS`, bot fallback dùng `TELEGRAM_NOTIFY_CHAT_IDS`.
- Chat đang hỏi chỉ nhận phản hồi cuối cùng (không nhận log tiến trình).

## Cấu trúc

- `src/deep_agent.py`: logic deep agent
- `src/main.py`: CLI entrypoint
- `src/telegram_bot.py`: Telegram chat interface
- `requirements.txt`: dependencies
- `.env.example`: mẫu biến môi trường

## Gợi ý mở rộng

- Thay Tavily bằng tool riêng (SerpAPI, internal search)
- Lưu `artifacts` xuống file JSON để audit
- Bổ sung guardrails và chấm điểm chất lượng câu trả lời
