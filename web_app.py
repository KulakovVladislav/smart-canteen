# -*- coding: utf-8 -*-
"""Entry point for Streamlit: delegates to ui/streamlit/main.py."""
import os, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from ui.streamlit.main import main  # noqa

if __name__ == "__main__":
    main()
