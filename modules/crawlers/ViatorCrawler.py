# modules/crawlers/ViatorCrawler.py
# =======================================================
# 📄 Viator 平台爬虫
# 稳定版（逐个订单展开 + 防 stale 元素）
# =======================================================
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
    match_group_name,
)
from modules.utils.output_utils import (
    extract_country_code_from_phone,
    format_phone_number,
)

# ✅ 日志配置
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class ViatorCrawler(BaseCrawler):
    """
    🧭 ViatorCrawler
    自动采集 Viator 平台订单信息。
    """

    # =======================================================
    # 🧾 页面打开
    # =======================================================
    def open_page(self) -> None:
        base_url = "https://supplier.viator.com/bookings/search?"
        url = (
            f"{base_url}travelDate={self.start_date}"
            f"&travelEndDate={self.end_date}"
            f"&sortBy=NEW_BOOKINGS"
            f"&pageNumber=1&pageSize=50"
            f"&filterBy=CONFIRMED_BOOKING"
            f"&filterBy=AMENDED_BOOKING"
        )
        logger.info(f"🌐 打开登录页: {base_url}")
        self.driver.get(base_url)
        input("👉 请在浏览器中手动登录后按回车继续...")
        logger.info(f"➡️ 跳转至订单页面: {url}")
        self.driver.get(url)
        time.sleep(5)
        self.platform_name = self._extract_platform_name()

    # =======================================================
    # 📋 采集逻辑
    # =======================================================
    def extract_booking_info(self) -> List[Dict[str, Any]]:
        orders = []
        cards = self.driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'Card__defaultCard') and contains(@class,'BookingSummaryCard__bookingSummaryCard')]",
        )
        logger.info(f"📄 检测到 {len(cards)} 个订单卡片")

        for i in range(len(cards)):
            try:
                # ⚡ 每次循环重新获取卡片，防止 stale
                cards = self.driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class,'Card__defaultCard') and contains(@class,'BookingSummaryCard__bookingSummaryCard')]",
                )
                card = cards[i]

                # 🚫 跳过取消订单
                canceled = card.find_elements(
                    By.XPATH,
                    ".//span[contains(@class,'BookingStatusLabel') and contains(text(),'Canceled')]",
                )
                if canceled:
                    logger.info(f"⏭️ 第 {i + 1} 个订单已取消，跳过")
                    continue

                # 🪄 展开详情与电话
                self._expand_single_detail(card)
                self._expand_single_phone(card)

                # 🧾 提取数据
                order = self._extract_single_booking(card)
                orders.append(order)
                logger.info(f"✅ 第 {i + 1} 个订单采集成功")

            except Exception as e:
                logger.error(f"❌ 第 {i + 1} 个订单采集失败: {e}", exc_info=False)

        return orders

    # =======================================================
    # 🔁 翻页
    # =======================================================
    def go_to_next_page(self) -> bool:
        next_page_elements = self.driver.find_elements(
            By.XPATH,
            "//li[contains(@class,'ant-pagination-next') and not(contains(@class,'disabled'))]/a",
        )
        if next_page_elements:
            logger.info("➡️ 检测到下一页，正在翻页...")
            safe_click(self.driver, next_page_elements[0])
            time.sleep(5)
            return True
        logger.info("🏁 没有下一页了")
        return False

    # =======================================================
    # 🔓 展开详情与电话
    # =======================================================
    def _expand_single_detail(self, card):
        """展开当前订单详情"""
        try:
            hide_btns = card.find_elements(
                By.XPATH,
                ".//button[contains(text(),'Hide details') or contains(@data-automation,'show-less')]",
            )
            if hide_btns:
                return
            show_btns = card.find_elements(
                By.XPATH,
                ".//button[contains(text(),'Show details') or contains(@data-automation,'show-more')]",
            )
            if show_btns:
                safe_click(self.driver, show_btns[0])
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"⚠️ 展开详情失败: {e}")

    def _expand_single_phone(self, card):
        """展开当前订单电话"""
        try:
            tel_span = card.find_elements(By.XPATH, ".//a[contains(@href,'tel:')]")
            if tel_span:
                return  # 已经显示
            phone_btns = card.find_elements(
                By.XPATH,
                ".//button[contains(@class,'PhoneNumberView') and contains(@class,'maskControls')]",
            )
            if phone_btns:
                safe_click(self.driver, phone_btns[0])
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"⚠️ 展开电话失败: {e}")

    # =======================================================
    # 🧩 单条订单解析
    # =======================================================
    def _extract_single_booking(self, card: Any) -> Dict[str, Any]:
        name = extract_text_safe(
            card,
            ".//span[contains(@class,'LabelAndValue__label')]/span/span[contains(text(),'Lead Traveler')]/ancestor::span/span[@class='LabelAndValue__value___IY-eR']",
        )
        phone, country = self._extract_phone_country(card)
        count = self._extract_count(card)
        hotel = self._extract_hotel(card)
        language = self._extract_language(card)
        date_str = self._extract_activity_date(card)
        group_title = extract_text_safe(
            card, ".//h3[contains(@class,'BookingSummaryCard__productTitle')]"
        )
        group_option = extract_text_safe(
            card, ".//p[contains(@class,'BookingSummaryCard__productSubtitle')]"
        )
        group_name = match_group_name(group_title, group_option)
        isboat = "Yes" if "G" in group_name else "No"

        return {
            "travelerName": name,
            "travelerPhone": phone,
            "travelerCountry": country,
            "travelerCount": count,
            "travelerHotel": hotel,
            "groupName": group_name,
            "language": language,
            "activityDate": date_str,
            "platformName": self.platform_name,
            "isBoat": isboat,
        }

    # =======================================================
    # ☎️ 电话提取逻辑
    # =======================================================
    def _extract_phone_country(self, card: Any) -> Tuple[str, str]:
        # Step 1️⃣ 尝试直接读取
        raw_phone = extract_text_safe(
            card,
            ".//div[contains(@class,'BookingSummaryCard__maskedPhoneNumber')]//a[contains(@href,'tel:')]/span",
        )
        if raw_phone != "Unknown" and raw_phone.strip():
            phone = format_phone_number(raw_phone)
            country = extract_country_code_from_phone(phone)
            return phone, country

        # Step 2️⃣ 尝试进入聊天页
        try:
            msg_btn = card.find_element(
                By.XPATH, ".//button[contains(@data-automation,'message-traveller')]"
            )
            safe_click(self.driver, msg_btn)
            time.sleep(3)

            # Step 3️⃣ 聊天页中点击显示
            show_btns = self.driver.find_elements(
                By.XPATH,
                "//button[contains(@class,'PhoneNumberView__maskControls')]",
            )
            if show_btns:
                safe_click(self.driver, show_btns[0])
                time.sleep(1)
            else:
                logger.warning("⚠️ 聊天页未找到显示号码按钮")

            raw_phone = extract_text_safe(
                self.driver, "//a[contains(@href,'tel:')]/span"
            )
            phone = (
                format_phone_number(raw_phone) if raw_phone != "Unknown" else "Unknown"
            )
            country = (
                extract_country_code_from_phone(phone) if phone != "Unknown" else "XX"
            )

            # Step 4️⃣ 返回并防止 stale
            self.driver.back()
            time.sleep(3)
            self.driver.find_elements(  # 重新抓一次，刷新引用
                By.XPATH,
                "//div[contains(@class,'BookingSummaryCard__bookingSummaryCard')]",
            )

            return phone, country

        except Exception as e:
            logger.warning(f"⚠️ 未找到聊天按钮或提取失败: {e}")
            return "Unknown", "XX"

    # =======================================================
    # 其它字段提取函数
    # =======================================================
    def _extract_platform_name(self) -> str:
        platform_map = {"311086": "V1", "337760": "V2", "410868": "V3"}
        text = extract_text_safe(
            self.driver, "//span[contains(@class,'Navigation__navigationItemLabel')]"
        )
        m = re.search(r"\((\d+)\)", text or "")
        return (
            platform_map.get(m.group(1), f"Unknown({m.group(1)})") if m else "Unknown"
        )

    def _extract_count(self, card: Any) -> int:
        text = extract_text_safe(
            card,
            ".//div[contains(@class,'BookingSummaryCard__bookingSummaryLabel') and contains(text(),'adult')]",
        )
        m = re.search(r"(\d+)", text)
        return int(m.group(1)) if m else 0

    def _extract_hotel(self, card: Any) -> str:
        text = extract_text_safe(
            card,
            (
                ".//span[contains(text(),'Pickup point') or contains(text(),'Meeting or pickup point')]/ancestor::span/span[@class='LabelAndValue__value___IY-eR']"
            ),
        )
        if not text or text == "Unknown":
            return "Unknown"
        lower_text = text.lower()
        if (
            "contact the supplier later" in lower_text
            or "hotel is not yet booked" in lower_text
        ):
            return "Unknown"
        if "hotel is not listed" in lower_text and ":" in text:
            text = text.split(":", 1)[-1].strip()
        text = re.sub(r"\(.*?\)", "", text)
        text = re.split(r"(?i)\bthe netherlands\b", text)[0]
        text = re.sub(r"\s*,\s*", ", ", text)
        text = re.sub(r"(,\s*){2,}", ", ", text)
        return text.strip(" ,") or "Unknown"

    def _extract_language(self, card: Any) -> str:
        text = extract_text_safe(
            card,
            ".//span[contains(.,'Tour language')]/span[@class='LabelAndValue__value___IY-eR']//li",
        )
        return "EN" if "english" in text.lower() else "CN"

    def _extract_activity_date(self, card: Any) -> str:
        raw = extract_text_safe(
            card, ".//span[contains(@class,'BookingSummaryCard__bookingDate')]"
        )
        if raw == "Unknown":
            return "a000000"
        parts = raw.split(",")
        date_str = (
            parts[1].strip() + ", " + parts[2].strip()
            if len(parts) == 3
            else raw.strip()
        )
        try:
            dt = datetime.strptime(date_str, "%b %d, %Y")
            return dt.strftime("a%y%m%d")
        except Exception:
            return "a000000"
