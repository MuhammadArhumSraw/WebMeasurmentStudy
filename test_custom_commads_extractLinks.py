from selenium import webdriver
from selenium.webdriver.firefox.options import Options

from custom_commands import CookieConsentCommand, ExtractLinksCommand

# Fake objects (OpenWPM normally provides these)
browser_params = None
manager_params = type("obj", (), {"data_directory": "./datadir"})
extension_socket = None

# Setup browser
options = Options()
options.headless = False  # set True if you want
driver = webdriver.Firefox(options=options)

# Test URL
url = "https://google.com"
driver.get(url)

# --- TEST COOKIE COMMAND ---
cookie_cmd = CookieConsentCommand()
cookie_cmd.execute(driver, browser_params, manager_params, extension_socket)

# --- TEST LINK EXTRACTION ---
extract_cmd = ExtractLinksCommand(base_url=url, max_links=5)
extract_cmd.execute(driver, browser_params, manager_params, extension_socket)

driver.quit()