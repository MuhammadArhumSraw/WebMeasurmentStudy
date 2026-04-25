import logging
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

from custom_commands import CookieConsentCommand

# -----------------------------
# Fake OpenWPM objects
# -----------------------------
class DummyManagerParams:
    data_directory = "./datadir"

browser_params = None
manager_params = DummyManagerParams()
extension_socket = None

# -----------------------------
# Logging (IMPORTANT)
# -----------------------------
logging.basicConfig(level=logging.INFO)

# -----------------------------
# Start browser
# -----------------------------
options = Options()
options.headless = False  # set True if you want

driver = webdriver.Firefox(options=options)

# -----------------------------
# Test sites (rotate these)
# -----------------------------
test_sites = [
  "https://www.formula1.com"
]

for url in test_sites:
    print(f"\n=== Testing: {url} ===")

    driver.get(url)

    # Let page + banner load
    import time
    time.sleep(5)

    # 🔥 CALL YOUR COMMAND (same as OpenWPM)
    cmd = CookieConsentCommand()
    cmd.execute(driver, browser_params, manager_params, extension_socket)

    # Pause so you can visually confirm
    input("Check browser → Press Enter to continue...")

driver.quit()