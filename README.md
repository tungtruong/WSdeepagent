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

### Session memory theo từng user/chat

- Bot tự nhớ lịch sử hội thoại theo từng `chat_id` và dùng làm ngữ cảnh cho câu hỏi mới.
- Giới hạn số lượt nhớ bằng biến `MEMORY_TURNS` (mặc định `3`).
- Memory được lưu xuống file `MEMORY_STORE_FILE` để vẫn giữ sau khi restart bot.
- Dùng `/reset` để xoá ngữ cảnh của phiên chat hiện tại.

### Whitelist user ID

- Thiết lập `TELEGRAM_WHITELIST_IDS` dạng danh sách id, cách nhau bởi dấu phẩy.
- Ví dụ: `TELEGRAM_WHITELIST_IDS=123456789,987654321`
- Để trống biến này nếu muốn cho phép tất cả user.

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
