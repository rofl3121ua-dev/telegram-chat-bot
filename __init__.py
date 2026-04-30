from telegram.ext import Application

from .callbacks import register_callback_handlers
from .commands import register_command_handlers
from .messages import register_message_handlers
from .poop import register_poop_handlers


def register_handlers(app: Application) -> None:
    register_command_handlers(app)
    register_poop_handlers(app)
    register_callback_handlers(app)
    register_message_handlers(app)
