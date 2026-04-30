from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from i18n import t


async def on_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_chat:
        return
    await query.answer()

    selected = "uk" if query.data == "lang:uk" else "ru"
    context.chat_data["lang"] = selected
    context.chat_data["lang_locked"] = True
    text_key = "lang_set_uk" if selected == "uk" else "lang_set_ru"
    await query.edit_message_text(t(selected, text_key))


def register_callback_handlers(app) -> None:
    app.add_handler(CallbackQueryHandler(on_language_callback, pattern=r"^lang:(ru|uk)$"))
