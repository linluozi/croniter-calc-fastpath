# One-page rollup

| item | value |
|---|---|
| Upstream | `pallets-eco/croniter` |
| Baseline commit | `4be99c39c411485e89598a19e8de52a276291c89` (2026-09-25) |
| `croniter.py` sha1, upstream | `011b243bd67f8010802075d5088aaea38e216676` |
| `croniter.py` sha1, patched | `9df537e80091edc1229c81e2d90a4e6688d3062f` |
| Licence | MIT, `LICENSE` byte-identical to upstream (sha1 `bc4de36b…`) |
| Other upstream files | 29 files byte-identical (after CRLF→LF normalisation) |
| Patch reproduces the file | yes, verified with `patch -p1 --binary` + `cmp` |

## Tests

| suite | upstream | patched |
|---|---|---|
| full (`src/croniter/tests`) | 4 failed, 244 passed, 4 errors, 92 subtests | 4 failed, 269 passed, 4 errors, 99 subtests |
| excluding POSIX-only `test_croniter_dst_repetition.py` | 244 passed, 92 subtests | **269 passed, 99 subtests** |

The 8 non-passing cases are identical before and after, and all come from
`time.tzset()` being POSIX-only. They were **not** executed on Linux here.

## Equivalence

| check | result |
|---|---|
| differential harness, upstream vs patched | 209,815 comparisons, **0 differences** |
| harness validated against mutants | catches 10/10 non-equivalent, silent on the 1 equivalent |
| new tests vs 10 injected bugs | **10/10 caught** |
| `ruff check croniter.py` | 28 findings both before and after (pre-existing) |
| `ruff check` on the new test file | clean |

## Performance (median of per-round ratios, 9 rounds)

| expression | speed-up | reverse-order run |
|---|---:|---:|
| `* * * * *` next | 3.26× | 3.11× |
| `* * * * *` prev | 3.14× | 3.04× |
| `*/5 * * * *` | 2.65× | 2.43× |
| `0 * * * *` | 2.79× | 2.78× |
| `0 0 * * *` | 2.54× | 2.61× |
| `0 0 * * 1#2` | 3.39× | 3.60× |
| `0 0 * * 5#5` | 3.72× | 3.76× |
| `0 0 L * *` | 2.47× | 2.40× |
| `0 0 15W * *` | 2.38× | 2.40× |
| `*/15 * * * * *` | 1.87× | 1.87× |

A/A noise floor (same file as both arms): per-workload medians **0.866–1.060**,
single rounds **0.586–1.814** (n=126). Smallest measured effect 1.87× is
outside that band.

## Which change does what

| workload | + closed-form weekday | + `timedelta` only | both |
|---|---:|---:|---:|
| `* * * * *` | 1.01× | 3.12× | 3.26× |
| `0 0 * * *` | 0.97× | 2.59× | 2.54× |
| `0 0 * * 1#2` | **1.54×** | 1.74× | 3.39× |
| `0 0 * * 5#5` | **1.45×** | 1.74× | 3.72× |
| `0 0 L * *` | 0.98× | 2.50× | 2.47× |
| `0 0 15W * *` | 1.00× | 2.41× | 2.38× |

The closed-form weekday lookup pays off only on `#n` schedules; the
`timedelta` rewrite carries the rest.

## Files

```
src/croniter/croniter.py                            modified
src/croniter/tests/test_croniter_calc_hotpath.py    added   (25 tests)
harness/bench.py  diff_equiv.py  attribution.py  mutation_test.py
harness/results_ab.json  results_ba.json  results_aa.json
runs/*.txt                                          raw logs
patches/0001-calc-hotpath.patch
NOTICE.md  DELIVERY.md  README-OPTIMIZATION.md
```
