from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import AnswerCallbackQuery, SendMessage, SendPhoto
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from cofesave.app import router_for
from cofesave.formats import DownloadFormat
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


@pytest.mark.parametrize("chat_type", ["private", "group", "supergroup"])
async def test_video_link_offers_formats_and_routes_selection(chat_type, settings, storage):
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.session.make_request = AsyncMock()
    jobs = JobManager(settings, storage)
    jobs.handle = AsyncMock()
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
        jobs.handle.assert_not_awaited()
        sent = bot.session.make_request.call_args.args[1]
        assert sent.reply_parameters.message_id == message.message_id
        buttons = {
            button.text: button for row in sent.reply_markup.inline_keyboard for button in row
        }
        assert set(buttons) == {"Audio (MP3)", "360p", "720p", "1080p", "Avtomatik"}
        menu = message.model_copy(update={"message_id": 11, "reply_to_message": message})
        callback = CallbackQuery(
            id="choice",
            from_user=User(id=2, is_bot=False, first_name="Someone else"),
            chat_instance="test",
            message=menu,
            data=buttons["Audio (MP3)"].callback_data,
        )
        await dispatcher.feed_update(bot, Update(update_id=11, callback_query=callback))
        jobs.handle.assert_not_awaited()
        assert isinstance(bot.session.make_request.call_args.args[1], AnswerCallbackQuery)
        callback = callback.model_copy(update={"from_user": message.from_user})
        await dispatcher.feed_update(bot, Update(update_id=12, callback_query=callback))
        jobs.handle.assert_awaited_once()
        received, link, selection = jobs.handle.call_args.args
        assert received.chat.id == -100123
        assert received.message_thread_id == message.message_thread_id
        assert link.platform == "YouTube"
        assert selection is DownloadFormat.MP3
    finally:
        await bot.session.close()


@pytest.mark.parametrize("chat_type", ["group", "supergroup"])
@pytest.mark.parametrize("text", ["Salom hammaga!", "https://example.com/", None])
async def test_group_chatter_is_ignored(chat_type, text, settings, storage):
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    bot.session.make_request = AsyncMock()
    jobs = JobManager(settings, storage)
    jobs.handle = AsyncMock()
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
        jobs.handle.assert_not_awaited()
        bot.session.make_request.assert_not_awaited()
    finally:
        await bot.session.close()
