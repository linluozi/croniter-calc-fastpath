"""Attribution: build the two single-change arms and benchmark them.

Isolating which of the two edits is responsible for which speed-up needs
adjacent arms, not just "before" and "after":

    upstream  --(+closed-form weekday)-->  arm1
    upstream  --(+timedelta rewrite)----->  arm2
    upstream  --(+both)------------------>  delivered

Arms are generated from the delivered file by reverting exactly one edit back to
the upstream text, so they cannot drift from the delivered sources.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TARGET = REPO / "src/croniter/croniter.py"
BENCH = REPO / "harness" / "bench.py"

CAL_NEW = """        # Closed form of the former calendar.Calendar(w).monthdayscalendar()
        # construction: the occurrences of a weekday in a month are exactly
        # ``first, first + 7, ...`` up to the last day of that month.
        weekday = (day_of_week + 6) % 7  # cron day-of-week -> datetime weekday
        first = 1 + (weekday - datetime.date(year, month, 1).weekday()) % 7
        return tuple(range(first, _last_day_of_month(year, month) + 1, 7))"""

CAL_OLD = """        w = (day_of_week + 6) % 7
        c = calendar.Calendar(w).monthdayscalendar(year, month)
        if c[0][0] == 0:
            c.pop(0)
        return tuple(i[0] for i in c)"""


def main():
    upstream = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if upstream is None or not upstream.is_file():
        raise SystemExit("usage: attribution.py <upstream croniter.py>")

    patched = TARGET.read_text(encoding="utf-8")
    if CAL_NEW not in patched:
        raise SystemExit("closed-form weekday fragment not found; the file changed")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="attrib-"))
    try:
        # arm2 = delivered minus the closed-form weekday (i.e. timedelta only)
        arm2 = tmp / "arm2_timedelta_only.py"
        arm2.write_text(patched.replace(CAL_NEW, CAL_OLD, 1), encoding="utf-8", newline="\n")

        # arm1 = upstream plus the closed-form weekday (i.e. weekday only)
        up_src = upstream.read_text(encoding="utf-8")
        if CAL_OLD not in up_src:
            raise SystemExit("upstream calendar fragment not found; wrong baseline?")
        arm1 = tmp / "arm1_weekday_only.py"
        arm1.write_text(
            up_src.replace(
                CAL_OLD,
                CAL_NEW.replace(
                    "        # Closed form of the former calendar.Calendar(w).monthdayscalendar()\n"
                    "        # construction: the occurrences of a weekday in a month are exactly\n"
                    "        # ``first, first + 7, ...`` up to the last day of that month.\n",
                    "",
                ),
                1,
            ),
            encoding="utf-8",
            newline="\n",
        )

        workloads = "minutely,daily,weekday,nth_weekday,nth_weekday_5,lastday,nearest_wd"
        for label, cand in (("arm1_weekday_only", arm1), ("arm2_timedelta_only", arm2)):
            print(f"\n=== {label} vs upstream ===", flush=True)
            cmd = [
                sys.executable,
                str(BENCH),
                "--label",
                label,
                "--rounds",
                "9",
                "--workloads",
                workloads,
                "--upstream",
                str(upstream),
                "--patched",
                str(cand),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            print(proc.stdout.rstrip() or proc.stderr.rstrip())
            if proc.returncode != 0:
                return 1

        # sanity: arm1 must be syntactically valid and importable
        for cand in (arm1, arm2):
            snippet = (
                "import importlib.util,sys;"
                f"s=importlib.util.spec_from_file_location('m',r'{cand}');"
                "m=importlib.util.module_from_spec(s);"
                "s.loader.exec_module(m);"
                "print(m.croniter('0 0 * * 1#2').get_next())"
            )
            check = subprocess.run(
                [sys.executable, "-c", snippet], capture_output=True, text=True, check=False
            )
            print(
                f"\nimport check {cand.name}: rc={check.returncode} {check.stdout.strip()}"
                f"{check.stderr.strip()[:200]}"
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
