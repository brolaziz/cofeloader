from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import Chat, Message, Update, User

from cofesave.app import router_for
from cofesave.jobs import JobManager


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/start", "CofeSave"),
        ("/help", "YouTube"),
        ("/stats", "Foydalanuvchilar"),
        ("hello", "Bitta"),
    ],
)
async def test_real_dispatcher_routes_commands_without_network(text, expected, settings, storage):
    calls = []

    async def request(bot, method, **_kwargs):
        calls.append(method)
        return Message(
            message_id=2,
            date=datetime.now(UTC),
            chat=Chat(id=1, type="private"),
            text=getattr(method, "text", None),
        )

    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.session.make_request = AsyncMock(side_effect=request)
    jobs = JobManager(settings, storage)
    dispatcher = Dispatcher()
    dispatcher.include_router(router_for(settings, storage, jobs))
    try:
        await dispatcher.feed_update(
            bot,
            Update(
                update_id=1,
                message=Message(
                    message_id=1,
                    date=datetime.now(UTC),
                    chat=Chat(id=1, type="private"),
                    from_user=User(id=1, is_bot=False, first_name="Tester"),
                    text=text,
                ),
            ),
        )
        assert len(calls) == 1
        response = calls[0]
        assert isinstance(response, SendMessage | SendPhoto)
        assert expected in (getattr(response, "text", None) or response.caption)
    finally:
        await jobs.stop()
        await bot.session.close()


async def test_non_admin_cannot_read_stats(settings, storage, message):
    router = router_for(settings, storage, JobManager(settings, storage))
    stats = next(
        handler.callback
        for handler in router.message.handlers
        if handler.callback.__name__ == "stats"
    )
    message.from_user.id = 2
    await stats(message)
    assert "faqat administrator" in message.answer.call_args.args[0]


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
async def test_group_video_link_is_queued(chat_type, settings, storage):
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.session.make_request = AsyncMock()
    jobs = JobManager(settings, storage)
    jobs.enqueue = AsyncMock()
    dispatcher = Dispatcher()
    dispatcher.include_router(router_for(settings, storage, jobs))
    message = Message(
        message_id=10,
        date=datetime.now(UTC),
        chat=Chat(id=-100123, type=chat_type),
        from_user=User(id=1, is_bot=False, first_name="Tester"),
        text="https://youtu.be/dQw4w9WgXcQ",
        message_thread_id=42 if chat_type == "supergroup" else None,
        is_topic_message=chat_type == "supergroup",
    )
    try:
        await dispatcher.feed_update(bot, Update(update_id=10, message=message))
        jobs.enqueue.assert_awaited_once()
        queued, link = jobs.enqueue.call_args.args
        assert queued.chat.id == -100123
        assert queued.message_thread_id == message.message_thread_id
        assert link.platform == "YouTube"
    finally:
        await bot.session.close()


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
@pytest.mark.parametrize("text", ["Salom hammaga!", "https://example.com/", None])
async def test_group_chatter_is_ignored(chat_type, text, settings, storage):
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.session.make_request = AsyncMock()
    jobs = JobManager(settings, storage)
    jobs.enqueue = AsyncMock()
    dispatcher = Dispatcher()
    dispatcher.include_router(router_for(settings, storage, jobs))
    try:
        await dispatcher.feed_update(
            bot,
            Update(
                update_id=20,
                message=Message(
                    message_id=20,
                    date=datetime.now(UTC),
                    chat=Chat(id=-100123, type=chat_type),
                    from_user=User(id=1, is_bot=False, first_name="Tester"),
                    text=text,
                ),
            ),
        )
        jobs.enqueue.assert_not_awaited()
        bot.session.make_request.assert_not_awaited()
    finally:
        await bot.session.close()
