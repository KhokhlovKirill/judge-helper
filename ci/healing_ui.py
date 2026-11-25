"""Run against the APK and the synthetic acceptance server on a GitHub emulator."""

import json
import os
import time
from pathlib import Path

import httpx
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait

from .healing import buttons, openrouter, select_button, verify_score


def run():
    email = "heal@example.test"
    host = "http://127.0.0.1:8000"
    session = httpx.post(
        host + "/login", json={"email": email, "password": "Contest123"}
    ).json()
    client = httpx.Client(
        base_url=host, headers={"Authorization": "Bearer " + session["token"]}
    )
    event = client.get("/events").json()[0]["id"]
    opts = UiAutomator2Options().load_capabilities(
        {
            "appium:app": str(Path(os.environ["APK"]).resolve()),
            "appium:automationName": "UiAutomator2",
            "appium:autoGrantPermissions": True,
            "appium:newCommandTimeout": 120,
        }
    )
    driver = webdriver.Remote("http://127.0.0.1:4723", options=opts)
    report = []

    def find(by, key):
        return WebDriverWait(driver, 25).until(lambda d: d.find_element(by, key))

    def label(value):
        return find(AppiumBy.ACCESSIBILITY_ID, value)

    def inputs():
        return WebDriverWait(driver, 15).until(
            lambda d: (
                v
                if len(
                    v := d.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
                )
                >= 2
                else False
            )
        )

    try:
        a, p = inputs()
        a.send_keys(email)
        p.send_keys("Contest123")
        if driver.is_keyboard_shown():
            driver.hide_keyboard()
        label("Войти").click()
        find(AppiumBy.XPATH, "//*[contains(@content-desc,'Мобильная приёмка')]").click()
        for n, mode in [(1, "baseline"), (2, "healed"), (3, "injected-defect")]:
            find(
                AppiumBy.XPATH,
                f"//*[contains(@content-desc,'{n}. Тестов Участник {n}')]",
            ).click()
            t, a = inputs()
            t.send_keys("8.4")
            a.send_keys("9")
            if driver.is_keyboard_shown():
                driver.hide_keyboard()
            label("Сохранить").click()
            label("Отправить оценку")
            original = "score_confirm" if mode == "baseline" else "submit_score_legacy"
            matches = driver.find_elements(
                AppiumBy.XPATH,
                f"//*[@resource-id='{original}' or substring-after(@resource-id,':id/')='{original}']",
            )
            entry = {"case": mode, "locator": original}
            if matches:
                matches[0].click()
            else:
                assert mode != "baseline", "Исходный локатор отсутствует"
                candidates = buttons(driver.page_source)
                chosen = select_button(candidates, openrouter)
                entry.update(
                    candidates=candidates,
                    choice=chosen,
                    model=os.environ["OPENROUTER_MODEL"],
                )
                label(chosen["label"]).click()
            for _ in range(60):
                snapshot = client.get("/events/" + event).json()
                if str(n) in snapshot["scores"]:
                    break
                time.sleep(0.25)
            if mode == "injected-defect":
                try:
                    verify_score(snapshot, n, email, 84, 90)
                except AssertionError as exc:
                    assert str(exc) == "Сохранены неверные баллы"
                    entry.update(
                        result="Failed", expected_failure=True, reason=str(exc)
                    )
                else:
                    raise AssertionError("Тест пропустил внедрённую ошибку")
            else:
                verify_score(snapshot, n, email, 84, 90)
                entry["result"] = "Passed"
            report.append(entry)
    finally:
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/self-healing.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2)
        )
        driver.save_screenshot("artifacts/last-screen.png")
        driver.quit()
        client.close()


if __name__ == "__main__":
    run()
