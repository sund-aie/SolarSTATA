"""Recursively convert NaN/Inf/numpy types to JSON-safe values.

FastAPI's default JSON encoder rejects NaN, but pandas/scipy produce
NaN frequently (missing values, undefined statistics). We convert
NaN/Inf to None so the response is valid JSON.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def safe(obj):
    if isinstance(obj, dict):
        return {k: safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return safe(obj.tolist())
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return obj
