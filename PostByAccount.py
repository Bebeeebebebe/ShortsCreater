import threading
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
from selenium.webdriver.common.keys import Keys
# pip install keyboard
import keyboard
import pickle
from dataclasses import dataclass
import subprocess
import random
import time

@dataclass
class VideoSideTexts:
    description: str
    hashtags: str
    music_author: str
    music_name: str

@dataclass
class VideoPostRequest:
    """
    Запрос на публикацию видео для конкретного аккаунта.

    Используется для передачи данных в систему автопостинга:
    - account_name: путь к файлу аккаунта .pkl, который публикует видео
    - videos: словарь {путь_к_видео -> текстовые данные для этого видео}
    """
    platform: str
    account_name: str
    videos: dict[str, VideoSideTexts]

def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0):
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)
    return delay

class MultiPost:
    def __init__(self, video_post_requests: list[VideoPostRequest]):
        self.requests = video_post_requests
        # Создаем драйверы через отдельный метод, чтобы учитывать версию Chrome
        self.drivers = [self.start_driver() for _ in video_post_requests]

    def normalize_platform(self, platform: str) -> str:
        return platform.strip().lower()

    def get_chrome_main_version(self) -> int | None:
        """
        Возвращает основную версию установленного Chrome (например 145),
        либо None если определить не удалось.
        """
        try:
            output = subprocess.check_output(
                r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
                shell=True,
                text=True
            )

            full_version = output.strip().split()[-1]
            main_version = int(full_version.split(".")[0])

            print(f"Используем Chrome версии {full_version}")

            return main_version

        except Exception:
            print("Не удалось определить версию Chrome, используем дефолт")
            return None
    def get_cookie_path(self, request: VideoPostRequest) -> str:
        platform = self.normalize_platform(request.platform)

        return os.path.join(
            "Accounts",
            platform,
            f"{request.account_name}.pkl"
        )
    def start_driver(self):
        options = uc.ChromeOptions()

        main_version = self.get_chrome_main_version()

        driver = uc.Chrome(version_main=main_version, options=options)
        driver.maximize_window()
        return driver

    def autorize(self, index: int):
        driver = self.drivers[index]
        request = self.requests[index]

        platform = self.normalize_platform(request.platform)

        TARGET_SITES = {
            "tiktok": "https://www.tiktok.com/",
            "youtube": "https://www.youtube.com/"
        }

        if platform not in TARGET_SITES:
            raise ValueError(f"Платформа {platform} не поддерживается")

        cookie_file = self.get_cookie_path(request)

        if not os.path.exists(cookie_file):
            raise FileNotFoundError(f"Файл cookies не найден: {cookie_file}")

        base_url = TARGET_SITES[platform]

        # 1️⃣ максимально чисто
        driver.get("about:blank")
        driver.get(base_url)

        driver.execute_cdp_cmd("Network.enable", {})
        driver.delete_all_cookies()

        # 2️⃣ грузим session_data
        with open(cookie_file, "rb") as f:
            session_data = pickle.load(f)

        cookies = session_data.get("cookies", [])
        local_storage = session_data.get("local_storage", {})

        # 3️⃣ восстанавливаем cookies через CDP
        for cookie in cookies:
            cdp_cookie = {
                "name": cookie.get("name"),
                "value": cookie.get("value"),
                "domain": cookie.get("domain"),
                "path": cookie.get("path", "/"),
                "secure": cookie.get("secure", False),
                "httpOnly": cookie.get("httpOnly", False),
            }

            if "expiry" in cookie:
                cdp_cookie["expires"] = int(cookie["expiry"])

            try:
                driver.execute_cdp_cmd("Network.setCookie", cdp_cookie)
            except Exception as e:
                print("CDP cookie error:", e)

        # 4️⃣ восстанавливаем localStorage
        for key, value in local_storage.items():
            driver.execute_script(
                "window.localStorage.setItem(arguments[0], arguments[1]);",
                key, value
            )

        # 5️⃣ финальный reload
        driver.get(base_url)

        print(f"✅ Полная авторизация (cookies + LS): {platform}/{request.account_name}")

    def prepare_for_posting(self, platform_name: str):
        """
        Общая подготовка к постингу:
        - фильтрация по платформе
        - авторизация
        - возврат (index, request, driver)
        """

        platform_name = self.normalize_platform(platform_name)

        for index, request in enumerate(self.requests):
            if self.normalize_platform(request.platform) != platform_name:
                continue

            print(f"▶ Подготовка аккаунта: {platform_name}/{request.account_name}")

            self.autorize(index)

            driver = self.drivers[index]

            yield index, request, driver

    def post_to_youtube(self):
        for index, request, driver in self.prepare_for_posting("youtube"):

            driver.get("https://studio.youtube.com")

            for video_path, side_text in request.videos.items():
                print(f"  ⬆ YouTube видео: {video_path}")

                # ===== ТВОЙ СЦЕНАРИЙ =====
                # upload_btn = driver.find_element(By.XPATH, "//ytcp-button[@id='upload-icon']")
                # upload_btn.click()

                # file_input = driver.find_element(By.XPATH, "//input[@type='file']")
                # file_input.send_keys(os.path.abspath(video_path))

                # title_input = driver.find_element(By.ID, "textbox")
                # title_input.clear()
                # title_input.send_keys(side_text.description)

                # description_box = driver.find_elements(By.ID, "textbox")[1]
                # description_box.send_keys(side_text.hashtags)

                # next_btn = driver.find_element(By.XPATH, "//ytcp-button[@id='next-button']")
                # next_btn.click()  # несколько раз

                # publish_btn = driver.find_element(By.XPATH, "//ytcp-button[@id='done-button']")
                # publish_btn.click()
                # =========================

                print(f"  ✅ YouTube видео отправлено: {video_path}")

    def get_random_mobile_profile(self):
        mobile_profiles = [
            {
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                "width": 390,
                "height": 844
            },
            {
                "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                "width": 412,
                "height": 915
            },
            {
                "user_agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                "width": 393,
                "height": 851
            }
        ]

        return random.choice(mobile_profiles)

    def type_like_human(self, element, text, min_delay=0.02, max_delay=0.06):
        """
        Эмулирует человеческий ввод текста посимвольно.
        """
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))
    def post_to_tiktok(self):
        for index, request, driver in self.prepare_for_posting("tiktok"):
            for video_path, side_text in request.videos.items():
                driver.get("https://www.tiktok.com/upload")
                print(f"  ⬆ TikTok видео: {video_path}")
                time.sleep(10)
                driver.execute_script("document.body.click();")
                time.sleep(5)

                driver.execute_script("""
                const host = document.querySelector('tiktok-cookie-banner');
                if (host && host.shadowRoot) {
                    const buttons = host.shadowRoot.querySelectorAll('button');
                    if (buttons.length > 1) {
                        buttons[1].click();  // "Разрешить все"
                    }
                }
                """)

                time.sleep(5)
                # ждём input
                file_input = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                )
                time.sleep(random_delay(0.5, 1.2))

                time.sleep(2)
                # загружаем видео
                file_input.send_keys(os.path.abspath(video_path))
                time.sleep(random_delay(0.8, 1.4))
                
                try:
                    time.sleep(5)
                    enable_btn = WebDriverWait(driver, 20).until(
                        EC.element_to_be_clickable((
                            By.CSS_SELECTOR,
                            "div[role='dialog'] .common-modal-footer button[data-type='primary']"
                        ))
                    )

                    enable_btn.click()
                except:
                    pass
                try:

                    time.sleep(5)
                    btn = WebDriverWait(driver, 20).until(
                        EC.element_to_be_clickable((
                            By.XPATH,
                            "//div[contains(@class,'tutorial-tooltip')]"
                            "//button[@data-type='primary']"
                        ))
                    )
                    driver.execute_script("arguments[0].click();", btn)
                except:
                    pass

                #Заполнение содержания видео
                #описание
                description = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        'div[contenteditable="true"]'
                    ))
                )

                description.click()
                time.sleep(0.5)

                # Встаём в конец текста
                description.send_keys(Keys.CONTROL + Keys.END)
                time.sleep(0.3)

                # Выделяем всё и удаляем по одному символу через BACKSPACE
                text_length = len(description.text)
                for _ in range(text_length + 20):  # +20 на всякий случай
                    description.send_keys(Keys.BACKSPACE)
                    time.sleep(0.01)

                time.sleep(0.5)

                # Фокус
                description.click()
                time.sleep(0.3)

                # Сначала описание
                self.type_like_human(description, side_text.description)

                # Небольшая пауза как будто человек думает
                time.sleep(random.uniform(0.4, 0.8))

                # Пробел перед хештегами
                description.send_keys(" ")
                #web-creation-caption-hashtag-button
                time.sleep(random.uniform(0.1, 0.2))

                # Вводим каждый хештег и подтверждаем Enter
                hashtags = [tag for tag in side_text.hashtags.split("#") if tag.strip()]
                for tag in hashtags:
                    self.type_like_human(description, "#" + tag)
                    time.sleep(random.uniform(3, 4))
                    driver.execute_script("""
                        arguments[0].dispatchEvent(new KeyboardEvent('keydown', {
                            key: 'Enter', code: 'Enter', keyCode: 13,
                            bubbles: true, cancelable: true
                        }));
                        arguments[0].dispatchEvent(new KeyboardEvent('keypress', {
                            key: 'Enter', code: 'Enter', keyCode: 13,
                            bubbles: true, cancelable: true
                        }));
                        arguments[0].dispatchEvent(new KeyboardEvent('keyup', {
                            key: 'Enter', code: 'Enter', keyCode: 13,
                            bubbles: true, cancelable: true
                        }));
                    """, description)
                    time.sleep(random.uniform(0.3, 0.6))

                #Звук
                # ===== Парсинг названия и автора звука =====
                # Звук (опционально — только если указаны автор и название)
                if side_text.music_author and side_text.music_name:
                    time.sleep(5)

                    sound_query = f"{side_text.music_author} - {side_text.music_name}"

                    soundBtn = driver.find_element(By.XPATH, '//*[@id="open-new-editor"]/div[2]/button')
                    soundBtn.click()
                    soundInput = WebDriverWait(driver, 20).until(
                        EC.element_to_be_clickable((
                            By.CSS_SELECTOR,
                            'input.TextInput__input'
                        ))
                    )

                    soundInput.click()
                    soundInput.clear()
                    self.type_like_human(soundInput, sound_query)

                    soundInput.send_keys(Keys.ENTER)

                    WebDriverWait(driver, 10).until(
                        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".MusicPanelMusicItem__wrap")) > 0
                    )

                    items = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((
                            By.CSS_SELECTOR,
                            ".MusicPanelMusicItem__wrap"
                        ))
                    )

                    first_item = items[0]
                    add_button = first_item.find_element(By.CSS_SELECTOR, "button")
                    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(add_button))
                    add_button.click()

                    time.sleep(3)

                    saveBtn = driver.find_element(By.XPATH,
                                                  '//*[@id="root"]/div/div/div[2]/div[2]/div/div/div/div[5]/div[2]/div[2]/div/div[2]/div[1]/div[3]/div/button[2]')
                    saveBtn.click()

                    time.sleep(2)
                else:
                    print(f"  ℹ Звук не указан, пропускаем шаг добавления музыки")
                #Кнопка опубликовать
                driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div[2]/div[2]/div/div/div/div[6]/div/button[1]').click()
                time.sleep(3)
                try:
                    driver.find_element(By.CLASS_NAME, 'TUXButton.TUXButton--default.TUXButton--medium.TUXButton--primary').click()
                except:
                    pass
                print(f"  ✅ TikTok видео отправлено: {video_path}")