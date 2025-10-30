# modules/crawler_Viator.py
# =======================================================
# 📄 Viator 平台爬虫
# 工程化 + 标准化 + 注释补全版本
# =======================================================
import re
import time
import logging
from datetime import datetime
from typing import Any, Dict, List, Tuple

from selenium.webdriver.common.by import By

from modules.crawlers.base_crawler import BaseCrawler
from modules.crawlers.crawler_utils import (
    safe_click,
    extract_text_safe,
    match_group_name,
)
from modules.output_utils import extract_country_code_from_phone, format_phone_number

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
    爬取 Viator 平台的订单信息。

    功能：
    - 手动登录后自动翻页采集
    - 展开订单详情和电话
    - 抓取姓名、电话、人数、酒店、语言、团名、日期
    - 匹配平台 ID → 平台名称
    """

    def open_page(self, start_date: str, end_date: str) -> None:
        """
        打开 Viator 订单页面并等待用户登录。

        Args:
            start_date (str): 起始日期（YYYY-MM-DD）
            end_date (str): 结束日期（YYYY-MM-DD）
        """
        base_url = "https://supplier.viator.com/bookings/search?"
        url = (
            f"{base_url}travelDate={start_date}"
            f"&travelEndDate={end_date}"
            f"&sortBy=NEW_BOOKINGS"
            f"&pageNumber=1"
            f"&pageSize=50"
            f"&filterBy=CONFIRMED_BOOKING"
            f"&filterBy=AMENDED_BOOKING"
        )
        logger.info(f"🌐 打开登录页: {base_url}")
        self.driver.get(base_url)
        input("👉 请在浏览器中手动完成登录或切换账号后，按下回车键继续...")
        logger.info(f"➡️ 跳转至订单页面: {url}")
        self.driver.get(url)
        time.sleep(5)
        self.platform_name = self._extract_platform_name()

    def extract_booking_info(self) -> List[Dict[str, Any]]:
        """
        抓取当前页面所有订单信息。

        Returns:
            List[Dict[str, Any]]: 订单信息列表。
        """
        # 展开订单详情 & 电话
        self._click_show_details()
        self._click_show_phone_buttons()
        time.sleep(0.5)

        cards = self.driver.find_elements(
            By.XPATH,
            "//div[contains(@class,'Card__defaultCard') and contains(@class,'BookingSummaryCard__bookingSummaryCard')]",
        )
        logger.info(f"📄 检测到 {len(cards)} 个订单卡片")

        orders = []
        for i, card in enumerate(cards, start=1):
            # 跳过取消订单
            if card.find_elements(
                By.XPATH,
                ".//span[contains(@class,'BookingStatusLabel') and contains(text(),'Canceled')]",
            ):
                logger.info(f"⏭️ 第 {i} 个订单已取消，跳过")
                continue
            try:
                orders.append(self._extract_single_booking(card))
            except Exception as e:
                logger.warning(f"⚠️ 第 {i} 个订单解析失败: {e}")
        return orders

    def go_to_next_page(self) -> bool:
        """
        翻页到下一页订单。

        Returns:
            bool: True = 成功翻页，False = 没有下一页
        """
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

    def _click_show_details(self) -> None:
        """
        展开所有订单详情卡片。
        """
        card_btns = self.driver.find_elements(
            By.XPATH,
            "//button[contains(text(),'Show details') or contains(@data-automation,'show-more')]",
        )
        for btn in card_btns:
            safe_click(self.driver, btn)
            time.sleep(0.5)
        logger.debug(f"🪄 展开 {len(card_btns)} 个订单详情")

    def _click_show_phone_buttons(self) -> None:
        """
        展开所有订单的电话号码（点击小电话图标）。
        """
        phone_btns = self.driver.find_elements(
            By.XPATH,
            "//button[contains(@class,'PhoneNumberView') and contains(@class,'maskControls')]",
        )
        for btn in phone_btns:
            safe_click(self.driver, btn)
            time.sleep(0.5)
        logger.debug(f"📞 展开 {len(phone_btns)} 个订单电话")

    def _extract_single_booking(self, card: Any) -> Dict[str, Any]:
        """
        解析单条订单信息。

        Args:
            card: WebElement 订单卡片

        Returns:
            Dict[str, Any]: 订单信息字典
        """
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
        }

    def _extract_platform_name(self) -> str:
        """
        提取平台 ID 并映射为平台名称。
        """
        platform_map = {
            "311086": "V1",
            "337760": "V2",
            "410868": "V3",
        }
        text = extract_text_safe(
            self.driver, "//span[contains(@class,'Navigation__navigationItemLabel')]"
        )
        if not text:
            return "Unknown"
        m = re.search(r"\((\d+)\)", text)
        if m:
            platform_id = m.group(1)
            return platform_map.get(platform_id, f"Unknown({platform_id})")
        return "Unknown"

    def _extract_count(self, card: Any) -> int:
        """
        提取订单人数。
        """
        text = extract_text_safe(
            card,
            ".//div[contains(@class,'BookingSummaryCard__bookingSummaryLabel') and contains(text(),'adult')]",
        )
        m = re.search(r"(\d+)", text)
        return int(m.group(1)) if m else 0

    def _extract_hotel(self, card: Any) -> str:
        """
        提取酒店信息并清洗。
        """
        text = extract_text_safe(
            card,
            (
                ".//span[contains(text(),'Pickup point') "
                "or contains(text(),'Meeting or pickup point')]/ancestor::span"
                "/span[@class='LabelAndValue__value___IY-eR']"
            ),
        )

        if text and text != "Unknown":
            lower_text = text.lower()

            # 🛑 情况1：用户还没决定酒店
            if (
                "contact the supplier later" in lower_text
                or "hotel is not yet booked" in lower_text
                or "decide later" in lower_text
            ):
                return "Unknown"

            # 🏨 情况2：hotel is not listed: XXX
            if "hotel is not listed" in lower_text and ":" in text:
                text = text.split(":", 1)[-1].strip()

            # 🧼 清洗数据
            text = re.sub(r"\(.*?\)", "", text)  # 去括号内容
            text = re.split(r"(?i)\bthe netherlands\b", text)[0]  # 去掉国家名
            text = re.sub(r"\s*,\s*", ", ", text)  # 格式化逗号
            text = re.sub(r"(,\s*){2,}", ", ", text)  # 去多余连续逗号
            return text.strip(" ,") or "Unknown"
        return "Unknown"

    def _extract_language(self, card: Any) -> str:
        """
        提取订单语言。
        """
        text = extract_text_safe(
            card,
            ".//span[contains(.,'Tour language')]/span[@class='LabelAndValue__value___IY-eR']//li",
        )
        return "EN" if "english" in text.lower() else "CN"

    def _extract_activity_date(self, card: Any) -> str:
        """
        提取活动日期，格式化为 aYYMMDD。
        """
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

    def _extract_phone_country(self, card: Any) -> Tuple[str, str]:
        """
        提取旅客电话号。优先从主卡片获取，若没有则尝试点击“Message traveler”。
        """
        """
        提取旅客电话号。
        若主卡片中缺失，则点击“Message traveler”→显示号码→提取→返回。
        """
        # Step 1️⃣ 直接提取
        try:
            raw_phone = extract_text_safe(
                card,
                ".//div[contains(@class,'BookingSummaryCard__maskedPhoneNumber')]//a[contains(@href,'tel:')]/span",
            )
            phone = format_phone_number(raw_phone)
            country = extract_country_code_from_phone(phone)
            return phone, country
        except Exception:
            pass  # 没找到则进入聊天页尝试

        # Step 2️⃣ 聊天页提取
        try:
            msg_btn = card.find_element(
                By.XPATH, ".//button[contains(@data-automation,'message-traveller')]"
            )
            safe_click(self.driver, msg_btn)
            time.sleep(3)

            # Step 3️⃣ 聊天页中显示号码
            try:
                # 若号码被隐藏，点击小眼睛按钮
                show_btns = self.driver.find_elements(
                    By.XPATH,
                    "//button[contains(@class,'PhoneNumberView__maskControls')]",
                )
                if show_btns:
                    safe_click(self.driver, show_btns)
                    time.sleep(1)

                # 提取电话号码
                raw_phone = extract_text_safe(
                    self.driver, "//a[contains(@href,'tel:')]/span"
                )
                phone = format_phone_number(raw_phone)
                country = extract_country_code_from_phone(phone)

                # Step 4️⃣ 返回上一页
                self.driver.back()
                time.sleep(4)
                return phone, country

                # # 重新展开详情（Show details & 电话按钮）
                # try:
                #     show_detail = card.find_element(
                #         By.XPATH, ".//button[contains(., 'Show details')]"
                #     )
                #     self.driver.execute_script("arguments[0].click();", show_detail)
                #     time.sleep(1)
                # except:
                #     pass

                # try:
                #     phone_btn = card.find_element(
                #         By.XPATH, ".//div[contains(@class,'maskedPhoneNumber')]//button"
                #     )
                #     self.driver.execute_script("arguments[0].click();", phone_btn)
                #     time.sleep(1)
                # except:
                #     pass

                return phone, country

            except Exception as e:
                logger.warning(f"⚠️ 聊天页未找到电话号: {e}")
                self.driver.back()
                time.sleep(3)
                return "Unknown", "XX"

        except Exception as e:
            logger.warning(f"⚠️ 未找到 'Message traveler' 按钮: {e}")
            return "Unknown", "XX"
