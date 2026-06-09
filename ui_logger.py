"""ui_logger.py — Structured input/event logger. File=DEBUG, stdout=INFO."""
from __future__ import annotations
import logging as _logging

def _setup() -> _logging.Logger:
    log = _logging.getLogger("tactics.input")
    log.setLevel(_logging.DEBUG)
    if log.handlers: return log
    fmt = _logging.Formatter("%(asctime)s.%(msecs)03d  %(levelname)-5s  %(message)s", "%H:%M:%S")
    for h, lvl in ((_logging.FileHandler("tactics_input.log","a","utf-8"), _logging.DEBUG),
                   (_logging.StreamHandler(), _logging.INFO)):
        h.setLevel(lvl); h.setFormatter(fmt); log.addHandler(h)
    return log

ILOG = _setup()

def _ilog(event, detail="", level=_logging.DEBUG, phase=None, caller=""):
    ILOG.log(level, f"{f'[{phase.name}]':<18} {event:<22} {detail}{f'  ← {caller}' if caller else ''}")
