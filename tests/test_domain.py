import pytest

from server.domain import (
    RuleError,
    category,
    component,
    results,
    submit,
    tenths,
    transition,
)


@pytest.mark.parametrize(
    ("birth", "group"),
    [
        ("2014-06-01", 0),
        ("2013-06-02", 0),
        ("2013-06-01", 1),
        ("2008-06-01", 2),
        ("1986-06-01", 3),
    ],
)
def test_category(birth, group):
    assert category(birth, "2026-06-01", [13, 18, 40]) == group


def test_future_birth():
    with pytest.raises(RuleError):
        category("2027-01-01", "2026-01-01", [13, 18, 40])


@pytest.mark.parametrize("value", [0, 0.1, 9.9, 10])
def test_valid_scores(value):
    assert tenths(value) == int(10 * value)


@pytest.mark.parametrize("value", [-0.1, 10.1, 0.01, "", "нет", "NaN", "Infinity"])
def test_invalid_scores(value):
    with pytest.raises(RuleError):
        tenths(value)


def test_ranking():
    assert component([10]) == 1
    assert component([10, 30]) == 2
    assert component([0, 0, 100, 100]) == 5
    e = {"judges": ["x", "y", "z"], "participants": {}, "scores": {}}
    for i, (tech, art, group) in enumerate(
        [(80, 80, 0), (80, 80, 0), (70, 95, 0), (1, 1, 1), (0, 0, 1), (0, 0, 0)]
    ):
        n = str(i + 1)
        e["participants"][n] = dict(surname=n, name="Имя", club="Клуб", category=group)
        if i != 5:
            e["scores"][n] = {
                "x": dict(t=0, a=100),
                "y": dict(t=tech, a=art),
                "z": dict(t=100, a=0),
            }
    rows = results(e, "x")
    assert [(r["total"], r["rank"]) for r in rows] == [
        (8, 1),
        (8, 1),
        (8, 3),
        (0.1, 1),
        (0, 2),
    ]
    assert rows[2]["technique"] == 7
    e["scores"]["1"] = {
        "x": dict(t=70, a=85),
        "y": dict(t=71, a=86),
        "z": dict(t=100, a=0),
    }
    assert results(e, "x")[2]["total"] == 7.66


def test_rules_and_replays():
    e = dict(
        judges=["a", "b"],
        chief="a",
        owner="o",
        state="draft",
        participants={"1": dict(name="N", surname="S", club="C", category=0)},
        scores={},
        operations={},
        corrections={},
        audit=[],
    )
    b = dict(operation="one", technique=4, artistry=5, version=0)

    def rejected(fn, *args):
        with pytest.raises(RuleError):
            fn(*args)

    rejected(transition, e, "start", "a")
    rejected(submit, e, "a", "1", b, "now")
    transition(e, "start", "o")
    rejected(transition, e, "start", "o")
    rejected(transition, e, "finish", "a")
    rejected(transition, e, "finish", "o")
    rejected(submit, e, "c", "1", b, "now")
    rejected(submit, e, "a", "2", b, "now")
    assert submit(e, "a", "1", b, "now") == (1, False)
    assert submit(e, "a", "1", b, "now") == (1, False)
    rejected(submit, e, "a", "1", b | {"technique": 6}, "now")
    rejected(submit, e, "a", "1", b | {"operation": "two"}, "now")
    rejected(submit, e, "a", "1", b | {"operation": "two", "version": 1}, "now")
    assert submit(e, "b", "1", b | {"operation": "three"}, "now") == (1, True)
    e["corrections"] = {
        "1": {
            "a": {"reason": "r", "approved": True},
            "b": {"reason": "r", "approved": True},
        }
    }
    rejected(transition, e, "finish", "o")
    for judge in ("a", "b"):
        assert submit(
            e, judge, "1", b | {"operation": "fix" + judge, "version": 1}, "now"
        ) == (2, False)
    transition(e, "finish", "o")
    rejected(transition, e, "approve", "b")
    rejected(transition, e, "approve", "a")
    e["draft_protocol"] = True
    transition(e, "approve", "a")
    rejected(transition, e, "approve", "a")
