"""指数成分缓存（index_members）测试：不联网，用假 pro 覆盖抓取→落盘→解析。"""

import pandas as pd

from alphaagent.data import index_members as im


class _FakePro:
    """按月返回固定成分快照的假 Tushare pro。"""

    def __init__(self, per_month: dict[str, list[str]]):
        self.per_month = per_month
        self.calls: list[str] = []

    def index_weight(self, index_code, start_date, end_date):
        self.calls.append(start_date)
        cons = self.per_month.get(start_date, [])
        return pd.DataFrame({"index_code": index_code, "con_code": cons, "trade_date": start_date})


def test_index_members_path():
    assert im.index_members_path("zz1000").name == "000852_SH_members.parquet"


def test_members_union_and_covers():
    cache = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2020-01-31", "2020-02-29", "2021-06-30"]),
            "instrument": ["a.SZ", "b.SZ", "c.SZ"],
        }
    )
    assert im.members_union(cache, "2020-01-01", "2020-12-31") == ["a.SZ", "b.SZ"]
    assert im.members_union(cache, "2019-01-01", "2019-12-31") == []
    assert im._cache_covers(cache, "2020-02-01", "2020-02-15")
    assert not im._cache_covers(cache, "2019-01-01", "2019-06-30")


def test_merge_and_append(tmp_path):
    path = tmp_path / "idx.parquet"
    a = pd.DataFrame({"trade_date": pd.to_datetime(["2020-01-31"]), "instrument": ["a.SZ"]})
    im.save_index_members(a, path=path)
    im.append_snapshot("zz1000", "2020-02-29", ["b.SZ", "a.SZ"], path=path)
    got = im.load_index_members(path=path)
    assert len(got) == 3
    assert set(got["instrument"]) == {"a.SZ", "b.SZ"}


def test_resolve_cached_fetches_then_reuses(tmp_path):
    path = tmp_path / "idx.parquet"
    pro = _FakePro(
        {
            "20200131": ["a.SZ", "b.SZ"],
            "20200229": ["b.SZ", "c.SZ"],
        }
    )
    members = im.resolve_index_members_cached(
        "zz1000", "2020-01-01", "2020-02-29", pro=pro, path=path, sleep_sec=0, verbose=False
    )
    assert members == ["a.SZ", "b.SZ", "c.SZ"]
    assert path.is_file()
    first_calls = len(pro.calls)
    assert first_calls == 2

    # 相同区间再次解析：缓存已覆盖，不应再请求 Tushare
    members2 = im.resolve_index_members_cached(
        "zz1000", "2020-01-01", "2020-02-29", pro=pro, path=path, sleep_sec=0, verbose=False
    )
    assert members2 == members
    assert len(pro.calls) == first_calls


def test_resolve_cached_refresh_forces_fetch(tmp_path):
    path = tmp_path / "idx.parquet"
    pro = _FakePro({"20200131": ["a.SZ"]})
    im.resolve_index_members_cached(
        "zz1000", "2020-01-01", "2020-01-31", pro=pro, path=path, sleep_sec=0, verbose=False
    )
    calls_after_first = len(pro.calls)
    im.resolve_index_members_cached(
        "zz1000", "2020-01-01", "2020-01-31", pro=pro, path=path, sleep_sec=0, verbose=False,
        refresh=True,
    )
    assert len(pro.calls) > calls_after_first
