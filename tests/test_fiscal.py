"""会計期ヘルパー（fiscal.py）のテスト。"""
from app import fiscal


def test_period_start_year():
    assert fiscal.period_start_year(59) == 2026
    assert fiscal.period_start_year(60) == 2027


def test_months_order():
    ms = fiscal.months(59)
    assert len(ms) == 12
    assert ms[0] == "2026-09"
    assert ms[3] == "2026-12"
    assert ms[4] == "2027-01"
    assert ms[-1] == "2027-08"


def test_quarter_of():
    assert fiscal.quarter_of("2026-09") == 1
    assert fiscal.quarter_of("2026-11") == 1
    assert fiscal.quarter_of("2026-12") == 2
    assert fiscal.quarter_of("2027-02") == 2
    assert fiscal.quarter_of("2027-03") == 3
    assert fiscal.quarter_of("2027-06") == 4
    assert fiscal.quarter_of("2027-08") == 4


def test_half_of():
    assert fiscal.half_of("2026-09") == 1
    assert fiscal.half_of("2027-02") == 1
    assert fiscal.half_of("2027-03") == 2
    assert fiscal.half_of("2027-08") == 2


def test_quarter_and_half_months():
    assert fiscal.quarter_months(1, 59) == ["2026-09", "2026-10", "2026-11"]
    assert fiscal.half_months(2, 59) == ["2027-03", "2027-04", "2027-05",
                                          "2027-06", "2027-07", "2027-08"]


def test_period_of_month():
    assert fiscal.period_of_month("2026-09") == 59
    assert fiscal.period_of_month("2027-08") == 59
    assert fiscal.period_of_month("2026-08") == 58
    assert fiscal.period_of_month("2027-09") == 60


def test_month_label():
    assert fiscal.month_label("2026-09") == "2026/9"
    assert fiscal.month_label("2027-01") == "2027/1"
