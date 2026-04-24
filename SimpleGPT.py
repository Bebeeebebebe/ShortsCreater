import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
import os
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
import json
from pathlib import Path
import subprocess
import pickle
import random
import time
import requests
from urllib.parse import urlparse

class SimpleGPT:
    def __init__(self, session_path: str, options: Options | None = None, dowload_folder: str = None):
        self.session_path = Path(session_path)
        self.options = options if options is not None else self._default_options()
        self.driver = self._init_driver()
        self.chat = None
        self.download_folder = dowload_folder
        self._load_cookies()

    def _default_options(self) -> uc.ChromeOptions:
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        return options

    def get_chrome_version(self):
        try:
            output = subprocess.check_output(
                r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
                shell=True,
                text=True
            )
            version = output.strip().split()[-1]
            return int(version.split(".")[0])
        except Exception:
            return None

    def _init_driver(self):
        chrome_version = self.get_chrome_version()
        driver = uc.Chrome(
            options=self.options,
            version_main=chrome_version
        )
        return driver

    def _load_cookies(self):
        cookies_file = self.session_path

        if not cookies_file.exists():
            return

        # Сначала открываем сайт
        self.driver.get("https://chat.openai.com/")

        # Читаем pickle
        with open(cookies_file, "rb") as f:
            session_data = pickle.load(f)

        cookies = session_data.get("cookies", [])

        for cookie in cookies:
            if "expiry" in cookie:
                cookie["expiry"] = int(cookie["expiry"])
            try:
                self.driver.add_cookie(cookie)
            except Exception:
                pass

        self.driver.refresh()

    def save_cookies(self):
        cookies_file = self.session_path / "cookies.json"
        self.session_path.mkdir(parents=True, exist_ok=True)

        cookies = self.driver.get_cookies()

        with open(cookies_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)

    def get_answer(self, prompt: str, file_path: str = None):

        # Имя сессии из пути
        session_name = self.session_path.stem
        download_dir = None
        if self.download_folder:
            download_dir = Path(self.download_folder) / session_name
            download_dir.mkdir(parents=True, exist_ok=True)

        # Вводим текст
        element = self.driver.find_element(By.ID, "prompt-textarea")

        self.driver.execute_script("""
        arguments[0].focus();
        document.execCommand('insertText', false, arguments[1]);
        """, element, prompt)
        self.human_pause(0.2, 0.5)

        # Добавляем файл, если есть
        if file_path:
            self.add_file(file_path)

        # Ждём пока кнопка отправки станет активной
        send_btn = WebDriverWait(self.driver, 25).until(
            lambda d: d.find_element(By.ID, "composer-submit-button")
            if "composer-submit-button-color" in d.find_element(By.ID, "composer-submit-button").get_attribute("class")
            else False
        )

        self.human_pause(0.2, 0.5)
        self.driver.execute_script("arguments[0].click();", send_btn)

        # 🔹 Ждём, пока генерация закончится (кнопка голосового режима станет активной)
        WebDriverWait(self.driver, 60).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[aria-label='Запустить голосовой режим']")
            )
        )

        # Ждём ещё немного для стабильности рендеринга
        self.human_pause(2, 3)

        # Получаем последний article (последний ответ)
        articles = WebDriverWait(self.driver, 60).until(
            lambda d: d.find_elements(By.TAG_NAME, "article") or False
        )

        last_article = articles[-1]

        # Собираем весь текст из <p>
        text_blocks = last_article.find_elements(By.TAG_NAME, "p")
        full_text = "\n".join([tb.text for tb in text_blocks if tb.text.strip() != ""])

        # Собираем все изображения
        imgs = last_article.find_elements(By.TAG_NAME, "img")
        downloaded_images = []
        for img in imgs:
            img_url = img.get_attribute("src")
            if download_dir and img_url:
                filename = os.path.basename(urlparse(img_url).path)
                file_path = download_dir / filename
                try:
                    r = requests.get(img_url, stream=True)
                    if r.status_code == 200:
                        with open(file_path, "wb") as f:
                            for chunk in r.iter_content(1024):
                                f.write(chunk)
                        downloaded_images.append(str(file_path))
                except Exception as e:
                    print(f"Ошибка при скачивании {img_url}: {e}")
            else:
                downloaded_images.append(img_url)

        return {
            "text": full_text,
            "images_paths": downloaded_images
        }



    def create_new_chat_in_folder(self, folder_name):
        project = self.find_project_by_name(folder_name)
        if(project != None):
            project.click()
            self.human_pause(0.5, 1)


    def create_folder_for_asking(self, folder_name: str):
        """
        Создаёт новый проект/чат с указанным именем.
        Всё обёрнуто в WebDriverWait 12 секунд.
        """

        wait = WebDriverWait(self.driver, 12)

        try:
            # Пытаемся нажать основную кнопку "Новый проект"
            new_project_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="stage-slideover-sidebar"]/div/div[2]/nav/div[6]/div'))
            )
            new_project_btn.click()
            time.sleep(8)
        except Exception:
            # Если не удалось, пробуем альтернативную кнопку
            alt_project_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="stage-slideover-sidebar"]/div/div[2]/nav/div[5]/button'))
            )
            self.driver.execute_script("arguments[0].click();", alt_project_btn)
            new_project_btn = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[@id="stage-slideover-sidebar"]/div/div[2]/nav/div[6]/div'))
            )
            new_project_btn.click()

        # Поле ввода названия проекта
        input_folder_name = wait.until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="project-modal-form"]/div[1]/div/input'))
        )
        self.driver.execute_script("arguments[0].click();", input_folder_name)
        self.type_like_human(input_folder_name, folder_name)

        # Кнопка создания проекта
        create_btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="project-modal-form"]/div[2]/div/button'))
        )
        self.driver.execute_script("arguments[0].click();", create_btn)

        # Ждём появления проекта в списке
        project = self.find_project_by_name(folder_name, 12)

        if project is not None:
            self.go_home()
            return True
        return False

    def get_folder_for_asking_from_link(self, folder_link:str):

        pass

    def share_folder_for_asking(self) -> str:
        pass

    def type_like_human(self, element, text, min_delay=0.02, max_delay=0.06):
        """
        Эмулирует человеческий ввод текста посимвольно.
        """
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(min_delay, max_delay))

    def human_pause(self, min:float = 0.3, max: float = 2):
        time.sleep(random.uniform(min,max))

    def go_home(self):
        self.driver.find_element(By.XPATH, '//*[@id="sidebar-header"]/a').click()

    def find_project_by_name(self, project_name: str, wait_time: int = 10) -> WebElement | None:
        """
        Ищет проект в боковой панели по имени.
        Возвращает WebElement проекта или None, если не найден.
        """
        wait = WebDriverWait(self.driver, wait_time)
        try:
            # Ждем появления хотя бы одного элемента проекта
            wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '[data-sidebar-item="true"]'))

            # Получаем все проекты
            projects = self.driver.find_elements(By.CSS_SELECTOR, '[data-sidebar-item="true"]')
            for project in projects:
                try:
                    title_element = project.find_element(By.CLASS_NAME, "truncate")
                    if title_element.text.strip() == project_name:
                        # Скроллим к элементу и возвращаем его
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", project)
                        return project
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def add_file(self, file_path: str):
        """
           Загружает файл в чат, обходя окно выбора файлов.
           file_path: абсолютный путь к файлу на диске
           """
        # Ждём появление кнопки "плюс"
        plus_btn = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button#composer-plus-btn'))
        )

        # Нажимаем кнопку "плюс", чтобы DOM создал <input type="file">
        self.driver.execute_script("arguments[0].click();", plus_btn)
        self.human_pause(0.2, 0.5)

        # Находим скрытый input type=file
        file_input = WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[type="file"][style*="display: none"], input[type="file"][hidden]'))
        )

        # Загружаем файл
        file_input.send_keys(file_path)
        self.human_pause(0.5, 1)