"""Selection is the only model-controlled step. The assertion stays independent."""

import json
import os
from xml.etree import ElementTree

import httpx


def buttons(source):
    result = []
    for node in ElementTree.fromstring(source).iter("android.widget.Button"):
        label = node.get("content-desc") or node.get("text")
        if node.get("enabled") == "true" and label in (
            "Отмена",
            "Отправить оценку",
            "Сохранить",
            "Подтвердить",
        ):
            result.append({"id": len(result), "role": "button", "label": label})
    return result


def select_button(options, completion):
    index = completion(options)
    if type(index) is not int or index not in [item["id"] for item in options]:
        raise ValueError("Модель не выбрала доступную кнопку")
    return options[index]


def openrouter(options):
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
        json={
            "model": os.environ["OPENROUTER_MODEL"],
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": 'Select the button that submits the score. Return only a JSON object with integer field "id".',
                },
                {"role": "user", "content": json.dumps(options, ensure_ascii=False)},
            ],
        },
        timeout=45,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])["id"]


def verify_score(snapshot, number, judge, technique, artistry):
    scores = snapshot["scores"][str(number)]
    assert list(scores) == [judge], "Ожидалась ровно одна оценка"
    assert scores[judge] == {"t": technique, "a": artistry, "version": 1}, (
        "Сохранены неверные баллы"
    )
