"""The report renderer and the number checker, on hand-made inputs."""
import pytest

from pavement_ai import report as R

RES = {
    "a": {"mae": 0.12345, "n": 19949, "share": 0.9512, "level": 0.95, "name": "JTG 5210-2018, clause 7.4.7",
          "list": [{"v": 2.5}, {"v": -0.0375}], "flag": True, "none": None, "whole": 3.0},
    "b": {"date": "retrieved 2026-11-17", "cost": 332000},
}


def test_lookup_and_fmt():
    assert R.lookup(RES, "a", "list.1.v") == -0.0375
    assert R.fmt(0.12345, ".3f") == "0.123"
    assert R.fmt(19949, ",d") == "19,949"
    assert R.fmt(3.0, "d") == "3"
    assert R.fmt(0.9512, "pct1") == "95.1"
    assert R.fmt(0.95, "pct0") == "95"
    assert R.fmt("x", "s") == "x"
    with pytest.raises(ValueError):
        R.fmt(2.5, "d")                       # a fraction must not be printed as a whole number
    with pytest.raises(TypeError):
        R.fmt("2.5", ".1f")
    with pytest.raises(TypeError):
        R.fmt(True, "d")
    with pytest.raises(TypeError):
        R.fmt(1.0, "s")


def test_render_fills_placeholders_and_tables():
    tpl = "MAE {{a:mae|.3f}} on {{ a:n | ,d }} visits ({{a:share|pct1}}%), {{a:name}}. {{table:t}}"
    out = R.render(tpl, RES, {"t": lambda res: "T=" + R.fmt(res["b"]["cost"], ",d")})
    assert out == "MAE 0.123 on 19,949 visits (95.1%), JTG 5210-2018, clause 7.4.7. T=332,000"
    with pytest.raises(KeyError):
        R.render("{{a:missing|.1f}}", RES)
    with pytest.raises(ValueError):
        R.render("{{ broken", RES)


def test_template_digits():
    assert R.template_digits("MAE {{a:mae|.3f}} and {{a:list.1.v|.2f}} m/km") == []
    assert R.template_digits("top 5 of {{a:n|,d}}, 95% interval") == ["5", "95"]


def test_supported_numbers():
    text = ("MAE 0.123 (0.12) on 19,949 visits; 95.1% and 95%; clause 7.4.7 of JTG 5210-2018; change -0.04; "
            "2.5 and 3 items; retrieved 2026-11-17; cost 332,000")
    assert R.unsupported_numbers(text, RES) == []


@pytest.mark.parametrize("text, bad", [
    ("MAE 0.124", ["0.124"]),                 # rounding the stored 0.12345 to three places gives 0.123
    ("19,950 visits", ["19,950"]),
    ("95.2%", ["95.2"]),
    ("clause 7.4.8", ["7.4.8"]),              # clause numbers count only when a results string carries them
    ("2 items", ["2"]),                       # 2.5 must not pass as "2" or "3" ...
    ("0 left", ["0"]),                        # ... and 0.12 / -0.04 must not pass as "0"
    ("12 %", ["12"]),                         # 0.12345 x 100 = 12.3, not a whole 12
    ("year 2025", ["2025"]),
    ("JTG 5210-2019", ["2019"]),
])
def test_unsupported_numbers_are_reported(text, bad):
    assert R.unsupported_numbers(text, RES) == bad


def test_whole_numbers_need_whole_values():
    assert R.unsupported_numbers("3 folds", RES) == []                 # 3.0 is a whole number
    assert R.unsupported_numbers("95 %", RES) == []                    # 0.95 x 100
    assert R.unsupported_numbers("1 site", {"x": {"v": 1.4}}) == ["1"]
    assert R.unsupported_numbers("1.4 and 140", {"x": {"v": 1.4}}) == []
    assert R.unsupported_numbers("flag 1", {"x": {"v": True}}) == ["1"]    # booleans are not numbers
