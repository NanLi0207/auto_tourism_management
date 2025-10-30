"""
browser.py
========================
用于管理 Selenium 浏览器的初始化与关闭。
采用全局单例，避免重复打开多个浏览器窗口。

注意事项：
- 推荐使用 Chrome 浏览器
- 需要提前安装对应版本的 chromedriver
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from .config import SELENIUM_SHORT_WAIT

# 全局 driver 与 wait 对象
driver = None
wait = None


def init_driver():
    """
    初始化全局浏览器对象（单例）
    ------------------------
    - 语言设置为英文，避免 Google Maps 页面多语言影响 XPath 定位
    - 使用无痕模式，避免缓存干扰
    - 禁用地理位置弹窗

    Returns:
        webdriver.Chrome 对象
    """
    global driver, wait
    if driver:
        return driver

    opts = Options()
    opts.add_argument("--lang=en")  # 使用英文界面
    opts.add_argument("--incognito")  # 无痕模式
    opts.add_experimental_option(
        "prefs", {"profile.default_content_setting_values.geolocation": 2}
    )
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, SELENIUM_SHORT_WAIT)
    return driver


def quit_driver():
    """
    关闭全局浏览器对象
    ------------------------
    - 在程序结束时调用，释放资源。
    """
    global driver
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        driver = None
