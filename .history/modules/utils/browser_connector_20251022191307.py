# modules/browser_connector.py
import subprocess
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ===============================
# 全局配置
# ===============================
DEFAULT_PORT = 9222
DEFAULT_USER_DATA_DIR = r"C:\chrome-debug"
DEFAULT_DOWNLOAD_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../downloads/")
)


# ===============================
# 启动 Chrome
# ===============================
def start_chrome_with_debug(
    port: int = DEFAULT_PORT,
    user_data_dir: str = DEFAULT_USER_DATA_DIR,
    chrome_path: str = r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
):
    """
    启动 Chrome 并开启远程调试 + 自动下载（不弹 Save As）
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

    # 3️⃣ 启动 Chrome，预设下载路径（✨ 核心）
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-popup-blocking",
        f"--force-device-scale-factor=1",
        f"--enable-features=NetworkService,NetworkServiceInProcess",
        "--disable-save-password-bubble",
        "--safebrowsing-disable-download-protection",
    ]

    # 👇 关键：告诉 Chrome 默认下载路径（防止 Save As 弹窗）
    cmd.append(f"--download.default_directory={os.path.abspath(download_dir)}")

    subprocess.Popen(cmd, shell=True)
    print(f"🚀 已启动 Chrome（调试端口 {port}），自动下载目录：{download_dir}")
    time.sleep(2)


# ===============================
# 接管 Chrome
# ===============================
def connect_to_existing_browser(
    debugger_address: str = f"127.0.0.1:{DEFAULT_PORT}",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
):
    """
    接管已启动的 Chrome，并配置自动下载目录
    """
    options = Options()
    options.debugger_address = debugger_address

    # ✅ 这段是最关键的，确保不弹 Save As
    prefs = {
        "download.default_directory": os.path.abspath(download_dir),
        "download.prompt_for_download": False,  # ✅ 不弹 Save As
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )
    print(f"✅ 已接管浏览器：{driver.title}")
    return driver


# ===============================
# 关闭所有 Chrome
# ===============================
def close_all_chrome():
    """
    关闭所有正在运行的 Chrome 浏览器窗口
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
