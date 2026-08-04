"""Tests for the Data Loader module (AI Trading Brain v1, Phase 2)."""

import os
import tempfile
import unittest

from trading_brain.data_loader import load_candles_from_csv


def write_csv(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    f.write(content)
    f.close()
    return f.name


class TestLoadCandlesFromCsv(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            os.unlink(p)

    def _load(self, content, **kwargs):
        path = write_csv(content)
        self._paths.append(path)
        return load_candles_from_csv(path, **kwargs)

    def test_basic_header_parsing(self):
        candles = self._load(
            "Date,Open,High,Low,Close\n"
            "2024-01-02,1.09,1.096,1.089,1.095\n"
        )
        self.assertEqual(len(candles), 1)
        c = candles[0]
        self.assertEqual((c.open, c.high, c.low, c.close), (1.09, 1.096, 1.089, 1.095))
        self.assertEqual(c.timestamp.year, 2024)

    def test_rows_sorted_ascending_regardless_of_file_order(self):
        candles = self._load(
            "Date,Open,High,Low,Close\n"
            "2024-01-03,1,1,1,1\n"
            "2024-01-02,2,2,2,2\n"
            "2024-01-04,3,3,3,3\n"
        )
        self.assertEqual([c.timestamp.day for c in candles], [2, 3, 4])

    def test_reindexed_zero_based_and_contiguous(self):
        candles = self._load(
            "Date,Open,High,Low,Close\n"
            "2024-01-03,1,1,1,1\n"
            "2024-01-02,2,2,2,2\n"
        )
        self.assertEqual([c.index for c in candles], [0, 1])

    def test_case_insensitive_and_reordered_headers(self):
        candles = self._load(
            "CLOSE,LOW,HIGH,OPEN,DATE\n"
            "1.095,1.089,1.096,1.09,2024-01-02\n"
        )
        c = candles[0]
        self.assertEqual((c.open, c.high, c.low, c.close), (1.09, 1.096, 1.089, 1.095))

    def test_time_header_maps_to_timestamp(self):
        candles = self._load(
            "time,open,high,low,close\n"
            "2024-01-02 09:30:00,1.09,1.096,1.089,1.095\n"
        )
        self.assertEqual(candles[0].timestamp.hour, 9)
        self.assertEqual(candles[0].timestamp.minute, 30)

    def test_dot_separated_date_format(self):
        candles = self._load(
            "date,open,high,low,close\n"
            "2024.01.02 09:30:00,1.09,1.096,1.089,1.095\n"
        )
        self.assertEqual(candles[0].timestamp.month, 1)

    def test_missing_required_column_raises(self):
        with self.assertRaises(ValueError):
            self._load("Date,Open,High,Close\n2024-01-02,1,1,1\n")

    def test_blank_lines_are_skipped(self):
        candles = self._load(
            "Date,Open,High,Low,Close\n"
            "2024-01-02,1,1,1,1\n"
            "\n"
            "2024-01-03,2,2,2,2\n"
        )
        self.assertEqual(len(candles), 2)

    def test_empty_file_returns_empty_list(self):
        candles = self._load("")
        self.assertEqual(candles, [])

    def test_no_header_mode_assumes_fixed_column_order(self):
        candles = self._load(
            "2024-01-02,1.09,1.096,1.089,1.095\n"
            "2024-01-03,1.095,1.098,1.093,1.096\n",
            has_header=False,
        )
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].open, 1.09)
        self.assertEqual(candles[1].close, 1.096)

    def test_unparseable_timestamp_sorts_last_not_first(self):
        # A row with a timestamp format the loader doesn't recognize must not
        # silently jump to the front of a walk-forward series -- that would
        # be look-ahead by construction for every module downstream.
        candles = self._load(
            "Date,Open,High,Low,Close\n"
            "2024-01-02,1,1,1,1\n"
            "not-a-date,2,2,2,2\n"
            "2024-01-03,3,3,3,3\n"
        )
        self.assertEqual([c.open for c in candles], [1, 3, 2])
        self.assertIsNone(candles[-1].timestamp)


if __name__ == "__main__":
    unittest.main()
