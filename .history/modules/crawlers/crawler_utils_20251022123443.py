# crawler/utils.py
import re
import os
import json
import time
import logging
from functools import lru_cache
from selenium.webdriver.common.by import By


# =========================
# 🧭 日志配置
# =========================

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# =========================
# 🖱️ 通用操作工具
# =========================


def safe_click(driver, element, delay: float = 0.3) -> None:
    """
    滚动并点击指定元素。

    Args:
        driver (selenium.webdriver): 浏览器 WebDriver
        element (WebElement): 需要点击的元素
        delay (float): 点击前等待时间（秒）

    Notes:
        - 使用 JS click 增强点击成功率
        - 自动滚动到元素可视区域
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(delay)
        driver.execute_script("arguments[0].click();", element)
    except Exception as e:
        print(f"⚠️ safe_click failed: {e}")


def extract_text_safe(element_or_driver, selector: str, default="Unknown"):
    """
    安全提取元素文本，可自动判断使用 XPath 或 CSS 选择器。

    Args:
        element_or_driver (WebDriver | WebElement): Selenium 对象
        selector (str): XPath 或 CSS 选择器
        default (str): 提取失败时的默认返回值

    Returns:
        str: 提取到的文本，失败则返回 default。
    """
    try:
        if selector.strip().startswith("//") or selector.strip().startswith(".//"):
            el = element_or_driver.find_element(By.XPATH, selector)
        else:
            el = element_or_driver.find_element(By.CSS_SELECTOR, selector)
        return el.text.strip()
    except Exception:
        return default


def clean_traveler_name(name: str) -> str:
    """
    清洗旅客姓名，去除括号及多余空格。

    Args:
        name (str): 原始姓名

    Returns:
        str: 清洗后的姓名
    """
    return re.sub(r"\s*\(.*?\)\s*", "", name).strip()


# =========================
# 🏷️ 团名匹配相关
# =========================


def match_group_name(title: str, package: str, log_unmatched: bool = False) -> str:
    """
    根据 title 和 package 内容匹配对应的团代码。
    优先按关键词出现总次数，其次按匹配关键词数量。

    Args:
        title (str): 团的标题
        package (str): 套餐选项描述
        log_unmatched (bool): 当未匹配到团名时是否记录日志

    Returns:
        str: 团代码（如未匹配则返回 'Unknown'）
    """
    KEYWORDS_MAP = get_group_keywords_map()

    text = f"{title or ''} {package or ''}".lower()
    best_match = "Unknown"
    best_score = (-1, -1)  # (occurrences, match_count)

    for code, keywords in KEYWORDS_MAP.items():
        match_count = sum(1 for kw in keywords if kw.lower() in text)
        occurrences = sum(text.count(kw.lower()) for kw in keywords)
        score = (occurrences, match_count)
        if score > best_score:
            best_score = score
            best_match = code

    if best_match == "Unknown" and log_unmatched:
        print(f"⚠️ 未匹配团名: {title} | {package}")
    return best_match


# =========================
# 🧾 团名关键词配置加载
# =========================


@lru_cache(maxsize=1)
def load_group_data() -> dict:
    """
    加载 config/groups.json 配置文件，只加载一次（使用 LRU 缓存）。

    Returns:
        dict: JSON 文件内容，若加载失败返回空字典。

    Raises:
        FileNotFoundError: 当配置文件不存在时记录日志但不抛出。
    """
    file_path = os.path.join(os.path.dirname(__file__), "../../config/groups.json")
    file_path = os.path.abspath(file_path)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"❌ groups.json not found at {file_path}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"❌ 解析 groups.json 失败: {e}")
        return {}


def get_group_keywords_map() -> dict:
    """
    获取关键词映射表。

    Returns:
        dict: 团名关键词映射
    """
    return load_group_data().get("keywords", {})


def get_group_fullname_EN_map() -> dict:
    """
    获取团名英文全称映射表。

    Returns:
        dict: 团代码 -> 英文全称 映射
    """
    return load_group_data().get("fullname_EN", {})


def get_group_fullname_CN_map() -> dict:
    """
    获取团名中文全称映射表。

    Returns:
        dict: 团代码 -> 中文全称 映射
    """
    return load_group_data().get("fullname_CN", {})
