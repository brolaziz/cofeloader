import asyncio
import logging
import shutil
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, ErrorEvent, FSInputFile, Message

from cofesave.config import ROOT, Settings
from cofesave.jobs import JobManager
from cofesave.links import LinkError, parse_link
from cofesave.storage import Storage


def router_for(settings: Settings, storage: Storage, jobs: JobManager) -> Router:
    router = Router()
    router.message.filter(F.chat.type.in_({ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP}))

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user:
            storage.add_user(message.from_user.id)
        welcome = (
            "CofeSave'ga xush kelibsiz!\n\nYouTube, Instagram yoki TikTok havolasini yuboring."
        )
        image = ROOT / "assets" / "brand" / "cofesave-welcome.png"
        if image.is_file():
            await message.answer_photo(FSInputFile(image), caption=welcome)
        else:
            await message.answer(welcome)

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(
            "Videoning 'Ulashish / Share' tugmasidan havolasini nusxalab, shu yerga yuboring.\n\n"
            "• YouTube videolari va Shorts\n• Instagram Reels va video postlar\n"
            "• TikTok videolari\n\n"
            f"Har safar bitta havola. Maksimal hajm: {settings.max_bytes // 1_000_000} MB. "
            f"Davomiylik: {settings.max_duration // 60} daqiqagacha.\n"
            "Yopiq videolar, jonli efirlar, pleylistlar va foto albomlar qo'llab-quvvatlanmaydi. "
            "Platforma cheklovi bo'lsa, boshqa video bilan sinab ko'ring."
        )

    @router.message(Command("stats"))
    async def stats(message: Message) -> None:
        if not message.from_user or message.from_user.id not in settings.admin_ids:
            await message.answer("Bu buyruq faqat administrator uchun.")
            return
        users, videos, sent, cached = storage.stats()
        await message.answer(
            f"Foydalanuvchilar: {users}\nKeshdagi videolar: {videos}\n"
            f"Yuborilgan: {sent}\nKeshdan yuborilgan: {cached}\n"
            f"Jarayonda: {len(jobs.tasks)}"
        )

    @router.message(F.text)
    async def video_link(message: Message) -> None:
        try:
            link = parse_link(message.text or "")
        except LinkError as error:
            if message.chat.type == ChatType.PRIVATE:
                await message.answer(str(error))
            return
        if message.from_user:
            storage.add_user(message.from_user.id)
        await jobs.handle(message, link)

    @router.message()
    async def other_message(message: Message) -> None:
        if message.chat.type == ChatType.PRIVATE:
            await message.answer(
                "Video fayli emas, uning YouTube, Instagram yoki TikTok havolasini yuboring."
            )

    @router.errors()
    async def handle_error(event: ErrorEvent) -> bool:
        # Telegram exceptions can contain request data; log only their class.
        logging.getLogger(__name__).error("Update failed: %s", type(event.exception).__name__)
        return True

    return router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # HTTP libraries must never log Bot API URLs containing the token.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    settings = Settings.load()
    if not shutil.which("ffmpeg") or not shutil.which("node"):
        raise RuntimeError(
            "FFmpeg va Node.js o'rnatilishi kerak. Docker orqali ham ishga tushirish mumkin."
        )
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    bot = Bot(settings.token, session=AiohttpSession(timeout=120))
    storage = Storage(settings.data_dir / "cofesave.sqlite3", bot.id)
    jobs = JobManager(settings, storage)
    dispatcher = Dispatcher()
    dispatcher.include_router(router_for(settings, storage, jobs))

    async def shutdown() -> None:
        await jobs.stop()

    dispatcher.shutdown.register(shutdown)
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Botni boshlash"),
                BotCommand(command="help", description="Yordam va limitlar"),
            ]
        )
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            tasks_concurrency_limit=50,
        )
    finally:
        await jobs.stop()
        storage.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
