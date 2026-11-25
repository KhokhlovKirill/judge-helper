"""Competition rules. Scores are stored as integer tenths."""

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from statistics import mean


class RuleError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def require(condition, message, status=422):
    if not condition:
        raise RuleError(message, status)


def category(birth, start, boundaries):
    birth, start = date.fromisoformat(birth), date.fromisoformat(start)
    require(birth <= start, "Дата рождения позже соревнования")
    age = (
        start.year - birth.year - ((start.month, start.day) < (birth.month, birth.day))
    )
    return sum(age >= limit for limit in boundaries)


def tenths(value):
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise RuleError("Нужно число") from None
    require(
        number.is_finite() and 0 <= number <= 10 and number * 10 == int(number * 10),
        "Оценка от 0 до 10 с шагом 0,1",
    )
    return int(number * 10)


def component(values):
    ordered = sorted(values)
    kept = ordered[1:-1] if len(ordered) >= 3 else ordered
    return Decimal(sum(kept)) / (10 * Decimal(len(kept)))


def rounded(value):
    return float(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP))


def results(event, viewer):
    rows = []
    for number, participant in event["participants"].items():
        scores = event["scores"].get(number, {})
        if len(scores) != len(event["judges"]) or not scores:
            continue
        technique, artistry = (
            component([s[field] for s in scores.values()]) for field in ("t", "a")
        )
        rows.append(
            dict(
                number=int(number),
                name=participant["surname"] + " " + participant["name"],
                club=participant["club"],
                category=participant["category"],
                technique=rounded(technique),
                artistry=rounded(artistry),
                total=rounded((6 * technique + 4 * artistry) / 10),
            )
        )
    rows.sort(key=lambda r: (r["category"], -r["total"], -r["technique"], r["number"]))
    previous, position, rank = None, 0, 0
    for row in rows:
        key = row["category"], row["total"], row["technique"]
        position = 1 if previous is None or previous[0] != key[0] else position + 1
        if previous != key:
            rank = position
        row["rank"], previous = rank, key
    return rows


def charts(event, rows):
    distribution, deviations = defaultdict(list), defaultdict(lambda: defaultdict(list))
    for row in rows:
        group = row["category"]
        distribution[group].append(row["total"])
        scores = event["scores"][str(row["number"])]
        weighted = {
            judge: (s["t"] * 0.6 + s["a"] * 0.4) / 10 for judge, s in scores.items()
        }
        average = mean(weighted.values())
        for judge, value in weighted.items():
            deviations[group][judge].append(value - average)
    return {
        "distribution": distribution,
        "deviations": {
            group: {judge: round(mean(values), 2) for judge, values in judges.items()}
            for group, judges in deviations.items()
        },
    }


def transition(event, action, actor):
    if action == "start":
        require(actor == event["owner"], "Только организатор", 403)
        require(
            event["state"] == "draft" and event["participants"] and event["judges"],
            "Нужен черновик с участниками и бригадой",
            409,
        )
        event["state"] = "active"
    elif action == "finish":
        require(actor == event["owner"], "Только организатор", 403)
        require(
            event["state"] == "active"
            and len(results(event, actor)) == len(event["participants"])
            and not event["corrections"],
            "Не все оценки или исправления завершены",
            409,
        )
        event["state"] = "finished"
    else:
        require(
            action == "approve" and actor == event["chief"], "Только главный судья", 403
        )
        require(
            event["state"] == "finished" and event.get("draft_protocol"),
            "Сначала сформируйте протокол",
            409,
        )
        event["state"] = "approved"


def submit(event, actor, number, body, timestamp):
    require(actor in event["judges"], "Только назначенный судья", 403)
    require(number in event["participants"], "Нет участника", 404)
    t, a = tenths(body["technique"]), tenths(body["artistry"])
    op = body["operation"]
    signature = [number, actor, t, a, body["version"]]
    last = event["operations"].get(op)
    if last:
        require(last["signature"] == signature, "Идентификатор уже использован", 409)
        return last["version"], False
    require(event["state"] == "active", "Соревнование не идёт", 409)
    scores = event["scores"].setdefault(number, {})
    old = scores.get(actor)
    version = old["version"] if old else 0
    require(body["version"] == version, "Версии различаются", 409)
    permission = event["corrections"].get(number, {}).get(actor, {})
    if old:
        require(permission.get("approved"), "Нужно разрешение главного судьи", 409)
        event["audit"].append(
            dict(
                judge=actor,
                number=number,
                old=old.copy(),
                new=[t, a],
                reason=permission["reason"],
                time=timestamp,
            )
        )
        del event["corrections"][number][actor]
        if not event["corrections"][number]:
            del event["corrections"][number]
    scores[actor] = dict(t=t, a=a, version=version + 1)
    event["operations"][op] = dict(signature=signature, version=version + 1)
    return version + 1, not old and len(scores) == len(event["judges"])
