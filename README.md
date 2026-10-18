# croniter-calc-fastpath

[![CI/CD](https://github.com/linluozi/croniter-calc-fastpath/actions/workflows/cicd.yml/badge.svg)](https://github.com/linluozi/croniter-calc-fastpath/actions/workflows/cicd.yml)

A performance patch for [`croniter`](https://github.com/pallets-eco/croniter) — the cron
expression iterator that drives Celery Beat, Prefect and a large share of the
cron-as-a-service tooling in the Python ecosystem.

`get_next()` / `get_prev()` walk a cursor to the next matching instant by moving it one
field at a time. In upstream `croniter` every one of those moves builds a
`dateutil.relativedelta.relativedelta`; this fork replaces that with native `datetime`
arithmetic and replaces one calendar-grid lookup with a closed form.

**Result: 1.87×–3.76× faster iteration, no observable behaviour change.**

| | |
|---|---|
| Upstream | https://github.com/pallets-eco/croniter |
| Baseline commit | `4be99c39c411485e89598a19e8de52a276291c89` (2026-09-25, `master`, `6.3.0.dev0`) |
| Licence | MIT, upstream `LICENSE` kept byte for byte |
| Changed | `src/croniter/croniter.py` (the only source file) + 25 new tests + harness; 30 other upstream files verified byte-identical |
| Behaviour | unchanged — 209,815 differential comparisons against pristine upstream, 0 differences |
| Tests | 273 passed on Linux × 6 environments (3.9–3.13 + i386), zero failures |

![Per-workload speed-up](docs/figures/speedup.png)

Bars are the forward run (upstream vs patched), diamonds are the reverse run with the two
arms swapped. They agree within 0–8.3 %, so the effect is not an artefact of load order.

## The two changes

**1. `relativedelta` → `datetime` arithmetic in `_calc`**

```python
# before
d += relativedelta(days=diff_day, hour=23, minute=59, second=59)
# after
d = (d + datetime.timedelta(days=diff_day)).replace(hour=23, minute=59, second=59)
```

Each step is a *relative* offset plus an *absolute* replacement of the time-of-day, which
`datetime` already does natively. Measured on this machine:

```
relativedelta(minutes=3, second=59)             5996 ns
replace(second=59) + timedelta(minutes=3)        678 ns
relativedelta(hours=-2, minute=59, second=59)   4386 ns
replace(minute=59, second=59) + timedelta(-2h)   687 ns
```

Calendar months cannot be expressed as a fixed `timedelta`, so `_shift_months()` handles
them, clamping the day of month exactly the way `relativedelta` does.

**2. Month-grid weekday lookup → closed form**

`_get_nth_weekday_of_month` used to materialise an entire
`calendar.Calendar(w).monthdayscalendar()` grid for every candidate day just to answer
"which days of this month are Mondays?". The occurrences of a weekday in a month are always
`first, first+7, first+14, …`, so it is now two lines. Verified against the old
implementation for **all 839,832 (year, month, weekday) triples in 1..9998** — zero
mismatches.

## Which change does what

![Attribution of each change](docs/figures/attribution.png)

This is the part most "sped up by 3×" write-ups skip. Measured with two extra arms, each
applying exactly one of the two edits on top of pristine upstream:

* On ordinary expressions (`* * * * *`, `0 0 * * *`) the closed-form weekday lookup is
  worth **nothing** (0.97–1.01×, inside the noise band) and `timedelta` is worth 2.5–3.1×.
* On `#n` schedules the closed-form lookup is worth **1.45–1.54×** on its own, and the two
  compose super-multiplicatively (1.54 × 1.74 = 2.7 against a measured 3.39).
* On `L` and `W` the closed-form lookup is worth **nothing**: `L` is answered by an early
  `return` before the weekday path is reached, and `W` goes through `_get_nearest_weekday`,
  which still calls `calendar.weekday`.

## Is the speed-up real?

![Effect size against the noise floor](docs/figures/noise-floor.png)

The grey band is the **A/A noise floor**: the same file loaded as both arms, measured with
the identical loop. Per-workload medians land in 0.866–1.060, single rounds span
0.586–1.814 (n = 126). The smallest real effect reported here is 1.87×. The bands do not
overlap for any workload.

## Is it still correct?

Four independent checks, all reproducible from `harness/`:

| check | result |
|---|---|
| Upstream CI workflow, 7 jobs | **all green** — 273 passed on 3.9/3.10/3.11/3.12/3.13/i386, plus `ruff check` + `mypy` + `ruff format` |
| `diff_equiv.py` — differential harness vs pristine upstream | **209,815 comparisons, 0 differences** |
| `mutation_test.py` — 10 bugs injected into the patched file | **10/10 caught** by the new tests |
| `ruff check` | 28 findings before *and* after in `croniter.py` (pre-existing); new test file clean |

The differential harness covers forward/backward walks over 43 expressions × 15 start dates
× 2 return types, second-resolution expressions, five timezones across DST transitions,
`croniter_range`, `match()`, and `expand()`/`is_valid()` over 1,240 generated expressions.

One mutant (`year` jump with `hour=12` instead of `hour=0`) is **behaviourally equivalent** —
the following field processors reset the time of day anyway — so no black-box test can
distinguish it. That is documented rather than counted as a coverage gap.

## Known limitations

1. **The Windows development run cannot execute the 8 DST-repetition tests** (`time.tzset()`
   is POSIX-only). They were executed on Linux via the upstream CI workflow and all passed;
   on Windows their failure set is merely identical before and after the patch.
2. **Timings come from one machine** (Windows, CPython 3.13.12). Absolute milliseconds are
   not portable; only the ratios are.
3. **`python-dateutil` is not removed.** `croniter_range`, the timestamp helpers and the DST
   machinery still use it. The change is confined to `_calc`.
4. **No upstream PR was opened.** This is a fork plus a patch file, not an accepted change.
5. On Windows, applying `patches/0001-calc-hotpath.patch` needs `patch -p1 --binary`, because
   the default strips trailing CRs and silently corrupts the result.

## Repository layout

```
src/croniter/croniter.py                          the only modified source file
src/croniter/tests/test_croniter_calc_hotpath.py  25 new tests
harness/bench.py                                  benchmark (forward / reverse / A/A)
harness/diff_equiv.py                             differential equivalence harness
harness/mutation_test.py                          10 injected bugs, 10 must be caught
harness/attribution.py                            rebuilds the two single-change arms
harness/make_figures.py                           regenerates every figure from the JSON
harness/results_{ab,ba,aa}.json                   raw per-round samples
runs/                                             full pytest / bench / mutation logs
patches/0001-calc-hotpath.patch                   applies with `patch -p1 --binary`
README-OPTIMIZATION.md                            the full write-up
NOTICE.md                                         what changed, licensing
docs/figures/                                     the three figures above
```

## Reproduce

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e . pytest pytz tzdata

python -m pytest src/croniter/tests -q

# needs a pristine upstream checkout at 4be99c39c4
python harness/diff_equiv.py <upstream>/src/croniter/croniter.py src/croniter/croniter.py

python harness/bench.py --label ab --rounds 9 --out harness/results_ab.json \
    --upstream <upstream>/src/croniter/croniter.py --patched src/croniter/croniter.py
python harness/bench.py --label ba --rounds 9 --out harness/results_ba.json \
    --upstream src/croniter/croniter.py --patched <upstream>/src/croniter/croniter.py
python harness/bench.py --label aa --rounds 9 --out harness/results_aa.json \
    --upstream <upstream>/src/croniter/croniter.py --patched <upstream>/src/croniter/croniter.py
```

## Licence

MIT, inherited from upstream. `LICENSE` is byte-identical to the upstream file
(sha1 `bc4de36b…`); all upstream copyright notices are retained. See
[NOTICE.md](NOTICE.md) for the modification statement. Upstream project:
<https://github.com/pallets-eco/croniter>.
