# modules/utils/browser_connector.py
# =====================================================
# 🌐 Chrome 浏览器调试模式连接工具
# -----------------------------------------------------
# - 支持启动带远程调试端口的 Chrome
# - 支持 Selenium 接管已启动的浏览器
# - 自动设置下载目录，无弹窗
# - 提供关闭所有 Chrome 的功能
# =====================================================

import subprocess
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# =====================================================
# ⚙️ 全局配置
# =====================================================
DEFAULT_PORT: int = 9222
DEFAULT_USER_DATA_DIR: str = r"C:\chrome-debug"
DEFAULT_DOWNLOAD_DIR: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../downloads/")
)


# =====================================================
# 🚀 启动 Chrome 浏览器（带远程调试端口）
# =====================================================
def start_chrome_with_debug(
    port: int = DEFAULT_PORT,
    user_data_dir: str = DEFAULT_USER_DATA_DIR,
    chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
) -> None:
    """
    启动 Chrome 并开启远程调试模式，同时预设下载目录。

    该函数通过 `--remote-debugging-port` 启动 Chrome，
    并指定用户数据目录，以便之后通过 Selenium 接管现有浏览器。
    适用于需要登录后自动化操作的场景（如爬虫）。

    Args:
        port (int, optional): 调试端口号，默认为 9222。
        user_data_dir (str, optional): Chrome 用户数据存储路径。
        chrome_path (str, optional): Chrome 浏览器可执行文件路径。
        download_dir (str, optional): 文件下载目录，默认为 ../downloads/。

    Raises:
        FileNotFoundError: 当未找到 Chrome 可执行文件时抛出异常。
    """

    # 1️⃣ 检查 Chrome 路径
    if not os.path.exists(chrome_path):
        alt_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        if os.path.exists(alt_path):
            chrome_path = alt_path
        else:
            raise FileNotFoundError("❌ 找不到 Chrome 浏览器")

    # 2️⃣ 确保用户数据目录和下载目录存在
    os.makedirs(user_data_dir, exist_ok=True)
    os.makedirs(download_dir, exist_ok=True)

    # 3️⃣ 启动 Chrome
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        "--force-device-scale-factor=1",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        "--disable-save-password-bubble",
        "--safebrowsing-disable-download-protection",
    ]

    subprocess.Popen(cmd, shell=True)
    print(f"🚀 已启动 Chrome（调试端口 {port}），下载目录：{download_dir}")
    time.sleep(2)


# =====================================================
# 🤝 接管现有浏览器 + 自动下载设置
# =====================================================
def connect_to_existing_browser(
    debugger_address: str = f"127.0.0.1:{DEFAULT_PORT}",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
) -> webdriver.Chrome:
    """
    使用 Selenium 接管已启动的 Chrome 浏览器，并设置自动下载目录。

    通过 Chrome DevTools Protocol (CDP)，禁用下载弹窗并允许文件自动保存。
    适用于需要登录后再自动化的场景。

    Args:
        debugger_address (str, optional): Chrome 调试地址（IP:Port），默认 127.0.0.1:9222。
        download_dir (str, optional): 下载目录路径。

    Returns:
        webdriver.Chrome: 已接管的 Chrome WebDriver 对象。
    """

    options = Options()
    options.debugger_address = debugger_address

    # ✅ 设置下载相关偏好
    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--start-maximized")

    # ✅ 连接到已有 Chrome
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )

    # ✅ 使用 DevTools 协议设置自动下载行为
    driver.execute_cdp_cmd(
        "Page.setDownloadBehavior",
        {
            "behavior": "allow",
            "downloadPath": os.path.abspath(download_dir),
        },
    )

    print(f"✅ 已接管浏览器，下载目录：{download_dir}")
    return driver


# =====================================================
# 🧹 关闭所有 Chrome
# =====================================================
def close_all_chrome() -> None:
    """
    关闭所有正在运行的 Chrome 浏览器进程（Windows）。

    使用 `taskkill` 命令强制关闭所有 chrome.exe 进程。
    适用于清理卡住的浏览器进程。
    """
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "chrome.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("🧹 已关闭所有 Chrome 浏览器进程")
    except Exception as e:
        print(f"⚠️ 无法关闭 Chrome：{e}")
