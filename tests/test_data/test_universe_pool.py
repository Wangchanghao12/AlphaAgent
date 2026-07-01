"""universe 与股票池拉取测试。"""



from unittest.mock import MagicMock



import pandas as pd



from seekalpha.data.universe import (

    _members_from_index_member,

    apply_is_st,

    fetch_index_members,

    fetch_index_members_for_dates,

    fetch_st_table,

    resolve_index_code,

)





def test_resolve_index_code():

    assert resolve_index_code("zz1000") == "000852.SH"





def test_members_from_index_member_overlap():

    df = pd.DataFrame(

        {

            "con_code": ["A.SZ", "B.SZ", "C.SZ", "D.SZ"],

            "in_date": ["20140101", "20160101", "20200101", "20230101"],

            "out_date": ["20151231", None, "20201231", "99991231"],

        }

    )

    # 2015-06 ~ 2022-12: A(2015末出), B(仍在), C(2020), D(2023才入→不含)

    got = _members_from_index_member(df, "2015-06-01", "2022-12-31")

    assert got == ["A.SZ", "B.SZ", "C.SZ"]





def test_fetch_index_members_prefers_index_member():

    pro = MagicMock()

    pro.index_member.return_value = pd.DataFrame(

        {

            "con_code": ["000001.SZ", "000002.SZ"],

            "in_date": ["20140101", "20140101"],

            "out_date": [None, None],

        }

    )

    members = fetch_index_members(pro, "zz1000", "2020-01-01", "2024-12-31", verbose=False)

    assert members == ["000001.SZ", "000002.SZ"]

    pro.index_weight.assert_not_called()





def test_fetch_index_members_fallback_weight():

    pro = MagicMock()

    pro.index_member.return_value = pd.DataFrame()

    pro.index_weight.return_value = pd.DataFrame(

        {

            "con_code": ["600000.SH"],

            "trade_date": ["20240131"],

            "weight": [0.1],

        }

    )

    members = fetch_index_members(

        pro, "zz1000", "2024-01-01", "2024-01-31", sleep_sec=0, verbose=False

    )

    assert "600000.SH" in members





def test_fetch_index_members_long_span_uses_monthly_union():

    pro = MagicMock()

    pro.index_member.return_value = pd.DataFrame()

    pro.index_weight.return_value = pd.DataFrame(

        {

            "con_code": ["600000.SH", "600001.SH"],

            "trade_date": ["20201231", "20201231"],

            "weight": [0.1, 0.1],

        }

    )

    members = fetch_index_members(

        pro, "zz1000", "2012-01-01", "2026-06-30", sleep_sec=0, verbose=False

    )

    assert members == ["600000.SH", "600001.SH"]

    assert pro.index_weight.call_count >= 1





def test_fetch_index_members_for_dates():
    pro = MagicMock()

    def fake_weight(**kwargs):
        end = kwargs.get("end_date", "")
        if end == "20240628":
            return pd.DataFrame(
                {"con_code": ["000001.SZ", "000002.SZ"], "trade_date": ["20240628", "20240628"]}
            )
        return pd.DataFrame()

    pro.index_weight.side_effect = fake_weight
    pool = fetch_index_members_for_dates(
        pro, "zz1000", ["2024-06-28"], sleep_sec=0, verbose=False
    )
    assert pool == {"000001.SZ", "000002.SZ"}


def test_fetch_st_table_empty():

    pro = MagicMock()

    pro.stock_st.return_value = pd.DataFrame()

    out = fetch_st_table(pro, trade_date="20240102")

    assert list(out.columns) == ["ts_code", "trade_date", "is_st"]

    assert out.empty





def test_apply_is_st_no_st_records():

    df = pd.DataFrame({"ts_code": ["A.SZ"], "trade_date": ["20240102"]})

    out = apply_is_st(df, pd.DataFrame(columns=["ts_code", "trade_date", "is_st"]))

    assert out["is_st"].tolist() == [0]

    assert out["not_st"].tolist() == [1]


