from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Set

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from deep_agent import DeepResearchAgent


TELEGRAM_MESSAGE_LIMIT = 4000


def load_memory_store(memory_file: str) -> Dict[str, List[Dict[str, str]]]:
    path = Path(memory_file)
    if not path.exists():
        return {}

    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(raw_data, dict):
        return {}

    normalized: Dict[str, List[Dict[str, str]]] = {}
    for key, value in raw_data.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue

        turns: List[Dict[str, str]] = []
        for turn in value:
            if not isinstance(turn, dict):
                continue
            user = str(turn.get("user", "")).strip()
            assistant = str(turn.get("assistant", "")).strip()
            if user or assistant:
                turns.append({"user": user, "assistant": assistant})

        normalized[key] = turns

    return normalized


def save_memory_store(memory_file: str, memory_store: Dict[str, List[Dict[str, str]]]) -> None:
    path = Path(memory_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(memory_store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_summary_store(summary_file: str) -> Dict[str, str]:
    path = Path(summary_file)
    if not path.exists():
        return {}

    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(raw_data, dict):
        return {}

    normalized: Dict[str, str] = {}
    for key, value in raw_data.items():
        if isinstance(key, str):
            normalized[key] = str(value or "").strip()
    return normalized


def save_summary_store(summary_file: str, summary_store: Dict[str, str]) -> None:
    path = Path(summary_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary_store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_whitelist_ids(raw_ids: str | None) -> Set[int]:
    if not raw_ids:
        return set()

    whitelist: Set[int] = set()
    for value in raw_ids.split(","):
        item = value.strip()
        if not item:
            continue
        try:
            whitelist.add(int(item))
        except ValueError:
            continue

    return whitelist


def parse_chat_ids(raw_ids: str | None) -> List[int]:
    if not raw_ids:
        return []

    chat_ids: List[int] = []
    for value in raw_ids.split(","):
        item = value.strip()
        if not item:
            continue
        try:
            chat_ids.append(int(item))
        except ValueError:
            continue

    return chat_ids


def split_message(text: str, max_len: int = TELEGRAM_MESSAGE_LIMIT) -> List[str]:
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    remaining = text

    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut == -1 or cut < int(max_len * 0.6):
            cut = max_len
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)

    return [chunk for chunk in chunks if chunk]


def build_contextual_query(query: str, memory: List[Dict[str, str]]) -> str:
    if not memory:
        return query

    turns = [
        f"User: {turn['user']}\nAssistant: {turn['assistant']}"
        for turn in memory
    ]
    history = "\n\n".join(turns)

    return (
        "Đây là lịch sử hội thoại trước đó giữa user và assistant. "
        "Hãy dùng nó làm ngữ cảnh để trả lời câu hỏi mới một cách nhất quán.\n\n"
        f"Lịch sử:\n{history}\n\n"
        f"Câu hỏi mới: {query}"
    )


async def ensure_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    whitelist_ids: Set[int] = context.application.bot_data["whitelist_ids"]
    if not whitelist_ids:
        return True

    user = update.effective_user
    user_id = user.id if user else None
    if user_id in whitelist_ids:
        return True

    if update.message:
        await update.message.reply_text("Bạn không có quyền dùng bot này.")
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_authorized(update, context):
        return
    await update.message.reply_text(
        "Chào bạn. Gửi câu hỏi bất kỳ để mình research sâu bằng Deep Agent.\n"
        "Bạn cũng có thể dùng: /ask <câu hỏi>."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_authorized(update, context):
        return
    await update.message.reply_text(
        "Cách dùng:\n"
        "- Gửi trực tiếp nội dung cần research\n"
        "- Hoặc /ask <nội dung>\n"
        "- /mode auto|fast|balanced|deep để đổi chế độ\n"
        "- Dùng /reset để xoá ngữ cảnh hội thoại hiện tại\n"
        "Bot sẽ lập kế hoạch, research và trả về kết quả tổng hợp."
    )


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_authorized(update, context):
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Vui lòng nhập câu hỏi sau /ask")
        return

    await handle_query(update, context, query)


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_authorized(update, context):
        return

    chat_id = str(update.effective_chat.id)
    mode_store: Dict[str, str] = context.application.bot_data["mode_store"]
    default_mode: str = context.application.bot_data["default_mode"]

    if not context.args:
        current_mode = mode_store.get(chat_id, default_mode)
        await update.message.reply_text(
            "Mode hiện tại: "
            f"{current_mode}. Dùng /mode auto|fast|balanced|deep để đổi."
        )
        return

    requested_mode = context.args[0].strip().lower()
    allowed_modes = {"auto", "fast", "balanced", "deep"}
    if requested_mode not in allowed_modes:
        await update.message.reply_text("Mode không hợp lệ. Chỉ nhận: auto, fast, balanced, deep.")
        return

    mode_store[chat_id] = requested_mode
    await update.message.reply_text(f"Đã chuyển mode sang: {requested_mode}")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_authorized(update, context):
        return

    chat_id = update.effective_chat.id
    memory_store: Dict[str, List[Dict[str, str]]] = context.application.bot_data["memory_store"]
    summary_store: Dict[str, str] = context.application.bot_data["summary_store"]
    memory_file: str = context.application.bot_data["memory_file"]
    summary_file: str = context.application.bot_data["summary_file"]
    memory_store[str(chat_id)] = []
    summary_store[str(chat_id)] = ""
    save_memory_store(memory_file, memory_store)
    save_summary_store(summary_file, summary_store)
    await update.message.reply_text("Đã xoá ngữ cảnh hội thoại của phiên chat này.")


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_authorized(update, context):
        return

    query = (update.message.text or "").strip()
    if not query:
        return
    await handle_query(update, context, query)


async def handle_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
) -> None:
    agent: DeepResearchAgent = context.application.bot_data["deep_agent"]
    max_subquestions: int = context.application.bot_data["max_subquestions"]
    quality_gate_threshold: int = context.application.bot_data["quality_gate_threshold"]
    mode_store: Dict[str, str] = context.application.bot_data["mode_store"]
    default_mode: str = context.application.bot_data["default_mode"]
    memory_store: Dict[str, List[Dict[str, str]]] = context.application.bot_data["memory_store"]
    summary_store: Dict[str, str] = context.application.bot_data["summary_store"]
    memory_summary_enabled: bool = context.application.bot_data["memory_summary_enabled"]
    memory_file: str = context.application.bot_data["memory_file"]
    summary_file: str = context.application.bot_data["summary_file"]
    memory_turns: int = context.application.bot_data["memory_turns"]
    progress_interval_seconds: int = context.application.bot_data["progress_interval_seconds"]
    progress_chat_ids: List[int] = context.application.bot_data["progress_chat_ids"]
    chat_id = update.effective_chat.id
    chat_key = str(chat_id)
    selected_mode = mode_store.get(chat_key, default_mode)
    chat_memory = memory_store.setdefault(chat_key, [])
    chat_summary = summary_store.get(chat_key, "")
    contextual_query = build_contextual_query(query, chat_memory)
    if chat_summary:
        contextual_query = (
            "Tóm tắt ngữ cảnh dài hạn của hội thoại:\n"
            f"{chat_summary}\n\n"
            f"{contextual_query}"
        )
    loop = asyncio.get_running_loop()
    progress_state = {"latest": None, "sent": None, "done": False}

    async def send_progress_message(message: str) -> None:
        if not progress_chat_ids:
            return
        for target_chat_id in progress_chat_ids:
            try:
                await context.application.bot.send_message(chat_id=target_chat_id, text=message)
            except Exception:
                continue

    async def periodic_progress_sender() -> None:
        while not progress_state["done"]:
            await asyncio.sleep(progress_interval_seconds)
            latest = progress_state["latest"]
            if latest and latest != progress_state["sent"]:
                await send_progress_message(latest)
                progress_state["sent"] = latest

        latest = progress_state["latest"]
        if latest and latest != progress_state["sent"]:
            await send_progress_message(latest)
            progress_state["sent"] = latest

    reporter_task = asyncio.create_task(periodic_progress_sender())

    def set_latest_progress(message: str) -> None:
        progress_state["latest"] = message

    def progress_callback(message: str) -> None:
        loop.call_soon_threadsafe(
            set_latest_progress,
            message,
        )

    try:
        result = await asyncio.to_thread(
            agent.run,
            contextual_query,
            max_subquestions,
            progress_callback,
            query,
            False,
            selected_mode,
            quality_gate_threshold,
        )
    except Exception as exc:
        progress_state["done"] = True
        await reporter_task
        await update.message.reply_text(f"Có lỗi khi research: {exc}")
        return
    finally:
        progress_state["done"] = True

    await reporter_task

    answer = result.get("final_answer", "Không có kết quả.")
    chat_memory.append({"user": query, "assistant": answer})
    if len(chat_memory) > memory_turns:
        removed_turns = chat_memory[:-memory_turns]
        del chat_memory[:-memory_turns]
        if memory_summary_enabled and removed_turns:
            previous_summary = summary_store.get(chat_key, "")
            merged_summary = await asyncio.to_thread(
                agent.summarize_memory,
                previous_summary,
                removed_turns,
            )
            summary_store[chat_key] = merged_summary
    save_memory_store(memory_file, memory_store)
    save_summary_store(summary_file, summary_store)

    chunks = split_message(answer)

    for idx, chunk in enumerate(chunks, start=1):
        if len(chunks) > 1:
            header = f"(Phần {idx}/{len(chunks)})\n"
            await update.message.reply_text(header + chunk)
        else:
            await update.message.reply_text(chunk)


async def notify_startup(application: Application) -> None:
    notify_chat_ids: List[int] = application.bot_data["notify_chat_ids"]
    model_name: str = application.bot_data["model_name"]

    if not notify_chat_ids:
        return

    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = (
        "✅ WSDeepAgent vừa restart thành công.\n"
        f"Model đang dùng: {model_name}\n"
        f"Started at: {started_at}"
    )

    for chat_id in notify_chat_ids:
        try:
            await application.bot.send_message(chat_id=chat_id, text=message)
        except Exception:
            continue


def main() -> None:
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token.strip() == "your_telegram_bot_token_here":
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN. Hãy tạo file .env từ .env.example")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Thiếu OPENAI_API_KEY. Hãy tạo file .env từ .env.example")

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    max_subquestions = int(os.getenv("MAX_SUBQUESTIONS", "4"))
    quality_gate_threshold = int(os.getenv("QUALITY_GATE_THRESHOLD", "70"))
    default_mode = os.getenv("DEFAULT_RESEARCH_MODE", "auto").strip().lower()
    if default_mode not in {"auto", "fast", "balanced", "deep"}:
        default_mode = "auto"
    memory_turns = int(os.getenv("MEMORY_TURNS", "3"))
    memory_summary_enabled = os.getenv("MEMORY_SUMMARY_ENABLED", "true").strip().lower() == "true"
    memory_file = os.getenv("MEMORY_STORE_FILE", "data/memory_store.json")
    summary_file = os.getenv("MEMORY_SUMMARY_FILE", "data/memory_summary.json")
    progress_interval_seconds = int(os.getenv("TELEGRAM_PROGRESS_INTERVAL_SECONDS", "10"))
    whitelist_ids = parse_whitelist_ids(os.getenv("TELEGRAM_WHITELIST_IDS"))
    notify_chat_ids = parse_chat_ids(os.getenv("TELEGRAM_NOTIFY_CHAT_IDS"))
    progress_chat_ids = parse_chat_ids(os.getenv("TELEGRAM_PROGRESS_CHAT_IDS"))
    if not notify_chat_ids and whitelist_ids:
        notify_chat_ids = sorted(list(whitelist_ids))
    if not progress_chat_ids:
        progress_chat_ids = notify_chat_ids

    app = Application.builder().token(token).post_init(notify_startup).build()
    app.bot_data["deep_agent"] = DeepResearchAgent(model_name=model_name)
    app.bot_data["model_name"] = model_name
    app.bot_data["max_subquestions"] = max_subquestions
    app.bot_data["quality_gate_threshold"] = max(1, min(100, quality_gate_threshold))
    app.bot_data["default_mode"] = default_mode
    app.bot_data["mode_store"] = {}
    app.bot_data["memory_turns"] = memory_turns
    app.bot_data["memory_summary_enabled"] = memory_summary_enabled
    app.bot_data["memory_file"] = memory_file
    app.bot_data["summary_file"] = summary_file
    app.bot_data["memory_store"] = load_memory_store(memory_file)
    app.bot_data["summary_store"] = load_summary_store(summary_file)
    app.bot_data["whitelist_ids"] = whitelist_ids
    app.bot_data["notify_chat_ids"] = notify_chat_ids
    app.bot_data["progress_chat_ids"] = progress_chat_ids
    app.bot_data["progress_interval_seconds"] = max(3, progress_interval_seconds)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
