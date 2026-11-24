"""Growth by type of municipality: every town in exactly one category, totals add up."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import trends_types as TT  # noqa: E402


def test_every_town_typed_and_categories_add_up():
    m = TT.muni_typed()
    s = TT.summary()
    total = s[s["dimension"] == "all"]
    for dim in TT.DIMS:
        d = s[s["dimension"] == dim]
        assert d["towns"].sum() == total["towns"].iloc[0] == m["muni_id"].nunique()
        assert abs(d["commitment_2025"].sum() - total["commitment_2025"].iloc[0]) < 1


def test_fixed_set_has_every_year():
    m = TT.muni_typed()
    assert (m.groupby("muni_id")["Year"].nunique() == TT.LAST - TT.FIRST + 1).all()


def test_municipal_appropriation_groups_add_up():
    s = TT.trcf_summary("trcf_municipal")
    total = s[s["dimension"] == "all"].iloc[0]
    for dim in TT.DIMS:
        d = s[s["dimension"] == dim]
        assert d["towns"].sum() == total["towns"]
        assert abs(d["trcf_municipal_2025"].sum() - total["trcf_municipal_2025"]) < 1


def test_sanford_2022_education_netted_and_net_unchanged():
    from lib import trends as T
    m = T.mvr_muni()
    s = m[m["Place"].str.upper().eq("SANFORD")].set_index("Year")
    assert 15e6 < s.loc[2022, "trcf_education"] < 20e6          # was $59.3M gross
    assert abs(s.loc[2022, "trcf_net"] - 36_745_901.89) < 1      # net to be raised untouched
    a = s.loc[2022]
    assert abs(a["trcf_county"] + a["trcf_municipal"] + a["trcf_tif"] + a["trcf_education"]
               - a["trcf_appropriations"]) < 1
