#!/usr/bin/env python3
"""Offline count-contract tests; no backup, database or server process is invoked."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "infra/scripts/backup-lab.py"
SPEC = importlib.util.spec_from_file_location("backup_lab_count_contract", SOURCE)
assert SPEC is not None and SPEC.loader is not None
BACKUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKUP)


def count_rows(run_count: str, outcome_count: str, metrics: list[str]) -> str:
    return "\n".join([run_count, outcome_count, *metrics]) + "\n"


class DemoCountsTest(unittest.TestCase):
    def reject(self, value) -> None:
        with self.assertRaises(BACKUP.BackupError) as failure:
            BACKUP.validate_demo_counts(value)
        self.assertEqual(str(failure.exception),
                         "Demo counts must contain consistent nonnegative integer totals and per-run metrics.")

    def test_initial_seed_one_run_twelve_outcomes(self):
        BACKUP.validate_demo_counts("1\n12\n12\t7\t3\t2\t0\n")

    def test_ongoing_synthetic_nine_runs_1096_outcomes(self):
        # Matches historical row totals only; these per-run values are synthetic.
        metrics = ["12\t7\t3\t2\t0"] * 8 + ["1000\t900\t50\t25\t25"]
        BACKUP.validate_demo_counts(count_rows("9", "1096", metrics))

    def test_empty_database_counts(self):
        BACKUP.validate_demo_counts("0\n0\n")

    def test_zero_input_run_and_crlf_rows(self):
        BACKUP.validate_demo_counts("1\r\n0\r\n0\t0\t0\t0\t0\r\n")

    def test_missing_or_extra_metric_rows(self):
        for value in (count_rows("2", "12", ["12\t7\t3\t2\t0"]),
                      count_rows("0", "12", ["12\t7\t3\t2\t0"])):
            with self.subTest(value=value):
                self.reject(value)

    def test_missing_headers_and_blank_records(self):
        for value in ("", "1\n", "\n0\n", "0\n0\n\n", "1\n12\n\n12\t7\t3\t2\t0\n"):
            with self.subTest(value=value):
                self.reject(value)

    def test_headers_require_single_integer_field(self):
        self.reject("1\t1\n12\n12\t7\t3\t2\t0\n")
        self.reject("1\n12\t12\n12\t7\t3\t2\t0\n")

    def test_metrics_require_exactly_five_fields(self):
        for row in ("12\t7\t3\t2", "12\t7\t3\t2\t0\t0", "12 7 3 2 0"):
            with self.subTest(row=row):
                self.reject(count_rows("1", "12", [row]))

    def test_negative_headers_and_metrics(self):
        for value in (count_rows("-1", "0", []), count_rows("0", "-1", []),
                      count_rows("1", "12", ["12\t8\t3\t2\t-1"])):
            with self.subTest(value=value):
                self.reject(value)

    def test_noninteger_headers(self):
        for token in ("1.0", "1e0", "NaN", "True", "+1", " 1", "1 ", "١"):
            with self.subTest(token=token):
                self.reject(count_rows(token, "12", ["12\t7\t3\t2\t0"]))

    def test_noninteger_metrics(self):
        for token in ("7.0", "7e0", "NaN", "True", "+7", " 7", "7 ", "٧"):
            with self.subTest(token=token):
                self.reject(count_rows("1", "12", [f"12\t{token}\t3\t2\t0"]))

    def test_per_run_accounting_cannot_cancel_between_runs(self):
        # Aggregate outcomes still equal 24; each run must balance independently.
        self.reject(count_rows("2", "24", ["12\t8\t3\t2\t0", "12\t6\t3\t2\t0"]))

    def test_input_sum_must_match_outcome_total(self):
        self.reject(count_rows("1", "13", ["12\t7\t3\t2\t0"]))

    def test_wrong_input_type_or_private_marker_is_not_echoed(self):
        for value in (None, 12, True, b"0\n0\n", "private-count-marker\n0\n"):
            with self.subTest(value_type=type(value).__name__):
                self.reject(value)


if __name__ == "__main__":
    unittest.main()
