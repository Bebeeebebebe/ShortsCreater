import threading
import undetected_chromedriver as uc
import os
# pip install keyboard
import keyboard
import pickle
import subprocess
from urllib.parse import urlparse
import time
class AccountLogger:
    def __init__(self, account_name: str, site_key: str):
        self.account_name = account_name

        self.TARGET_SITES = {
            "YouTube": "https://www.youtube.com",
            "TikTok": "https://www.tiktok.com",
            "ChatGPT": "https://chatgpt.com/"
        }

        if site_key not in self.TARGET_SITES:
            raise ValueError("Сайт пока не поддерживается")

        self.target_url = self.TARGET_SITES[site_key]

        self.driver = None
        self.running = False

    def get_site_folder_name(self) -> str:
        parsed = urlparse(self.target_url)
        domain = parsed.netloc

        if isinstance(domain, bytes):
            domain = domain.decode("utf-8")

        domain = domain.lower().replace("www.", "")
        return domain.split(".")[0]


    def start_driver(self):
        import subprocess

        options = uc.ChromeOptions()

        # Определяем версию Chrome
        try:
            output = subprocess.check_output(
                r'reg query "HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon" /v version',
                shell=True, text=True
            )
            version = output.strip().split()[-1]
            main_version = int(version.split(".")[0])
            print(f"Используем Chrome версии {version}")
        except:
            main_version = None
            print("Не удалось определить версию Chrome, используем дефолт")

        # Передаём версию в uc
        self.driver = uc.Chrome(version_main=main_version, options=options)
        self.driver.maximize_window()

    def open_target_site(self):
        self.driver.get(self.target_url)

    # -------------------------
    # Хоткей без пауз вообще
    # -------------------------

    def hotkey_listener(self):
        HOTKEY = "ctrl+shift+q"

        print(f"Слушаю {HOTKEY} ...")

        try:
            keyboard.add_hotkey(HOTKEY, self.on_exit)

            while self.running:
                time.sleep(0.5)

        except Exception as e:
            print("Ошибка хоткея:", e)

    def on_exit(self):
        print("Хоткей нажат → инициализация закрытия браузера")

        cookies = self.driver.get_cookies()

        local_storage = self.driver.execute_script("""
        var items = {};
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
        }
        return items;
        """)

        # Получаем имя сайта (tiktok / youtube)
        site_folder = self.get_site_folder_name()

        # Accounts/tiktok/
        base_folder = os.path.join("Accounts", site_folder)
        os.makedirs(base_folder, exist_ok=True)

        # Accounts/tiktok/account_name.pkl
        file_path = os.path.join(base_folder, f"{self.account_name}.pkl")

        session_data = {
            "cookies": cookies,
            "local_storage": local_storage
        }

        with open(file_path, "wb") as file:
            pickle.dump(session_data, file)
        print(f"Cookies сохранены в: {file_path}")

        self.stop()

    # -------------------------
    # Запуск
    # -------------------------

    def run(self):
        self.running = True

        self.start_driver()
        self.open_target_site()

        threading.Thread(
            target=self.hotkey_listener,
            daemon=True
        ).start()

        print("Браузер открыт. ")

        while self.running:
            pass  # можно заменить на Event.wait()

    def stop(self):
        self.running = False

        if self.driver:
            self.driver.quit()
            self.driver = None
