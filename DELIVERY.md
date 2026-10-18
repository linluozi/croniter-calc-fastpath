# croniter — `_calc` hot-path optimisation

This ZIP contains a **modified copy** of [`pallets-eco/croniter`](https://github.com/pallets-eco/croniter),
an open-source cron-expression iterator for Python that is in active use (it is
the scheduler engine behind Celery Beat, Prefect and many cron-as-a-service
tools).

* **Upstream:** https://github.com/pallets-eco/croniter
* **Baseline commit:** `4be99c39c411485e89598a19e8de52a276291c89` (2026-09-25, `master`)
* **Licence:** MIT — the upstream `LICENSE` is kept **byte for byte**; see `NOTICE.md`
* **Version string in this tree:** `6.3.0.dev0` (as upstream declares it)

## What is inside

```
croniter-6.3.0.dev0-calc-hotpath-opt/
├── README-OPTIMIZATION.md      <- the full write-up (problem, change, evidence, limits)
├── NOTICE.md                   <- what was modified, licensing
├── DELIVERY.md                 <- this file
├── LICENSE                     <- upstream MIT licence, byte-identical
├── src/croniter/croniter.py    <- MODIFIED (the optimisation)
├── src/croniter/tests/
│   └── test_croniter_calc_hotpath.py   <- ADDED (25 tests)
├── harness/
│   ├── bench.py                <- the benchmark used for every number in the report
│   ├── diff_equiv.py           <- differential equivalence harness (209,815 comparisons)
│   ├── attribution.py          <- rebuilds the two single-change arms and benchmarks them
│   ├── mutation_test.py        <- injects 10 bugs, checks the new tests catch them
│   ├── results_ab.json         <- forward run, 9 rounds per workload
│   ├── results_ba.json         <- reverse run (arms swapped), 9 rounds
│   └── results_aa.json         <- A/A noise floor (same file as both arms)
├── runs/
│   ├── baseline_tests.txt      <- full `pytest` output, unmodified upstream
│   ├── patched_tests.txt       <- full `pytest` output, patched
│   ├── baseline_nonposix_tests.txt  <- excluding the POSIX-only DST file
│   ├── patched_nonposix_tests.txt
│   ├── diff_equiv.txt          <- "no differences found"
│   ├── mutation_testing.txt    <- 10 injected bugs, 10 caught
│   ├── attribution_arms.txt    <- single-change arms
│   ├── bench_baseline_vs_patched.txt
│   ├── bench_reverse_order.txt
│   ├── bench_aa_noisefloor.txt
│   └── rollup.md               <- one-page summary of the numbers
└── patches/
    └── 0001-calc-hotpath.patch <- applies with `patch -p1 --binary`, reproduces the
                                   delivered file byte for byte (verified with `cmp`)


## The short version

`croniter._calc` moved its cursor with `dateutil.relativedelta` on every field
step — ~4.4–6.0 µs per move against ~0.68 µs for the equivalent native
`datetime` arithmetic — and `_get_nth_weekday_of_month` built an entire
`calendar.Calendar(...).monthdayscalendar()` grid on every candidate day just
to answer "which days are Mondays?".

Both are replaced with native `datetime` / closed-form arithmetic. Behaviour is
unchanged: **209,815 differential comparisons against pristine upstream report
zero differences**, the existing test suite is unchanged, and 25 new tests
(including deterministic "the optimisation is still there" assertions) run
green. Ten injected bugs were all caught.

Measured speed-ups (median of per-round ratios, 9 rounds, forward and reverse
runs agreeing within 0.0–8.3 %; A/A noise floor on this machine 0.866–1.060
per workload median, 0.586–1.814 per single round):

| expression | speed-up |
|---|---:|
| `* * * * *` (forward / backward) | 3.26× / 3.14× |
| `*/5 * * * *` | 2.65× |
| `0 * * * *` | 2.79× |
| `0 0 * * *` | 2.54× |
| `0 0 * * 1#2` | 3.39× |
| `0 0 * * 5#5` | 3.72× |
| `0 0 L * *` | 2.47× |
| `*/15 * * * * *` (second resolution) | 1.87× |

Absolute milliseconds are machine-specific; only the ratios should be quoted
elsewhere. `README-OPTIMIZATION.md` §3.2 breaks the gain down by which of the
two changes is responsible — the closed-form weekday lookup contributes
**nothing** on ordinary expressions and 1.50× on `#n` schedules, while the
`timedelta` rewrite is worth 2.3–3.1× nearly everywhere.

## Running it

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e . pytest pytz tzdata

python -m pytest src/croniter/tests -q           # 269 passed, 99 subtests
python harness/diff_equiv.py <upstream croniter.py> src/croniter/croniter.py
python harness/bench.py --label ab --rounds 9 \
    --upstream <upstream croniter.py> --patched src/croniter/croniter.py
```

On Windows, `src/croniter/tests/test_croniter_dst_repetition.py` cannot run: it
calls `time.tzset()`, which POSIX-only. That is upstream behaviour (identical
failure set before and after the patch), not a regression. Those 8 tests were
**not** executed in this environment.

## Known limitations

See `README-OPTIMIZATION.md` §6. The headline ones: the DST-repetition tests
could not be run on Windows; timings come from a single machine; `python-dateutil`
is still required by `croniter_range` and the DST helpers; and no upstream pull
request was opened — this is a fork plus a patch, not an accepted change.
