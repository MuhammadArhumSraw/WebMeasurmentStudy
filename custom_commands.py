import logging
import json
from os import path
from urllib.parse import urlparse
from pathlib import Path
import time
from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains

from openwpm.commands.types import BaseCommand
from openwpm.config import BrowserParams, ManagerParams
from openwpm.socket_interface import ClientSocket

from urllib.parse import urlparse

def safe_site_name(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")  # normalize
    return domain
class ExtractLinksCommand(BaseCommand):
    def __init__(self, base_url: str = "", max_links: int = 50) -> None:
        self.logger = logging.getLogger("openwpm")
        self.base_url = base_url
        self.max_links = max_links

    def __repr__(self) -> str:
        return "ExtractLinksCommand"

    # ─────────────────────────────────────────────
    # WAIT FOR STABLE DOM (CRITICAL FIX)
    # ─────────────────────────────────────────────
    def _wait_for_dom_stability(self, driver, timeout=10):
        last_count = 0

        for _ in range(timeout):
            try:
                links = driver.find_elements(By.TAG_NAME, "a")
                count = len(links)

                if count == last_count:
                    return
                last_count = count

                time.sleep(1)
            except:
                time.sleep(1)

    # ─────────────────────────────────────────────
    # SAFE LINK COLLECTION
    # ─────────────────────────────────────────────
    def _collect_links(self, driver):
        links = set()

        # MAIN PAGE
        for a in driver.find_elements(By.TAG_NAME, "a"):
            try:
                href = a.get_attribute("href")
                if href and href.startswith("http"):
                    links.add(href)
            except:
                continue

        # IFRAMES
        iframes = driver.find_elements(By.TAG_NAME, "iframe")

        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)

                for a in driver.find_elements(By.TAG_NAME, "a"):
                    try:
                        href = a.get_attribute("href")
                        if href and href.startswith("http"):
                            links.add(href)
                    except:
                        continue

                driver.switch_to.default_content()

            except:
                driver.switch_to.default_content()
                continue

        return list(links)

    # ─────────────────────────────────────────────
    # MAIN EXECUTION
    # ─────────────────────────────────────────────
    def execute(
        self,
        webdriver,
        browser_params: BrowserParams,
        manager_params: ManagerParams,
        extension_socket: ClientSocket,
    ) -> None:

        self.logger.info("Extracting links from %s", webdriver.current_url)

        # IMPORTANT FIX: let JS finish rendering
        #time.sleep(5)
        self._wait_for_dom_stability(webdriver, timeout=10)
        #time.sleep(5)

        links = self._collect_links(webdriver)[: self.max_links]

        # SAVE
        safe_name = safe_site_name(webdriver.current_url)

        print(safe_name)
        import os

        out_dir = Path(manager_params.data_directory) / "links"
        os.makedirs(out_dir, exist_ok=True)

        out_path = out_dir / f"{safe_name}.json"

        print(f"Saving {len(links)} links to {out_path}...")

        with open(out_path, "w") as f:
            json.dump({"links": links}, f)
            f.flush()
            os.fsync(f.fileno())

        self.logger.info("Saved %d links → %s", len(links), out_path)
        

        print("LOOKING FOR:", out_path)
        print("EXISTS:", out_path.exists())


        return links

class CookieConsentCommand(BaseCommand):

    def __init__(self) -> None:
        self.logger = logging.getLogger("openwpm")

    def __repr__(self) -> str:
        return "CookieConsentCommand"

    # -----------------------------
    # CLICK LOGIC
    # -----------------------------
    def _try_click(self, webdriver):
        with open("accept_words.txt", "r") as f:
            keywords = [line.strip().lower() for line in f if line.strip()]
        

        elements = webdriver.find_elements(By.XPATH, "//button | //a | //*[@role='button']")

        for el in elements:
            try:
                text = (el.text or "").lower()
                aria = (el.get_attribute("aria-label") or "").lower()
                html = (el.get_attribute("innerHTML") or "").lower()

                combined = f"{text} {aria} {html}"

                if any(k in combined.split() for k in keywords):
                    print(el.text)
                    self.logger.info(f"CLICKING: {combined[:80]}")

                    webdriver.execute_script("arguments[0].click();", el)
                    return True

            except Exception:
                continue

        return False

    # -----------------------------
    # IFRAME HANDLER (THIS WAS MISSING)
    # -----------------------------
    def _handle_iframes(self, webdriver, depth=0, max_depth=3):
        if depth > max_depth:
            return False

        iframes = webdriver.find_elements(By.TAG_NAME, "iframe")

        for iframe in iframes:
            try:
                webdriver.switch_to.frame(iframe)

                self.logger.info(f"Switched to iframe depth={depth}")

                if self._try_click(webdriver):
                    webdriver.switch_to.default_content()
                    return True

                if self._handle_iframes(webdriver, depth + 1, max_depth):
                    webdriver.switch_to.default_content()
                    return True

                webdriver.switch_to.default_content()

            except Exception:
                webdriver.switch_to.default_content()
                continue

        return False

    # -----------------------------
    # OPENWPM ENTRY POINT
    # -----------------------------
    def execute(self, webdriver: Firefox,
                browser_params: BrowserParams,
                manager_params: ManagerParams,
                extension_socket: ClientSocket) -> None:

        self.logger.info("Handling cookie consent (iframe-aware)...")

        time.sleep(3)

        if self._try_click(webdriver):
            return

        if self._handle_iframes(webdriver):
            return

        self.logger.info("No cookie consent found.")

class SleepCommand(BaseCommand):
    def __init__(self, seconds: int = 3):
        self.seconds = seconds
        self.logger = logging.getLogger("openwpm")

    def __repr__(self):
        return f"SleepCommand({self.seconds}s)"

    def execute(
        self,
        webdriver: Firefox,
        browser_params: BrowserParams,
        manager_params: ManagerParams,
        extension_socket: ClientSocket,
    ) -> None:

        self.logger.info("Sleeping for %s seconds...", self.seconds)
        time.sleep(self.seconds)