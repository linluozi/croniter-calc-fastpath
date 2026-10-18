"""Differential equivalence harness: upstream croniter vs. the patched one.

Both implementations are loaded from their source files as independent
modules, so the comparison does not depend on installation order.

Usage:
    python diff_equiv.py <upstream croniter.py> <patched croniter.py> [--quick]
"""

import importlib.util
import itertools
import random
import sys
import traceback
from datetime import datetime, timedelta

failures = []


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def record(kind, detail):
    if len(failures) < 40:
        failures.append((kind, detail))


def run_sequence(mod, expr, start, count, direction, ret_type=None):
    out = []
    try:
        it = mod.croniter(expr, start, ret_type=ret_type)
        for _ in range(count):
            out.append(next(it) if direction == "next" else it.get_prev(ret_type))
    except Exception as exc:  # noqa: BLE001 - the exception itself is compared
        out.append(("EXC", type(exc).__name__, str(exc)))
    return out


def compare_sequence(up, opt, expr, start, count, direction, ret_type=None):
    a = run_sequence(up, expr, start, count, direction, ret_type)
    b = run_sequence(opt, expr, start, count, direction, ret_type)
    if a != b:
        record(
            "sequence",
            {
                "expr": expr,
                "start": repr(start),
                "direction": direction,
                "ret_type": getattr(ret_type, "__name__", ret_type),
                "upstream": a[:6],
                "patched": b[:6],
            },
        )
    return len(a)


EXPRESSIONS = [
    "* * * * *",
    "*/5 * * * *",
    "0 0 * * *",
    "0 0 1 * *",
    "0 0 L * *",
    "0 0 31 * *",
    "0 0 30 2 *",
    "0 0 * * 1",
    "0 0 * * 0",
    "0 0 * * 7",
    "0 0 * * sat",
    "0 0 * * 1#2",
    "0 0 * * 5#5",
    "0 0 * * 0#1",
    "0 0 * * l5",
    "0 0 1 * wed",
    "0 0 15 * 3",
    "0 0 1W * *",
    "0 0 15W * *",
    "0 0 LW * *",
    "0 0 W1 * *",
    "0 0 29 2 *",
    "0 0 29 2 1",
    "0 6 30 3 *",
    "0 0 31 4 *",
    "0 0 31 2 *",
    "15 0,3 * 3 *",
    "0 */3 * * *",
    "0 0 */3 * *",
    "30 2 * * *",
    "0 0 * 1,7 *",
    "0 0 1,15,31 * *",
    "59 23 31 12 *",
    "0 0 1 1 *",
    "5 4 * * sun",
    "0 12 * * mon-fri",
    "0 0 1-7 * *",
    "0 0 * * 1-5",
    "0 0 1 1,4,7,10 *",
    "0 0 * * 6#3",
    "0 0 * 2 1#5",
    "0 0 29 2 *",
    "0 0 30 2 *",
]

SECOND_EXPRESSIONS = [
    "*/15 * * * * *",
    "0 0 0 * * *",
    "30 0 0 * * *",
    "0 0 0 1 * *",
    "0 0 0 L * *",
    "0 0 0 * * 1#2",
    "0 0 0 15W * *",
    "0 0 0 29 2 *",
    "59 59 23 31 12 *",
    "*/7 */5 * * * *",
    # `*` in the seconds field keeps the sub-minute part of the cursor, so the
    # hour/minute/day jumps below must not reset it. Without these the
    # backwards branch of the hour processor is not covered.
    "* * 5,17 * * *",
    "* 0 0,12 * * *",
    "* */15 1,13 * * *",
    "* 30 2 * * 1#2",
    "* 0 3 15W * *",
    "* 0 0 L * *",
    "* 45 23 31 12 *",
    "*/5 * 4,16 * * *",
]

START_DATES = [
    datetime(2010, 1, 23, 12, 18),
    datetime(2010, 2, 25),
    datetime(2010, 8, 25, 15, 56),
    datetime(1996, 2, 27),
    datetime(2000, 2, 27),
    datetime(2024, 1, 1),
    datetime(2024, 2, 28, 23, 59),
    datetime(2024, 2, 29, 0, 0),
    datetime(2024, 12, 31, 23, 59, 30),
    datetime(2025, 3, 1, 0, 0),
    datetime(2025, 4, 30, 23, 59),
    datetime(2026, 10, 18, 15, 29, 17, 654321),
    datetime(1970, 1, 1, 0, 0),
    datetime(2038, 1, 19, 3, 14, 7),
    datetime(2099, 12, 31, 23, 59),
]

COUNT = 25 if "--quick" not in sys.argv else 6


def main():
    up = load(sys.argv[1], "croniter_up")
    opt = load(sys.argv[2], "croniter_opt")
    total = 0

    # 1. forward / backward sequences, datetime and float return types
    for expr in EXPRESSIONS:
        for start in START_DATES:
            for direction in ("next", "prev"):
                for ret_type in (datetime, float):
                    total += compare_sequence(up, opt, expr, start, COUNT, direction, ret_type)

    # 2. second-resolution expressions
    for expr in SECOND_EXPRESSIONS:
        for start in START_DATES:
            for direction in ("next", "prev"):
                total += compare_sequence(up, opt, expr, start, COUNT, direction, datetime)

    # 3. timezone aware iteration (DST transitions)
    try:
        from zoneinfo import ZoneInfo
    except ImportError:  # pragma: no cover
        ZoneInfo = None
    if ZoneInfo is not None:
        for tzname in ("Europe/Berlin", "Europe/Bucharest", "America/New_York",
                       "Australia/Lord_Howe", "Asia/Shanghai"):
            tz = ZoneInfo(tzname)
            for expr in ("15 0,3 * 3 *", "30 2 * * *", "0 0 * * *", "0 2 * * 0",
                         "0 0 L * *", "0 0 * * 1#2", "0 0 1W * *"):
                for start in (datetime(2010, 1, 25, tzinfo=tz),
                              datetime(2023, 3, 25, 12, 0, tzinfo=tz),
                              datetime(2023, 10, 28, 12, 0, tzinfo=tz),
                              datetime(2024, 3, 9, 12, 0, tzinfo=tz)):
                    for direction in ("next", "prev"):
                        total += compare_sequence(up, opt, expr, start, 12, direction, datetime)

    # 4. croniter_range
    for expr in ("0 0 * * *", "*/5 * * * *", "0 0 1 * *", "0 0 * * 1#2", "0 0 31 * *"):
        for start, stop in (
            (datetime(2024, 1, 1), datetime(2024, 3, 1)),
            (datetime(2024, 3, 1), datetime(2024, 1, 1)),
            (datetime(2024, 2, 27), datetime(2024, 3, 2)),
        ):
            for exclude_ends in (False, True):
                for ret_type in (datetime, float):
                    a = list(up.croniter_range(start, stop, expr,
                                               ret_type=ret_type,
                                               exclude_ends=exclude_ends))
                    b = list(opt.croniter_range(start, stop, expr,
                                                ret_type=ret_type,
                                                exclude_ends=exclude_ends))
                    total += len(a)
                    if a != b:
                        record("range", {"expr": expr, "start": repr(start),
                                         "stop": repr(stop),
                                         "exclude_ends": exclude_ends,
                                         "upstream": a[:5], "patched": b[:5]})

    # 5. match()/match_range() on a minute grid
    for expr in ("*/5 * * * *", "0 0 * * 1#2", "0 0 L * *", "0 0 1W * *"):
        base = datetime(2024, 1, 1)
        a = [up.croniter.match(expr, base + timedelta(days=i, hours=h))
             for i in range(40) for h in (0, 6, 12)]
        b = [opt.croniter.match(expr, base + timedelta(days=i, hours=h))
             for i in range(40) for h in (0, 6, 12)]
        total += len(a)
        if a != b:
            record("match", {"expr": expr})

    # 6. expand()/is_valid() parity on a generated expression corpus
    rng = random.Random(20261018)
    fields = ["*", "0", "1", "5", "7", "12", "31", "*/2", "*/5", "0-30", "1-31",
              "1,15,31", "L", "1W", "15W", "mon", "fri", "sat", "sun", "1#2",
              "5#5", "l5", "jan", "dec"]
    corpus = set()
    for _ in range(1200):
        parts = [rng.choice(fields) for _ in range(5)]
        corpus.add(" ".join(parts))
    corpus.update(EXPRESSIONS)
    for expr in sorted(corpus):
        total += 1
        try:
            a = ("ok", up.croniter.expand(expr))
        except Exception as exc:  # noqa: BLE001
            a = ("exc", type(exc).__name__, str(exc))
        try:
            b = ("ok", opt.croniter.expand(expr))
        except Exception as exc:  # noqa: BLE001
            b = ("exc", type(exc).__name__, str(exc))
        if a != b:
            record("expand", {"expr": expr, "upstream": repr(a)[:200],
                              "patched": repr(b)[:200]})
        if a[0] == "ok":
            va = up.croniter.is_valid(expr)
            vb = opt.croniter.is_valid(expr)
            if va != vb:
                record("is_valid", {"expr": expr, "upstream": va, "patched": vb})

    # 7. nth-weekday helper, brute force over the whole supported range
    total += 1
    for year in itertools.chain(range(1970, 2100), (1, 4, 100, 400, 9998, 9999)):
        for month in range(1, 13):
            for dow in range(7):
                a = up.croniter._get_nth_weekday_of_month(year, month, dow)
                b = opt.croniter._get_nth_weekday_of_month(year, month, dow)
                if a != b:
                    record("nth_weekday", {"year": year, "month": month, "dow": dow,
                                           "upstream": a, "patched": b})

    print("comparisons:", total)
    if failures:
        print("FAILURES:", len(failures))
        for kind, detail in failures:
            print("-", kind, detail)
        return 1
    print("no differences found")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - top-level guard, the traceback is the report
        traceback.print_exc()
        sys.exit(2)
