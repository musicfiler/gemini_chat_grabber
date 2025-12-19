# auth_handler.py
# Version: 6.0 (Clean & Simple - User Agent Only)
import json
import os
from playwright.sync_api import sync_playwright


class AuthHandler:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        try:
            with open(config_file, "r") as f:
                self.config = json.load(f)
        except:
            self.config = {}
        self.cookie_file = self.config.get("cookie_file", "auth_state.json")

    def open_browser_for_login(self):
        """Öffnet Browser mit Standard User-Agent ohne komplexe Stealth-Skripte."""
        print(f"Starte Login-Browser (Basis Modus)...")

        with sync_playwright() as p:
            # Das ist der einzige wirklich wichtige Switch:
            # Er sagt Chrome: "Melde nicht, dass du von Software gesteuert wirst."
            args = [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]

            # Wir starten einen sichtbaren Browser
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",  # Versucht den echten installierten Chrome zu nehmen
                args=args
            )

            # Ein ganz normaler, aktueller Chrome User-Agent
            real_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=real_user_agent
            )

            # Minimaler JS-Tweak, oft notwendig
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = context.new_page()

            try:
                print("Lade Google Login...")
                # Wir gehen zur Account-Seite
                page.goto("https://accounts.google.com/ManageAccount", wait_until="domcontentloaded")

                print("\n--- ANLEITUNG ---")
                print("1. Bitte jetzt anmelden.")
                print("2. Wenn Sie eingeloggt sind -> Fenster schließen.")
                print("-----------------")

                # Warten bis Fenster zu ist
                try:
                    page.wait_for_event("close", timeout=0)
                except:
                    pass

                    # Speichern
                context.storage_state(path=self.cookie_file)
                print(f"✅ Login-Daten gespeichert in {self.cookie_file}")

            except Exception as e:
                print(f"❌ Fehler: {e}")
            finally:
                try:
                    browser.close()
                except:
                    pass

        return "Login-Vorgang beendet."