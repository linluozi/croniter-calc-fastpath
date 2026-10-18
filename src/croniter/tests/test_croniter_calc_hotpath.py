"""Regression tests for the `_calc` hot-path rewrite.

The optimisation replaces, inside :meth:`croniter._calc`, every
``datetime + relativedelta(...)`` step with plain ``datetime.timedelta``
arithmetic (plus ``replace()`` for the absolute time-of-day parts), and
computes the weekday occurrences of a month in closed form instead of
building a ``calendar.Calendar(...).monthdayscalendar()`` matrix.

These tests pin down the two properties that matter:

* behaviour is unchanged (sequence snapshots, sub-minute cursor handling, the
  ``*`` seconds-field backwards path, and an exhaustive comparison of the
  closed-form weekday formula against the old ``calendar`` construction), and
* the optimisation is actually still in place.  The latter is asserted with a
  *deterministic* counter (how many ``relativedelta`` objects `_calc` builds)
  rather than with wall-clock time, so the test cannot flake on a busy machine.

Every expected value below was taken from the *unmodified* upstream
implementation, not derived from the cron semantics by hand.
"""

import calendar
import datetime
import unittest
from unittest import mock

import croniter as croniter_pkg
from croniter import croniter

cron_m = croniter_pkg.cron_m


def _calendar_reference(year, month, day_of_week):
    """The pre-optimisation implementation, kept verbatim as an oracle."""
    c = calendar.Calendar((day_of_week + 6) % 7).monthdayscalendar(year, month)
    if c[0][0] == 0:
        c.pop(0)
    return tuple(i[0] for i in c)


class ClosedFormWeekdayTest(unittest.TestCase):
    """`_get_nth_weekday_of_month` must equal the old calendar-based result."""

    def test_matches_calendar_construction_over_supported_range(self):
        checked = 0
        for year in range(1970, 2100):
            for month in range(1, 13):
                for day_of_week in range(7):
                    self.assertEqual(
                        croniter._get_nth_weekday_of_month(year, month, day_of_week),
                        _calendar_reference(year, month, day_of_week),
                        (year, month, day_of_week),
                    )
                    checked += 1
        self.assertEqual(checked, 130 * 12 * 7)

    def test_matches_calendar_construction_on_edge_years(self):
        # Year 1, leap-century boundaries and the top of the supported range.
        for year in (1, 4, 100, 400, 1900, 2000, 2100, 9998, 9999):
            for month in range(1, 13):
                for day_of_week in range(7):
                    self.assertEqual(
                        croniter._get_nth_weekday_of_month(year, month, day_of_week),
                        _calendar_reference(year, month, day_of_week),
                        (year, month, day_of_week),
                    )

    def test_returns_progression_by_seven(self):
        # Structural assertion: the returned days are always first, first+7, ...
        for month in range(1, 13):
            for day_of_week in range(7):
                days = croniter._get_nth_weekday_of_month(2024, month, day_of_week)
                self.assertEqual(list(days), list(range(days[0], days[-1] + 1, 7)))
                self.assertTrue(1 <= days[0] <= 7, days)
                self.assertLessEqual(days[-1], 31, days)


class NoRelativedeltaInCalcTest(unittest.TestCase):
    """`_calc` must not build `relativedelta` objects any more.

    Counting constructor calls is deterministic: it does not depend on how
    loaded the machine is, unlike a timing assertion.
    """

    def _count_relativedelta(self, expr, iterations, start, backwards=False):
        calls = []
        original = cron_m.relativedelta

        def counting(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        it = croniter(expr, start, ret_type=datetime.datetime)
        with mock.patch.object(cron_m, "relativedelta", side_effect=counting):
            for _ in range(iterations):
                if backwards:
                    it.get_prev(datetime.datetime)
                else:
                    next(it)
        return len(calls)

    def test_forward_minutely_builds_none(self):
        self.assertEqual(
            self._count_relativedelta("* * * * *", 500, datetime.datetime(2024, 1, 1)), 0
        )

    def test_forward_daily_builds_none(self):
        self.assertEqual(
            self._count_relativedelta("0 0 * * *", 200, datetime.datetime(2024, 1, 1)), 0
        )

    def test_backward_builds_none(self):
        self.assertEqual(
            self._count_relativedelta(
                "* * * * *", 500, datetime.datetime(2024, 6, 1, 12, 0), backwards=True
            ),
            0,
        )

    def test_nth_weekday_and_last_day_build_none(self):
        for expr in ("0 0 * * 1#2", "0 0 * * 5#5", "0 0 L * *", "0 0 15W * *"):
            with self.subTest(expr=expr):
                self.assertEqual(
                    self._count_relativedelta(expr, 100, datetime.datetime(2024, 1, 1)), 0
                )

    def test_second_resolution_builds_none(self):
        for expr in ("0 0 1 * * 30", "30 0 0 1 * *", "0 15 */2 * * *"):
            with self.subTest(expr=expr):
                self.assertEqual(
                    self._count_relativedelta(expr, 50, datetime.datetime(2024, 1, 1)), 0
                )

    def test_leap_day_expression_builds_none(self):
        self.assertEqual(
            self._count_relativedelta("0 0 29 2 * 0 2024", 1, datetime.datetime(2024, 1, 1)), 0
        )

    def test_year_field_builds_none(self):
        self.assertEqual(
            self._count_relativedelta(
                "0 0 31 1-2 * 0 2023-2025", 1, datetime.datetime(2024, 12, 30)
            ),
            0,
        )


class TimeOfDayResetTest(unittest.TestCase):
    """The `replace()`-based rewrites must reset exactly what relativedelta did."""

    def test_second_level_iteration_clears_microseconds(self):
        it = croniter("* * * * * *", datetime.datetime(2024, 1, 1, 0, 0, 0, 123456))
        nxt = it.get_next(datetime.datetime)
        self.assertEqual(nxt, datetime.datetime(2024, 1, 1, 0, 0, 1))
        self.assertEqual(nxt.microsecond, 0)

    def test_forward_minute_jump_resets_seconds_to_zero(self):
        # Forward jumps inside a second-resolution expression must zero the
        # seconds, i.e. the rewrite has to keep `replace(second=0)`.
        it = croniter("*/15 * * * * *", datetime.datetime(2024, 12, 31, 23, 59, 30))
        self.assertEqual(it.get_next(datetime.datetime), datetime.datetime(2025, 1, 1, 0, 0))
        self.assertEqual(it.get_next(datetime.datetime), datetime.datetime(2025, 1, 1, 0, 0, 1))

    def test_minute_level_iteration_drops_seconds_and_microseconds(self):
        it = croniter("*/5 * * * *", datetime.datetime(2024, 1, 1, 0, 0, 30, 500000))
        nxt = it.get_next(datetime.datetime)
        self.assertEqual(nxt, datetime.datetime(2024, 1, 1, 0, 5))
        self.assertEqual((nxt.second, nxt.microsecond), (0, 0))

    def test_prev_on_hour_boundary_keeps_minute_level_granularity(self):
        it = croniter("0 * * * *", datetime.datetime(2024, 6, 1, 12, 0))
        self.assertEqual(it.get_prev(datetime.datetime), datetime.datetime(2024, 6, 1, 11, 0))

    def test_star_seconds_keep_sub_minute_offset_when_going_backwards(self):
        # Regression guard: with `*` in the seconds field the cursor keeps its
        # sub-minute part, so an hour jump backwards must land on :59:59 and
        # keep counting down second by second.
        it = croniter("* 0 0,12 * * *", datetime.datetime(2024, 1, 1, 13, 18, 9))
        seq = [it.get_prev(datetime.datetime) for _ in range(3)]
        self.assertEqual(
            seq,
            [
                datetime.datetime(2024, 1, 1, 0, 59, 59),
                datetime.datetime(2024, 1, 1, 0, 59, 58),
                datetime.datetime(2024, 1, 1, 0, 59, 57),
            ],
        )


class MonthClampAndSecondCursorTest(unittest.TestCase):
    """Cases that only a specific shape of the rewrite can get wrong."""

    def test_impossible_month_day_fails_with_the_same_exception_type(self):
        # `_shift_months` must clamp the day of month while shifting, otherwise
        # `d.replace(day=31)` raises ValueError instead of the documented
        # CroniterBadDateError once the walk has to give up.
        it = croniter("0 0 30 2 *", datetime.datetime(2010, 1, 23, 12, 18))
        with self.assertRaises(croniter_pkg.CroniterBadDateError):
            it.get_prev(datetime.datetime)

    def test_backwards_minute_jump_resets_seconds(self):
        # proc_minute must reset the seconds field when jumping backwards,
        # even when the seconds field itself is `*`.
        it = croniter("*/15 * * * * *", datetime.datetime(2024, 12, 31, 23, 59, 30))
        prev = it.get_prev(datetime.datetime)
        self.assertEqual(prev, datetime.datetime(2024, 12, 31, 23, 45, 59))

    def test_backwards_day_jump_resets_the_time_of_day(self):
        # proc_day_of_month / proc_day_of_week must jump to 23:59:59 of the
        # previous matching day, not keep the time of day the walk started at.
        it = croniter("* * 5,17 * * *", datetime.datetime(2010, 1, 23, 12, 18))
        prev = it.get_prev(datetime.datetime)
        self.assertEqual(prev, datetime.datetime(2010, 1, 17, 23, 59, 59))


class SequenceSnapshotTest(unittest.TestCase):
    """Frozen expectations for calendar-boundary walks (behaviour must not drift)."""

    def walk(self, expr, start, count, backwards=False):
        it = croniter(expr, start, ret_type=datetime.datetime)
        out = []
        for _ in range(count):
            out.append(it.get_prev(datetime.datetime) if backwards else next(it))
        return out

    def test_last_day_of_month_across_leap_year(self):
        self.assertEqual(
            self.walk("0 0 L * *", datetime.datetime(2024, 1, 1), 4),
            [
                datetime.datetime(2024, 1, 31),
                datetime.datetime(2024, 2, 29),
                datetime.datetime(2024, 3, 31),
                datetime.datetime(2024, 4, 30),
            ],
        )

    def test_year_rollover(self):
        self.assertEqual(
            self.walk("59 23 31 12 *", datetime.datetime(2024, 1, 1), 2),
            [datetime.datetime(2024, 12, 31, 23, 59), datetime.datetime(2025, 12, 31, 23, 59)],
        )

    def test_month_shift_clamps_day(self):
        # Starting on the 31st and asking for the previous month must clamp to
        # the last existing day instead of raising.
        self.assertEqual(
            self.walk("0 0 31 * *", datetime.datetime(2024, 5, 31), 4, backwards=True),
            [
                datetime.datetime(2024, 3, 31),
                datetime.datetime(2024, 1, 31),
                datetime.datetime(2023, 12, 31),
                datetime.datetime(2023, 10, 31),
            ],
        )

    def test_fifth_weekday_skips_months_without_one(self):
        self.assertEqual(
            self.walk("0 0 * * 5#5", datetime.datetime(2024, 1, 1), 4),
            [
                datetime.datetime(2024, 3, 29),
                datetime.datetime(2024, 5, 31),
                datetime.datetime(2024, 8, 30),
                datetime.datetime(2024, 11, 29),
            ],
        )

    def test_nearest_weekday_never_lands_on_a_weekend(self):
        seq = self.walk("0 0 15W * *", datetime.datetime(2024, 1, 1), 7)
        for moment in seq:
            self.assertLess(moment.weekday(), 5, moment)
        self.assertEqual(seq[0], datetime.datetime(2024, 1, 15))
        self.assertEqual(seq[5], datetime.datetime(2024, 6, 14))  # 15 Jun 2024 is a Saturday

    def test_month_jump_resets_time_of_day(self):
        # A forward month jump with a day-of-week restriction must start the
        # new month at 00:00, otherwise the first candidate of the month can be
        # skipped (2010-02-01 is a Monday).
        self.assertEqual(
            self.walk("0 0 29 2 1", datetime.datetime(2010, 1, 23, 12, 18), 1),
            [datetime.datetime(2010, 2, 1)],
        )

    def test_year_field_walk(self):
        self.assertEqual(
            # `2025-02` has no 31st, so the walk legitimately ends after one step;
            # the year field is covered here, the multi-step path elsewhere.
            self.walk("0 0 31 1-2 * 0 2023-2025", datetime.datetime(2024, 12, 30), 1),
            [datetime.datetime(2025, 1, 31)],
        )


if __name__ == "__main__":
    unittest.main()
