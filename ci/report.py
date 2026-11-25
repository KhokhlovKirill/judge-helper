import json
import os
from pathlib import Path
from xml.etree import ElementTree
from .matrix import CASES, EXTRA


def main():
    root = Path("evidence")
    jobs = {k: v["result"] for k, v in json.loads(os.environ["JOB_RESULTS"]).items()}
    tests = {}
    for file in root.rglob("server.xml"):
        for case in ElementTree.parse(file).iter("testcase"):
            name = case.get("name").split("[")[0]
            tests[name] = tests.get(name, True) and len(case) == 0

    def result(check):
        job, _, name = check
        if job == "server" and name in tests:
            return "Passed" if tests[name] else "Failed"
        if job == "mobile":
            statuses = [jobs.get("android"), jobs.get("ios")]
        else:
            statuses = [jobs.get(job)]
        if "failure" in statuses:
            return "Failed"
        if all(s == "success" for s in statuses):
            return "Passed"
        return "Not run"

    text = [
        "# Помощник судьи",
        f"Коммит `{os.environ['GITHUB_SHA']}`",
        "",
        "| Проверка | Источник | Результат |",
        "|---|---|---|",
    ]
    for key, (title, checks) in [(f"JUDGE-{i}", v) for i, v in CASES.items()] + [
        (k, (k, v)) for k, v in EXTRA.items()
    ]:
        statuses = [result(c) for c in checks]
        status = next((v for v in ("Failed", "Not run") if v in statuses), "Passed")
        text.append(
            f"| {key} · {title} | {', '.join(c[2] for c in checks)} | {status} |"
        )
    text.extend(
        [
            "",
            "iOS проверяется на доступных симуляторах. Прогон на iOS 15 и доставка push на физическое устройство требуют отдельной проверки. Результаты OAuth и push в CI используют тестовый транспорт.",
            "",
            str(jobs),
        ]
    )
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
        out.write("\n".join(text))
    expected = (
        jobs.keys()
        if os.environ["GITHUB_EVENT_NAME"] != "pull_request"
        else ("server", "flutter")
    )
    assert all(jobs[k] == "success" for k in expected), jobs


if __name__ == "__main__":
    main()
