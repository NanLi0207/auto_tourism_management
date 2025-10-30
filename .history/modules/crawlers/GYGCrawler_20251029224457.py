# modules/crawler_GYG.py
# ===============================================
# 📄 GetYourGuide 平台订单爬虫
# 工程化 + 文档标准化版本
# ===============================================
import re
import time
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from selenium.webdriver.common.by import By

from modules.crawlers.BaseCrawler import BaseCrawler
from modules.crawlers.crawler_utils import (
    safe_click,
    extract_text_safe,
    clean_traveler_name,
    match_group_name,
)
from modules.utils.output_utils import (
    extract_country_code_from_phone,
    format_phone_number,
)

# ✅ 初始化日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class GYGCrawler(BaseCrawler):
    """
    🧭 GYGCrawler
    爬取 GetYourGuide 平台订单数据。

    功能：
    - 打开订单页面（手动登录后自动抓取）
    - 翻页抓取所有订单
    - 解析姓名、电话、语言、酒店、人数、团名、日期等信息
    """

    def open_page(self) -> None:
        """
        打开 GYG 订单页面，等待用户登录后继续。

        Args:
            start_date (str): 起始日期（YYYY-MM-DD）
            end_date (str): 结束日期（YYYY-MM-DD）
        """
        base_url = "https://supplier.getyourguide.com/bookings?managed_by=369677"
        url = f"{base_url}&filter_activity_date_from={self.start_date}&filter_activity_date_to={self.end_date}"
        logger.info(f"🌐 打开 GYG 页面: {url}")

        self.driver.get(base_url)
        input("👉 请在浏览器中手动完成登录或切换账号后，按下回车键继续...")
        self.driver.get(url)
        time.sleep(4)

    def extract_booking_info(self) -> List[Dict[str, Any]]:
        """
        从当前页面提取所有订单信息。

        Returns:
            List[Dict[str, Any]]: 每个订单为一个 dict。
        """
        # 展开每个订单的详情
        self._click_show_details()
        time.sleep(0.5)

        cards = self.driver.find_elements(
            By.XPATH, "//div[@data-testid='booking-card']"
        )
        logger.info(f"📄 检测到 {len(cards)} 个订单卡片")

        orders = []
        for i, card in enumerate(cards, start=1):
            # 跳过已取消的订单
            if card.find_elements(By.XPATH, ".//span[contains(text(), 'Canceled')]"):
                logger.info(f"⏭️ 第 {i} 个订单已取消，跳过")
                continue

            try:
                orders.append(self._extract_single_booking(card))
            except Exception as e:
                logger.warning(f"⚠️ 订单 {i} 解析失败: {e}")

        logger.info(f"✅ 本页提取 {len(orders)} 条有效订单")
        return orders

    def _click_show_details(self) -> None:
        """
        展开页面上所有未取消订单的详情卡片。
        """
        cards = self.driver.find_elements(
            By.XPATH, "//div[@data-testid='booking-card']"
        )
        for i, card in enumerate(cards, start=1):
            if card.find_elements(By.XPATH, ".//span[contains(text(), 'Canceled')]"):
                continue
            btns = card.find_elements(
                By.XPATH, ".//button[contains(., 'Show details')]"
            )
            if btns:
                safe_click(self.driver, btns[0])
                time.sleep(1)
                logger.debug(f"🪄 展开第 {i} 个订单详情")

    def go_to_next_page(self) -> bool:
        """
        翻页，进入下一页订单。

        Returns:
            bool:
                - True: 成功翻页
                - False: 没有下一页
        """
        next_btns = self.driver.find_elements(
            By.XPATH,
            "//button[contains(@class, 'p-paginator-next') and not(@disabled)]",
        )
        if next_btns:
            logger.info("➡️ 检测到下一页，正在翻页...")
            safe_click(self.driver, next_btns[0])
            time.sleep(5)
            return True
        logger.info("🏁 没有下一页了")
        return False

    def _extract_single_booking(self, card: Any) -> Dict[str, Any]:
        """
        解析单个订单卡片中的信息。

        Args:
            card: WebElement，订单卡片元素。

        Returns:
            Dict[str, Any]: 订单信息字典。
        """
        name = clean_traveler_name(
            extract_text_safe(card, '[data-testid="lead-traveler-name"]') or ""
        )
        # 电话
        phone, country = self._extract_phone_country(card)

        # 人数
        people_count = "Unknown"
        try:
            people_text = extract_text_safe(
                card, '[data-testid="participants-and-price"]'
            )
            match = re.search(r"(\d+)", people_text or "")
            if match:
                people_count = int(match.group(1))
        except Exception:
            pass

        # 酒店
        hotel = extract_text_safe(card, '[data-testid="customer-accommodation"]')
        # 语言
        language = self._extract_language(card)
        # 日期
        activity_date = self._extract_activity_date(card)
        # 团名
        group_title = extract_text_safe(card, "h4.text-body-strong")
        group_option = extract_text_safe(card, "p.text-caption")
        group_name = match_group_name(group_title, group_option)
        if "R" in group_name:
            isboat = "No"
        else:
            isboat = "Yes"

        return {
            "travelerName": name,
            "travelerPhone": phone,
            "travelerCountry": country,
            "travelerCount": people_count,
            "travelerHotel": hotel,
            "groupName": group_name,
            "language": language,
            "activityDate": activity_date,
            "platformName": "GYG",
            "isBoat": isboat,
        }

    def _extract_phone_country(self, card: Any) -> Tuple[str, str]:
        """
        提取游客电话和国家区号。

        Args:
            card: WebElement

        Returns:
            Tuple[str, str]: (电话, 国家代码)，失败时返回 ("Unknown", "XX")
        """
        try:
            phone_raw = extract_text_safe(card, '[data-testid="lead-traveler-phone"]')
            phone = format_phone_number(phone_raw)  # type: ignore
            country = extract_country_code_from_phone(phone)
            return phone, country
        except Exception:
            return "Unknown", "XX"

    def _extract_language(self, card: Any) -> str:
        """
        提取订单语言（EN 或 CN）。
        """
        text = extract_text_safe(
            card,
            '[data-testid="booking-detail-conduction-language"] .text-body.main-content',
        )
        if text:
            text = text.split(":")[-1].strip().lower()
            return "EN" if "english" in text else "CN"
        return "Unknown"

    def _extract_activity_date(self, card: Any) -> str:
        """
        提取并格式化活动日期，格式：aYYMMDD。
        """
        text = extract_text_safe(card, '[data-testid="conduction-time"]')
        if text:
            text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)
            try:
                parts = text.split(",", 1)[1]
                date_str = " ".join(parts.split(" ", 4)[0:4])
                dt = datetime.strptime(date_str.strip(), "%B %d, %Y")
                return dt.strftime("a%y%m%d")
            except Exception:
                pass
        return "Unknown"
