import sys

from services import telegram_bot as _m

sys.modules[__name__] = _m
