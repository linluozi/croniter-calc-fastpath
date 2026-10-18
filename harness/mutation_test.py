"""Mutation testing for the new test file.

Injects one bug at a time into a *copy* of the patched `croniter.py`, runs the
new test module with fail-fast, and reports whether the suite noticed.

Two extra mutants are listed as *behaviourally equivalent*: they change code
that the surrounding control flow overwrites anyway, so no black-box test can
distinguish them. They are excluded from the score rather than counted as gaps.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TARGET = REPO / "src/croniter/croniter.py"
TESTFILE = "src/croniter/tests/test_croniter_calc_hotpath.py"

MUTANTS = {
    # name: (old fragment, new fragment)
    "hour_back_second_zero": (
        """                        d = (d + datetime.timedelta(hours=diff_hour)).replace(
                            minute=59, second=59
                        )""",
        """                        d = (d + datetime.timedelta(hours=diff_hour)).replace(
                            minute=59, second=0
                        )""",
    ),
    "weekday_closed_form_off_by_one": (
        "first = 1 + (weekday - datetime.date(year, month, 1).weekday()) % 7",
        "first = 1 + (weekday - datetime.date(year, month, 1).weekday()) % 7 + 1",
    ),
    "shift_months_no_clamp": (
        "day=min(d.day, _last_day_of_month(year, month))",
        "day=d.day",
    ),
    "minute_back_no_second_reset": (
        "d = (d + datetime.timedelta(minutes=diff_min)).replace(second=59)",
        "d = (d + datetime.timedelta(minutes=diff_min))",
    ),
    "minute_forward_no_second_reset": (
        "d = (d + datetime.timedelta(minutes=diff_min)).replace(second=0)",
        "d = (d + datetime.timedelta(minutes=diff_min))",
    ),
    "day_back_keeps_time_of_day": (
        """d = (d + datetime.timedelta(days=diff_day)).replace(
                            hour=23, minute=59, second=59
                        )""",
        "d = (d + datetime.timedelta(days=diff_day))",
    ),
    "wrong_weekday_conversion": (
        "weekday = (day_of_week + 6) % 7",
        "weekday = day_of_week % 7",
    ),
    "month_forward_hour_6": (
        """                            day=reset_day,
                            hour=0,""",
        """                            day=reset_day,
                            hour=6,""",
    ),
    "hour_forward_minute_30": (
        """                        d = (d + datetime.timedelta(hours=diff_hour)).replace(
                            minute=0, second=0
                        )""",
        """                        d = (d + datetime.timedelta(hours=diff_hour)).replace(
                            minute=30, second=0
                        )""",
    ),
    "day_of_week_back_keeps_time": (
        """                        d = (d + datetime.timedelta(days=diff_day_of_week)).replace(
                            hour=23, minute=59, second=59
                        )""",
        "d = (d + datetime.timedelta(days=diff_day_of_week))",
    ),
}

# Documented as behaviourally equivalent (see README-OPTIMIZATION.md section 4.3)
EQUIVALENT = {
    "year_jump_hour_12": (
        """                                year=d.year + diff_year,
                                month=1,
                                day=1,
                                hour=0,""",
        """                                year=d.year + diff_year,
                                month=1,
                                day=1,
                                hour=12,""",
    ),
}


def run_one(name, old, new, original, workdir):
    if old not in original:
        return None, "PATTERN NOT FOUND"
    target = workdir / "src/croniter/croniter.py"
    target.write_text(original.replace(old, new, 1), encoding="utf-8", newline="\n")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTFILE, "-q", "-x", "-p", "no:cacheprovider"],
        cwd=workdir, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False,
    )
    tail = ""
    for line in proc.stdout.strip().splitlines()[::-1]:
        if "passed" in line or "failed" in line or "error" in line.lower():
            tail = line.strip()
            break
    return proc.returncode != 0, tail


def main():
    original = TARGET.read_text(encoding="utf-8")
    root = pathlib.Path(tempfile.mkdtemp(prefix="mutation-"))
    caught = 0
    try:
        print("=== mutation testing: injected bugs ===")
        for name, (old, new) in MUTANTS.items():
            workdir = root / name
            shutil.copytree(REPO, workdir,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache",
                                                          "*.egg-info", "runs"))
            caught_this, tail = run_one(name, old, new, original, workdir)
            if caught_this is None:
                print(f"{name:34s} SKIPPED ({tail})")
                continue
            caught += caught_this
            print(f"{name:34s} caught={caught_this!s:5s} {tail}")
        total = len(MUTANTS)
        print(f"\ncaught {caught}/{total} non-equivalent mutants")

        print("\n=== mutants documented as behaviourally equivalent ===")
        for name, (old, new) in EQUIVALENT.items():
            workdir = root / name
            shutil.copytree(REPO, workdir,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache",
                                                          "*.egg-info", "runs"))
            caught_this, tail = run_one(name, old, new, original, workdir)
            print(f"{name:34s} caught={caught_this} (expected False)  {tail}")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
