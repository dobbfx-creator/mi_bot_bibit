# utils/decisions.py
from utils.logging_ex import get_logger
LOG = get_logger("decisions")

def log_partial_check(sym, side, mfe_pct, r_current, cfg):
    LOG.info(
        "PARCIAL? sym=%s side=%s mfe_pct=%.4f r_current=%.4f "
        "threshold_R=%.4f fraction=%.2f enabled=%s",
        sym, side, mfe_pct, r_current, cfg.at_R, cfg.fraction, cfg.enabled
    )

def log_trailing_move(sym, side, last_pivot, buffer_pct, new_sl, reason):
    LOG.info(
        "TRAILING MOVE sym=%s side=%s pivot=%.4f buffer=%.4f%% new_sl=%.4f reason=%s",
        sym, side, last_pivot, buffer_pct*100.0, new_sl, reason
    )

def log_skip(reason, **kv):
    LOG.warning("SKIP: %s | %s", reason, kv)
