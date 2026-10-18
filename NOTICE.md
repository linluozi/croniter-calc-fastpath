This distribution is a modified copy of croniter
(https://github.com/pallets-eco/croniter), commit
4be99c39c411485e89598a19e8de52a276291c89 ("Bump the github-actions group with
2 updates (#274)", 2026-09-25).

Upstream copyright and licence
------------------------------
croniter is distributed under the MIT licence. The original ``LICENSE`` file is
kept in this distribution **byte for byte** (sha1
``bc4de36b161d5ab5f48981b7c2164507abc1328a``, identical to the upstream git
blob), and all upstream copyright notices are retained in the source files.

Modifications
-------------
Copyright (c) 2026 the contributors of this fork.

Files changed:

  src/croniter/croniter.py                          modified  (performance)
  src/croniter/tests/test_croniter_calc_hotpath.py  added     (tests)
  NOTICE.md                                         added
  DELIVERY.md                                       added
  README-OPTIMIZATION.md                            added
  harness/bench.py                                  added
  harness/diff_equiv.py                             added
  harness/mutation_test.py                          added
  harness/attribution.py                            added
  harness/results_{ab,ba,aa}.json                   added     (benchmark raw data)
  runs/*                                            added     (raw test/bench logs)
  patches/0001-calc-hotpath.patch                   added

**No other source file was touched** — `README.rst`, `pyproject.toml`, the
existing test modules and every other file under `src/croniter/` are
byte-identical to upstream. (Text files were re-normalised from CRLF to LF when
this ZIP was assembled, so that the patch applies cleanly; that changes line
endings, not content.) The public API, the accepted cron dialect and
the observable behaviour of every public entry point are unchanged; see
README-OPTIMIZATION.md and the differential harness in ``harness/`` for the
evidence.

The MIT licence of the upstream project applies to this distribution as a
whole, including the modifications listed above. The modifications are
additionally offered under the same MIT terms.

Third-party runtime dependencies (not bundled)
----------------------------------------------
``python-dateutil`` — Apache License 2.0 / BSD 3-Clause (dual). The optimisation
reduces, but does not remove, the use of this dependency; see the "Known
limitations" section of README-OPTIMIZATION.md.
