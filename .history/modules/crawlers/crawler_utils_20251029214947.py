# crawler/utils.py
# =====================================================
# 🧰 通用工具函数模块
# - 日志配置
# - Selenium 通用点击与提取文本
# - 团名关键词匹配工具
# - 汉字检测与姓名拼音转换
# =====================================================

import re
import os
import json
import time
import logging
import string
from functools import lru_cache
from typing import Union, Dict, Any

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from pypinyin import lazy_pinyin

# =====================================================
# 🧭 日志配置
# =====================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# =====================================================
# 🖱️ 通用 Selenium 操作
# =====================================================


def safe_click(driver: WebDriver, element: WebElement, delay: float = 0.3) -> None:
    """
    滚动到元素并安全点击（使用 JS click 提高点击成功率）。

    Args:
        driver (WebDriver): Selenium 浏览器驱动。
        element (WebElement): 需要点击的目标元素。
        delay (float, optional): 点击前的等待时间（秒）。默认 0.3 秒。

    Notes:
        - 自动滚动到元素可见区域。
        - 使用 JavaScript 执行点击，避免普通 click 的异常。
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(delay)
        driver.execute_script("arguments[0].click();", element)
    except Exception as e:
        logger.warning(f"⚠️ safe_click failed: {e}")


def extract_text_safe(
    element_or_driver: Union[WebDriver, WebElement],
    selector: str,
    default: str = "Unknown",
) -> str:
    """
    安全提取元素文本，可自动判断 XPath 或 CSS 选择器。

    Args:
        element_or_driver (WebDriver | WebElement): Selenium 对象。
        selector (str): XPath 或 CSS 选择器。
        default (str, optional): 提取失败时的默认值。默认为 "Unknown"。

    Returns:
        str: 提取到的文本，失败时返回 default。
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
    清洗旅客姓名，移除括号和多余空格。

    Args:
        name (str): 原始姓名字符串。

    Returns:
        str: 清洗后的姓名。
    """
    return re.sub(r"\s*\(.*?\)\s*", "", name).strip()


# =====================================================
# 🏷️ 团名匹配工具
# =====================================================


def match_group_name(title: str, package: str, log_unmatched: bool = False) -> str:
    """
    根据标题和套餐描述匹配团代码。

    优先级：
        1. 匹配关键词总出现次数。
        2. 匹配到的关键词数量。

    Args:
        title (str): 团名称或标题。
        package (str): 套餐描述。
        log_unmatched (bool, optional): 是否在未匹配时输出警告日志。默认为 False。

    Returns:
        str: 匹配到的团代码；未匹配时返回 "Unknown"。
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
        logger.warning(f"⚠️ 未匹配团名: {title} | {package}")

    return best_match


# =====================================================
# 📄 团名关键词配置加载
# =====================================================


@lru_cache(maxsize=1)
def load_group_data() -> Dict[str, Any]:
    """
    加载 `config/groups.json` 配置文件（使用 LRU 缓存，只加载一次）。

    Returns:
        dict: JSON 配置内容；加载失败时返回空字典。

    Raises:
        FileNotFoundError: 如果文件不存在，会记录错误日志但不会中断程序。
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


def get_group_keywords_map() -> Dict[str, list]:
    """
    获取团名关键词映射表。

    Returns:
        dict: 团代码 -> 关键词列表
    """
    return load_group_data().get("keywords", {})


def get_group_fullname_EN_map() -> Dict[str, str]:
    """
    获取团名英文全称映射表。

    Returns:
        dict: 团代码 -> 英文全称
    """
    return load_group_data().get("fullname_EN", {})


def get_group_fullname_CN_map() -> Dict[str, str]:
    """
    获取团名中文全称映射表。

    Returns:
        dict: 团代码 -> 中文全称
    """
    return load_group_data().get("fullname_CN", {})


# =====================================================
# 🈶 汉字判断与拼音转换
# =====================================================

HAN_RANGES = [
    (0x3400, 0x4DBF),  # CJK Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2B73F),  # Extension C
    (0x2B740, 0x2B81F),  # Extension D
    (0x2B820, 0x2CEAF),  # Extension E
    (0x2CEB0, 0x2EBEF),  # Extension F
    (0x30000, 0x3134F),  # Extension G
    (0x31350, 0x323AF),  # Extension H
    (0x2EBF0, 0x2EE5F),  # Extension I
    (0x2F800, 0x2FA1F),  # Compatibility Ideographs Supplement
]

COMPOUND_SURNAMES = [
    "欧阳",
    "司马",
    "诸葛",
    "东方",
    "夏侯",
    "皇甫",
    "尉迟",
    "上官",
    "长孙",
    "慕容",
]


def is_han_char(ch: str) -> bool:
    """
    判断单个字符是否为汉字（CJK 表意文字）。

    Args:
        ch (str): 待检测字符。

    Returns:
        bool: 是否为汉字。
    """
    if not ch:
        return False
    cp = ord(ch)
    return any(start <= cp <= end for start, end in HAN_RANGES)


def has_han(s: str) -> bool:
    """
    判断字符串中是否包含至少一个汉字。

    Args:
        s (str): 待检测字符串。

    Returns:
        bool: 是否包含汉字。
    """
    if not s:
        return False
    if s.isascii():
        return False
    return any(is_han_char(ch) for ch in s)


def all_han(s: str, ignore_space: bool = True) -> bool:
    """
    判断字符串是否全部为汉字。

    Args:
        s (str): 待检测字符串。
        ignore_space (bool, optional): 是否忽略空格。默认为 True。

    Returns:
        bool: 是否全部为汉字。
    """
    if not s:
        return False
    if ignore_space:
        s = "".join(ch for ch in s if not ch.isspace())
    return s != "" and all(is_han_char(ch) for ch in s)


def chinese_name_to_english(name: str) -> str:
    """
    将中文姓名转换为英文拼音形式。

    规则：
        - 如果姓名中不包含汉字，则首字母大写返回英文名。
        - 复姓优先匹配（如“欧阳修” -> “Xiu Ouyang”）。
        - 单姓（如“张三” -> “San Zhang”）。

    Args:
        name (str): 姓名字符串。

    Returns:
        str: 转换后的英文拼音姓名。
    """
    name = name.strip()
    if not has_han(name):
        return string.capwords(name.replace("/", " "))

    # 优先复姓匹配
    surname = None
    for s in COMPOUND_SURNAMES:
        if name.startswith(s):
            surname = s
            break

    if surname:
        given = name[len(surname) :]
        pinyin_surname = "".join(lazy_pinyin(surname))
        pinyin_given = "".join(lazy_pinyin(given))
        full = f"{pinyin_given} {pinyin_surname}"
    else:
        pinyins = lazy_pinyin(name)
        if len(pinyins) <= 1:
            return string.capwords("".join(pinyins))
        given_name = "".join(pinyins[1:])
        surname = pinyins[0]
        full = f"{given_name} {surname}"

    return string.capwords(full)
