"""The lab submission file: one JSON file per lab, uploaded on the course portal.

The last cell of every lab notebook calls

    ee105.save_submission("1.1", results, board=board)

which writes lab1.1_submission.json next to the notebook:

    {"format": "ee105-lab-submission/1", "lab": "1.1", "created": "2026-09-14T15:02:11-07:00",
     "simulated": false, "toolkit": "3.0", "python": "3.11.9",
     "board": {"firmware": "ee105 3.0", "device_id": "8A31C47E09D2F615"},
     "notes": null, "results": {...}}

The portal (ee105.org/portal) grades the file and records the grade. A run on the simulated
board is recorded as a practice run. The grading rules are in SUBMISSIONS.md of the lab kit
sources.
"""
import datetime
import json
import math
import platform
from pathlib import Path

FORMAT = "ee105-lab-submission/1"
MAX_BYTES = 150_000
LABS = ("0.1", "0.2", "1.1", "1.2", "2.1", "3.1", "3.2", "4.1", "4.2", "5.1")


def _clean(x, digits=6):
    """JSON-ready copy of x: numpy numbers and arrays become Python numbers and lists, NaN and
    infinity become None, floats keep `digits` significant digits (smaller files)."""
    try:
        import numpy as np
    except ImportError:            # pragma: no cover
        np = None
    if np is not None:
        if isinstance(x, np.ndarray):
            return [_clean(v, digits) for v in x.tolist()]
        if isinstance(x, np.generic):
            x = x.item()
    if hasattr(x, "to_dict") and hasattr(x, "columns"):          # pandas DataFrame
        return {str(c): _clean(x[c].to_numpy(), digits) for c in x.columns}
    if hasattr(x, "to_dict") and hasattr(x, "index"):            # pandas Series
        return {str(k): _clean(v, digits) for k, v in x.to_dict().items()}
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return float(f"{x:.{digits}g}")
    if isinstance(x, dict):
        return {str(k): _clean(v, digits) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v, digits) for v in x]
    return str(x)


def _board_info(board):
    if board is None:
        return None, False
    boards = board if isinstance(board, (list, tuple)) else [board]
    first = boards[0]
    info = dict(getattr(first, "info", {}) or {})
    if not info.get("firmware") and hasattr(first, "firmware"):
        try:
            first.firmware()
            info = dict(first.info)
        except Exception:
            pass
    simulated = any(bool(getattr(b, "simulated", False)) for b in boards)
    out = {"firmware": info.get("firmware"), "device_id": info.get("device_id")}
    if len(boards) > 1:
        out["other_device_ids"] = [dict(getattr(b, "info", {}) or {}).get("device_id") for b in boards[1:]]
    return out, simulated


def save_submission(lab, results, board=None, notes=None, folder=None):
    """Write lab<N.k>_submission.json for the course portal and say where it is.

    lab     : "1.1" (the lab number)
    results : dict of the lab's results (numbers, strings, lists; numpy and pandas are fine)
    board   : the board object of the lab (or a list of boards, the first one is the main one);
              None for labs without hardware
    notes   : optional text for the grader (for example "my partner was ...")
    Returns the path of the file.
    """
    from . import __version__
    lab = str(lab)
    if lab not in LABS:
        raise ValueError(f"lab must be one of {', '.join(LABS)}")
    info, simulated = _board_info(board)
    doc = {
        "format": FORMAT,
        "lab": lab,
        "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "simulated": simulated,
        "toolkit": __version__,
        "python": platform.python_version(),
        "board": info,
        "notes": notes,
        "results": _clean(results),
    }
    text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        big = sorted(((len(json.dumps(v)), k) for k, v in doc["results"].items()), reverse=True)[:3]
        raise ValueError(f"The submission would be {size / 1000:.0f} kB (limit {MAX_BYTES / 1000:.0f} kB). "
                         "Largest results: " + ", ".join(f"{k} ({n / 1000:.0f} kB)" for n, k in big))
    path = Path(folder or ".").resolve() / f"lab{lab}_submission.json"
    path.write_text(text, encoding="utf-8")
    print(f"[ok] Saved {path.name} ({size / 1000:.1f} kB) in {path.parent}")
    if simulated:
        print("[!!] This run used the SIMULATED board. The portal records it as a practice run (0 points). "
              "Run the lab on your demo board to get the grade.")
    print(f"     Upload this file on the course portal (ee105.org/portal) under Lab {lab}.")
    return path
