"""Benchmark: upstream croniter vs. the patched implementation.

Design notes (see REPORT.md for the reasoning):
  * one subprocess per workload: running several workloads inside a single
    process lets one workload warm up the interpreter for the next one, which
    is a well-known way to produce meaningless numbers;
  * inside that process the two arms are loaded as two independent modules and
    are interleaved round by round, so a slow machine phase hits both arms;
  * the reported number is the median of the per-round *ratios* (plus the
    ratio of the per-arm minima), never a ratio of two absolute times that were
    sampled at different moments;
  * `--aa` loads the very same file as both arms and therefore measures the
    noise floor of this loop shape on this machine.

Usage:
    python bench.py --upstream upstream/repo/src/croniter/croniter.py \
                    --patched  repo/src/croniter/croniter.py --label ab
    python bench.py --upstream X --patched X --label aa      # noise floor
"""

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime

WORKLOADS = {
    # name: (expression, iterations, start, direction)
    "minutely": ("* * * * *", 20000, (2010, 1, 23, 12, 18), "next"),
    "every5min": ("*/5 * * * *", 20000, (2010, 1, 23, 12, 18), "next"),
    "hourly": ("0 * * * *", 20000, (2010, 1, 23, 12, 18), "next"),
    "daily": ("0 0 * * *", 5000, (2010, 1, 23, 12, 18), "next"),
    "every3hours": ("0 */3 * * *", 10000, (2010, 1, 24, 12, 2), "next"),
    "dom_step": ("0 0 */3 * *", 2000, (2010, 2, 24, 12, 9), "next"),
    "weekday": ("0 0 * * sat", 3000, (2010, 2, 25, 0, 0), "next"),
    "nth_weekday": ("0 0 * * 1#2", 2000, (2010, 1, 25, 0, 0), "next"),
    "nth_weekday_5": ("0 0 * * 5#5", 1500, (2010, 1, 25, 0, 0), "next"),
    "lastday": ("0 0 L * *", 2000, (2010, 1, 25, 0, 0), "next"),
    "nearest_wd": ("0 0 15W * *", 2000, (2010, 1, 25, 0, 0), "next"),
    "prev_minutely": ("* * * * *", 20000, (2010, 8, 25, 15, 56), "prev"),
    "prev_sparse": ("0 0 * * sat,sun", 3000, (2010, 8, 25, 15, 56), "prev"),
    "second_step": ("*/15 * * * * *", 8000, (2010, 1, 23, 12, 18), "next"),
}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def make_runner(mod, workload):
    expr, iters, start, direction = WORKLOADS[workload]
    cls = mod.croniter

    def run():
        it = cls(expr, datetime(*start))
        if direction == "prev":
            last = it.get_prev(datetime)
            for _ in range(iters - 1):
                last = it.get_prev(datetime)
        else:
            last = next(it)
            for _ in range(iters - 1):
                last = next(it)
        return last

    return run


def run_workload(upstream_path, patched_path, workload, rounds, warmup):
    up = load(upstream_path, "croniter_up")
    pt = load(patched_path, "croniter_pt")
    run_up = make_runner(up, workload)
    run_pt = make_runner(pt, workload)

    for _ in range(warmup):
        run_up()
        run_pt()

    up_times, pt_times = [], []
    for rnd in range(rounds):
        # Alternate the order every round so a systematic first/second
        # position effect cancels out instead of being attributed to an arm.
        if rnd % 2 == 0:
            t0 = time.perf_counter()
            run_up()
            t1 = time.perf_counter()
            run_pt()
            t2 = time.perf_counter()
            up_times.append(t1 - t0)
            pt_times.append(t2 - t1)
        else:
            t0 = time.perf_counter()
            run_pt()
            t1 = time.perf_counter()
            run_up()
            t2 = time.perf_counter()
            pt_times.append(t1 - t0)
            up_times.append(t2 - t1)

    ratios = [u / p for u, p in zip(up_times, pt_times)]
    expr, iters, _start, direction = WORKLOADS[workload]
    return {
        "expr": expr,
        "iters": iters,
        "direction": direction,
        "upstream_ms": [round(v * 1e3, 3) for v in up_times],
        "patched_ms": [round(v * 1e3, 3) for v in pt_times],
        "upstream_median_ms": statistics.median(up_times) * 1e3,
        "patched_median_ms": statistics.median(pt_times) * 1e3,
        "upstream_min_ms": min(up_times) * 1e3,
        "patched_min_ms": min(pt_times) * 1e3,
        "ratio_median": statistics.median(ratios),
        "ratio_min": min(ratios),
        "ratio_max": max(ratios),
        "speedup_of_min": min(up_times) / min(pt_times),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--patched", required=True)
    ap.add_argument("--label", default="ab")
    ap.add_argument("--rounds", type=int, default=9)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--workloads", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--child", default="")
    args = ap.parse_args()

    names = [w.strip() for w in args.workloads.split(",") if w.strip()] or list(WORKLOADS)
    root = os.path.dirname(os.path.abspath(__file__))

    if args.child:
        payload = run_workload(
            os.path.abspath(args.upstream),
            os.path.abspath(args.patched),
            args.child,
            args.rounds,
            args.warmup,
        )
        print(json.dumps(payload), flush=True)
        return

    results = {
        "label": args.label,
        "rounds": args.rounds,
        "workloads": {},
        "host": sys.platform,
        "python": sys.version.split()[0],
    }
    for name in names:
        cmd = [
            sys.executable,
            os.path.join(root, "bench.py"),
            "--child",
            name,
            "--upstream",
            args.upstream,
            "--patched",
            args.patched,
            "--rounds",
            str(args.rounds),
            "--warmup",
            str(args.warmup),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace"
        )
        row = json.loads(proc.stdout.strip().splitlines()[-1])
        results["workloads"][name] = row
        print(
            f"{name:<15s} {row['expr']:<20s} {row['upstream_median_ms']:8.1f} -> "
            f"{row['patched_median_ms']:8.1f} ms   ratio {row['ratio_median']:.3f} "
            f"[{row['ratio_min']:.3f}, {row['ratio_max']:.3f}]  "
            f"speedup(min) {row['speedup_of_min']:.3f}",
            flush=True,
        )

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(results, fh, indent=2, ensure_ascii=False)
        print("wrote", args.out)


if __name__ == "__main__":
    main()
