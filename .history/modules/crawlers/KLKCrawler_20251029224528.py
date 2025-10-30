# modules/crawler_KLK.py
# =======================================================
# 📄 KLOOK 平台订单爬虫
# 工程化 + 注释补全 + 统一结构
# =======================================================
import re
import time
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    ElementClickInterceptedException,
)
from modules.crawlers.BaseCrawler import BaseCrawler
from modules.crawlers.crawler_utils import (
    safe_click,
    extract_text_safe,
    match_group_name,
)
from modules.utils.output_utils import extract_country_code_from_phone

# ✅ 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class KLKCrawler(BaseCrawler):
    """
    🧭 KLKCrawler
    用于爬取 KLOOK 平台订单信息。

    功能：
    - 登录 & 日期筛选
    - 翻页采集
    - 解析订单字段（姓名、电话、人数、酒店、语言、团名、日期）
    """

    def open_page(self) -> None:
        """
        打开 KLOOK 页面并输入起止日期。

        Args:
            start_date (str): 起始日期（YYYY-MM-DD）
            end_date (str): 结束日期（YYYY-MM-DD）
        """
        url = "https://merchant.klook.com/booking"
        self.driver.get(url)
        logger.info(f"⭐ 已打开 KLK 页面：{url}")
        input("👉 请在浏览器中手动完成登录或切换账号后，按下回车键继续...")

        wait = WebDriverWait(self.driver, 10)
        outer_start_input = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//label[contains(.,'Participation date')]/following::input[@placeholder='Start date']",
                )
            )
        )
        outer_start_input.click()
        time.sleep(0.3)

        # 输入日期
        popup_start_input = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//input[contains(@class,'ant-calendar-input') and @placeholder='Start date']",
                )
            )
        )
        popup_end_input = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//input[contains(@class,'ant-calendar-input') and @placeholder='End date']",
                )
            )
        )

        popup_start_input.send_keys(Keys.CONTROL, "a")
        popup_start_input.send_keys(self.start_date)
        popup_end_input.send_keys(Keys.CONTROL, "a")
        popup_end_input.send_keys(self.end_date)
        # popup_end_input.send_keys(Keys.ENTER)
        time.sleep(0.3)

        # 点击搜索
        search_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[span[text()='Search']]"))
        )
        self.driver.execute_script("arguments[0].click();", search_button)
        logger.info(f"📅 已筛选日期：{self.start_date} ~ {self.end_date}")
        self._click_confirmed_tab()
        time.sleep(5)
        self._click_eye_icon()
        time.sleep(5)
        self._wait_first_booking_ready()

    def extract_booking_info(self) -> List[Dict[str, Any]]:
        """
        抓取当前页面的所有订单信息。

        Returns:
            List[Dict[str, Any]]: 每个订单信息的字典。
        """

        cards = self.driver.find_elements(By.CSS_SELECTOR, "div.booking-info")
        logger.info(f"📄 检测到 {len(cards)} 条订单")

        orders = []
        for i, card in enumerate(cards, start=1):
            try:
                orders.append(self._extract_single_booking(card))
            except Exception as e:
                logger.warning(f"⚠️ 第 {i} 个订单解析失败: {e}")
        return orders

    def go_to_next_page(self) -> bool:
        """
        翻页到下一页订单。

        Returns:
            bool: True = 成功翻页，False = 没有下一页。
        """
        next_page_elements = self.driver.find_elements(
            By.XPATH,
            "//li[contains(@class,'ant-pagination-next') and not(contains(@class,'ant-pagination-disabled'))]/a",
        )

        if next_page_elements:
            logger.info("➡️ 检测到下一页，正在翻页...")
            safe_click(self.driver, next_page_elements[0])
            time.sleep(5)  # ⏳ 等页面加载完成
            return True
        logger.info("🏁 没有下一页了")
        return False

    def _click_confirmed_tab(self, max_retries: int = 3) -> None:
        """
        点击 Confirmed Tab，支持重试。
        """
        wait = WebDriverWait(self.driver, 10)
        xpath = "//div[@role='tab' and normalize-space(text())='Confirmed']"

        for attempt in range(max_retries):
            try:
                confirmed_tab = wait.until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                self.driver.execute_script("arguments[0].click();", confirmed_tab)
                logger.info(f"✅ 第 {attempt + 1} 次成功点击 Confirmed Tab")

                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "(//span[contains(@class,'i-icon-icon-view-off')])[1]",
                        )
                    )
                )
                return
            except (StaleElementReferenceException, ElementClickInterceptedException):
                logger.warning(f"⚠️ 第 {attempt + 1} 次点击失败，重试中...")
                time.sleep(1.5)
        raise Exception("❌ 多次尝试后仍未点击上 Confirmed tab")

    def _click_eye_icon(self) -> None:
        """
        点击小眼睛图标，展开电话。
        """
        xpath = "(//span[contains(@class,'i-icon-icon-view-off')])"
        eye_icon = WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        # 检查是否真的可见
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        safe_click(self.driver, eye_icon)
        logger.debug("👁️ 已点击眼睛图标展开电话")

    def _extract_single_booking(self, card: Any) -> Dict[str, Any]:
        """
        解析单条订单信息。

        Args:
            card: WebElement

        Returns:
            Dict[str, Any]: 订单信息
        """
        name = extract_text_safe(
            card,
            ".//li[p[@class='label' and normalize-space()='Full name:']]//div[contains(@class,'valuesColumns')]",
        )

        phone, country = self._extract_phone_number(card)
        count = self._extract_count(card)
        hotel = self._extract_hotel(card)
        language = self._extract_language(card)
        group = self._extract_group_name(card)
        activity_date = self._extract_activity_date(card)
        if "R" in group:
            isboat = "No"
        else:
            isboat = "Yes"
        return {
            "travelerName": name,
            "travelerPhone": phone,
            "travelerCountry": country,
            "travelerCount": count,
            "travelerHotel": hotel,
            "language": language,
            "groupName": group,
            "activityDate": activity_date,
            "platformName": "KLK",
            "isBoat": isboat,
        }

    def _extract_phone_number(self, card: Any) -> Tuple[str, str]:
        """
        提取电话和国家代码。
        """
        try:
            phone = extract_text_safe(
                card,
                ".//li[p[@class='label' and normalize-space()='Phone number:']]//div[contains(@class,'valuesColumns')]",
            )
            phone = phone.replace("-", "").replace(" ", "").strip()
            if phone and not phone.startswith("+"):
                phone = f"+{phone}"
            country = extract_country_code_from_phone(phone)
            return phone, country
        except Exception:
            return "Unknown", "XX"

    def _extract_count(self, card: Any) -> int:
        """
        提取订单人数。
        """
        text = extract_text_safe(
            card,
            ".//li[p[@class='label' and normalize-space()='Unit:']]//div[contains(@class,'valuesColumns')]",
        )
        m = re.search(r"[Xx×]\s*(\d+)", text or "")
        return int(m.group(1)) if m else 0

    def _extract_hotel(self, card: Any) -> str:
        """
        提取酒店信息。
        """
        try:
            return extract_text_safe(
                card,
                ".//li[p[@class='label' and normalize-space()='Departure location:']]//span[1]",
            )
        except Exception:
            try:
                return extract_text_safe(
                    card,
                    ".//li[p[@class='label' and normalize-space()='Departure Location (Map Selection):']]//div[contains(@class,'valuesColumns')]",
                )
            except Exception:
                return "Unknown"

    def _extract_language(self, card: Any) -> str:
        """
        提取语言信息。
        """
        lang = extract_text_safe(
            card,
            ".//li[p[@class='label' and normalize-space()='Preferred language:']]//div[contains(@class,'valuesColumns')]",
        )
        if not lang:
            text = extract_text_safe(
                card,
                ".//li[p[@class='label' and normalize-space()='Package name:']]//div[contains(@class,'valuesColumns')]",
            )
            lang = text.split()[0] if text else "Unknown"
        return "EN" if "english" in lang.lower() else "CN"

    def _extract_group_name(self, card: Any) -> str:
        """
        提取并匹配团名。
        """
        group_title = extract_text_safe(
            card,
            ".//li[p[@class='label' and normalize-space()='Activity name:']]//div[contains(@class,'valuesColumns')]",
        )
        group_option = extract_text_safe(
            card,
            ".//li[p[@class='label' and normalize-space()='Package name:']]//div[contains(@class,'valuesColumns')]",
        )
        return match_group_name(group_title, group_option)

    def _extract_activity_date(self, card: Any) -> str:
        """
        提取活动日期并格式化为 aYYMMDD。
        """
        text = extract_text_safe(
            card,
            ".//li[p[@class='label' and normalize-space()='Participation time:']]//div[contains(@class,'valuesColumns')]",
        )
        m = re.search(r"\d{4}-\d{2}-\d{2}", text or "")
        if not m:
            return "Unknown"
        date_str = m.group(0)
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return dt.strftime("a%y%m%d")
        except Exception:
            return "Unknown"

    def _wait_first_booking_ready(self, timeout: int = 12) -> bool:
        """
        等待第一个订单完全加载（Full name 不为空或 '***'）。
        """
        value_xpath = (
            By.XPATH,
            "(//div[contains(@class,'booking-info')])[1]"
            "//li[p[contains(normalize-space(.), 'Full name')]]"
            "//div[contains(@class,'valuesColumns')]",
        )

        wait = WebDriverWait(self.driver, timeout)

        try:
            # 等元素出现
            wait.until(EC.visibility_of_element_located(value_xpath))

            # 等待文本内容加载完成
            wait.until(
                lambda d: (val := d.find_element(*value_xpath).text.strip())
                not in ["", "***"]
            )

            value = self.driver.find_element(*value_xpath).text.strip()
            logger.info(f"✅ 第一个订单已完全渲染: Full name = {value}")
            return True

        except Exception as e:
            logger.warning(f"⚠️ 第一个订单等待超时或异常：{e}")
            return False
