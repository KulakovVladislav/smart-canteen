# -*- coding: utf-8 -*-
"""Точка входа Telegram-бота «Умной столовой»."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.telegram_bot import run_bot

if __name__ == "__main__":
    run_bot()
