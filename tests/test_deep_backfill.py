import datetime
from unittest.mock import patch
from chip_data_manager import ChipDataManager

def test_deep_backfill_requests_full_range_once():
    mgr = ChipDataManager(db_name=":memory:")
    calls = []
    def fake_fetch(symbol, start_date, end_date):
        calls.append((symbol, start_date, end_date))
        return {}  # no rows; exercises range logic only
    with patch.object(mgr, "_fetch_finmind_chip", side_effect=fake_fetch):
        mgr.deep_backfill("2330", start_date="2020-01-01")
    assert len(calls) == 1, "deep_backfill must be ONE FinMind request per symbol"
    sym, s, e = calls[0]
    assert sym == "2330" and s == "2020-01-01"
    assert e >= datetime.date.today().isoformat()
