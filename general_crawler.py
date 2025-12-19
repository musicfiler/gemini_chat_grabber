# general_crawler.py
# Version: 3.0
import time
import json
import os
import trafilatura
from datetime import datetime
from playwright.sync_api import sync_playwright
from database_manager import DatabaseManager


class GeneralCrawlerProcess:
    def __init__(self, urls, log_queue, config_file="config.json"):
        self.urls = urls
        self.queue = log_queue
        self.config_file = config_file
        with open(config_file, "r") as f:
            self.config = json.load(f)

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.queue.put(f"[GENERAL {timestamp}] {msg}")

    def run(self):
        self.log("Prozess gestartet.")
        db = DatabaseManager(self.config_file)
        cookie_path = self.config.get("cookie_file", "auth_state.json")

        with sync_playwright() as p:
            headless_mode = not self.config.get("browser_visible", True)
            browser = p.chromium.launch(headless=headless_mode)

            context_args = {"user_agent": self.config.get("user_agent")}
            if os.path.exists(cookie_path):
                context_args["storage_state"] = cookie_path

            context = browser.new_context(**context_args)
            page = context.new_page()

            for url in self.urls:
                if not url.strip(): continue
                self.log(f"Besuche: {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    # Warte kurz für dynamischen Content
                    time.sleep(2)

                    # 1. Screenshot (Optional, hier nur Logik Platzhalter)
                    # page.screenshot(path=f"screenshot_{i}.png")

                    # 2. HTML holen für Trafilatura
                    content_html = page.content()

                    # 3. Extraktion mit Trafilatura (Bester Text-Extraktor)
                    cleaned_text = trafilatura.extract(content_html)

                    if cleaned_text:
                        # Wir speichern HTML + Text
                        final_content = f"\n<pre>{cleaned_text}</pre>\n\n{content_html}"
                        title = page.title()
                        db.save_content(url, title, final_content, "GeneralCrawler")
                        self.log(f" -> Gespeichert: {title}")
                    else:
                        self.log(" -> Warnung: Kein Text extrahiert.")

                except Exception as e:
                    self.log(f"Fehler bei {url}: {e}")

            browser.close()
        self.log("Fertig.")