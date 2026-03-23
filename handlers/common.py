from __future__ import annotations

from services.container import AppServices
from telegram.ext import ContextTypes


def get_services(context: ContextTypes.DEFAULT_TYPE) -> AppServices:
    return context.application.bot_data["services"]
