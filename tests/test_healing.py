import pytest
from ci.healing import buttons, select_button, verify_score


def test_replay_and_business_failure():
    source = '<hierarchy><android.widget.Button enabled="true" content-desc="Отмена"/><android.widget.Button enabled="true" content-desc="Отправить оценку"/><android.widget.EditText text="private@example.test"/></hierarchy>'
    opts = buttons(source)
    assert select_button(opts, lambda _: 1)["label"] == "Отправить оценку"
    with pytest.raises(ValueError):
        select_button(opts, lambda _: 9)
    state = {"scores": {"1": {"judge": {"t": 84, "a": 90, "version": 1}}}}
    verify_score(state, 1, "judge", 84, 90)
    state["scores"]["1"]["judge"]["t"] = 0
    with pytest.raises(AssertionError, match="неверные баллы"):
        verify_score(state, 1, "judge", 84, 90)
