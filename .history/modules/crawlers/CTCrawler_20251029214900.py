# modules/crawler_CT.py
# =====================================================
# 📄 CTrip 平台订单爬虫 (CT Crawler)
# 工程化 + 文档标准化版本
# =====================================================

import os
import time
import logging
from typing import Any, Dict, List
from pathlib import Path
import pandas as pd

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from modules.crawlers.base_crawler import BaseCrawler
from modules.crawlers.crawler_utils import (
    safe_click,
    match_group_name,
    chinese_name_to_english,
)
from modules.output_utils import extract_country_code_from_phone, format_phone_number


# ✅ 初始化日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class CTCrawler(BaseCrawler):
    """
    CTrip (携程) 平台订单爬虫类。

    该类继承自 BaseCrawler，用于自动化登录携程供应商后台，
    执行订单导出、文件处理、数据清洗与结构化解析。
    """

    def __init__(self, driver: Any, start_date: str, end_date: str, download_dir: str):
        """
        初始化 CTCrawler 实例。

        Args:
            driver (Any): Selenium WebDriver 对象。
            start_date (str): 查询开始日期，格式 "YYYY-MM-DD"。
            end_date (str): 查询结束日期，格式 "YYYY-MM-DD"。
            download_dir (str): 文件下载保存的目标文件夹。
        """
        super().__init__(driver=driver, start_date=start_date, end_date=end_date)
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    # =====================================================
    # 🌐 页面操作主流程
    # =====================================================

    def open_page(self) -> None:
        """
        打开携程订单页面，完成登录/验证后执行：
        1. 设置英文 cookie
        2. 刷新页面
        3. 切换到 All 标签页
        4. 等待 panel 加载完成
        5. 设置日期并搜索
        6. 等待结果加载完成
        7. 导出订单文件并重命名
        """
        url = "https://vbooking.ctrip.com/ticket_order/order/list"
        logger.info(f"🌐 打开页面: {url}")
        self.driver.get(url)
        input("👉 请在浏览器中完成登录/验证后按回车继续...")

        self._set_english_cookies()
        self.driver.refresh()
        self._click_all()
        self._wait_panel_ready()
        self._set_date_and_search()
        self._wait_panel_idle()
        self._click_export()
        self._rename()

    def extract_booking_info(self) -> List[Dict[str, Any]]:
        """
        读取并解析下载的订单 Excel，提取结构化的预订信息。

        Returns:
            List[Dict[str, Any]]: 订单信息列表，每个元素代表一条订单记录。
        """
        self._read_and_clean()
        self._filter_by_date()
        orders = []

        for order in self.clean_orders.itertuples(index=True, name="Order"):
            name = chinese_name_to_english(str(order.Contact_Name))
            phone = f"+{format_phone_number(str(order.Contact_Mobile))}"
            country = extract_country_code_from_phone(phone)
            people_count = int(str(order.Tickets_Booked))
            product = str(order.Booked_Resource_Name).lower()
            group_name = match_group_name(str(order.Booked_Resource_Name), "")
            hotel = str(order.Additional_Information).split(":")[-1]
            language = "CN" if any(k in product for k in ["chinese", "中文"]) else "EN"
            activity_date = order.Date_of_Use.date().strftime("a%y%m%d")  # type: ignore

            # 🛥️ 是否包含船
            isboat = ""
            if any(k in product for k in ("船", "boat")):
                if any(
                    k in product
                    for k in (
                        "不含游船",
                        "不包游船",
                        "不包含游船",
                        "不含船",
                        "不包船",
                        "不包含船",
                        "excl. boat",
                    )
                ):
                    isboat = "不包船"
                else:
                    isboat = "包船"

            # 🚌 车辆信息
            bus = ""
            if "42 seater" in product:
                bus = 42
            elif "19 seater" in product:
                bus = 19

            orders.append(
                {
                    "travelerName": name,
                    "travelerPhone": phone,
                    "travelerCountry": country,
                    "travelerCount": people_count,
                    "travelerHotel": hotel,
                    "groupName": group_name,
                    "language": language,
                    "activityDate": activity_date,
                    "platformName": "CT",
                    "isBoat": isboat,
                }
            )

        return orders

    def go_to_next_page(self) -> bool:
        """
        携程订单列表不分页，因此此方法直接返回 False。

        Returns:
            bool: False
        """
        return False

    # =====================================================
    # 🍪 Cookie & 页面控制辅助方法
    # =====================================================

    def _set_english_cookies(self) -> None:
        """
        设置携程后台的英文语言 cookie，确保页面显示英文内容。
        """
        cookies = [
            {
                "name": "vbk-locale-lang",
                "value": "en-US",
                "domain": ".ctrip.com",
                "path": "/",
            },
            {
                "name": "ibulocale",
                "value": "en_us",
                "domain": ".ctrip.com",
                "path": "/",
            },
            {
                "name": "ibulocale",
                "value": "en_us",
                "domain": ".vbooking.ctrip.com",
                "path": "/",
            },
            {"name": "ibulanguage", "value": "EN", "domain": ".ctrip.com", "path": "/"},
        ]
        for c in cookies:
            try:
                self.driver.add_cookie(c)
            except Exception as e:
                logger.warning(f"⚠️ Cookie 设置失败: {c['name']} - {e}")

    def _click_all(self) -> None:
        """
        点击“ALL”标签页，确保显示全部订单。
        """
        all_tab = WebDriverWait(self.driver, 30).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//div[@class='tab-bar-item' and normalize-space(text())='All']",
                )
            )
        )
        all_tab.click()
        logger.info("✅ 已点击 All")

    def _wait_panel_ready(self, timeout: int = 60) -> None:
        """
        等待 panel4 面板激活。

        Args:
            timeout (int, optional): 超时时间（秒）。Defaults to 60.

        Raises:
            TimeoutException: 激活超时。
        """
        logger.info("⌛ 等待 panel4 激活...")
        end_time = time.time() + timeout
        while time.time() < end_time:
            ready = self.driver.execute_script("""
                const p = document.querySelector('#rc-tabs-1-panel-4');
                if (!p) return false;
                if (p.getAttribute('aria-hidden') !== 'false') return false;
                const picker = p.querySelector('.condition-range-picker input');
                const loading = p.querySelector('.ant-table-wrapper.is-loading');
                return !!picker && !loading;
            """)
            if ready:
                logger.info("✅ panel4 已激活")
                time.sleep(2)
                return
            time.sleep(0.5)
        raise TimeoutException("❌ panel4 激活超时")

    def _wait_panel_idle(self, timeout: int = 60) -> None:
        """
        等待搜索结果加载完成（表格不再处于 loading 状态）。

        Args:
            timeout (int, optional): 超时时间（秒）。Defaults to 60.

        Raises:
            TimeoutException: 加载超时。
        """
        logger.info("⌛ 等待搜索结果加载完成...")
        end_time = time.time() + timeout
        while time.time() < end_time:
            loading = self.driver.execute_script("""
                const p = document.querySelector('#rc-tabs-1-panel-4');
                return p ? !!p.querySelector('.ant-table-wrapper.is-loading') : true;
            """)
            if not loading:
                logger.info("✅ 表格加载完成")
                time.sleep(1)
                return
            time.sleep(0.5)
        raise TimeoutException("❌ 等待表格加载超时")

    def _set_date_and_search(self, timeout: int = 30) -> bool:
        """
        设置订单搜索日期范围，并点击搜索按钮。

        Args:
            timeout (int, optional): 查找日期控件的超时时间。Defaults to 30.

        Returns:
            bool: 是否设置成功。
        """
        logger.info(f"📅 设置日期: {self.start_date} ~ {self.end_date}")

        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".condition-range-picker")
                )
            )
        except TimeoutException:
            logger.error("❌ 未找到日期控件")
            self.driver.save_screenshot("debug_no_date_picker.png")
            return False

        self.driver.execute_script("""
            const picker = document.querySelector('.condition-range-picker');
            const suffix = picker?.querySelector('.ant-picker-suffix');
            (suffix || picker)?.click();
        """)
        time.sleep(0.3)

        js = """
        const picker = document.querySelector('.condition-range-picker');
        const inputs = picker.querySelectorAll('input');
        if (inputs.length < 2) return { ok: false };

        function trigger(el, val){
            if (el.hasAttribute('readonly')) el.removeAttribute('readonly');
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
            el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }

        trigger(inputs[0], arguments[0]);
        trigger(inputs[1], arguments[1]);
        document.body.click();
        picker.dispatchEvent(new Event('change', { bubbles: true }));

        return {
            start: inputs[0].value,
            end: inputs[1].value,
            ok: !!(inputs[0].value && inputs[1].value)
        };
        """
        result = self.driver.execute_script(js, self.start_date, self.end_date)
        logger.info(f"📅 日期设置结果: {result}")

        if not result.get("ok"):
            logger.warning("⚠️ 日期写入失败")
            self.driver.save_screenshot("debug_date_fail.png")
            return False

        self.driver.execute_script(
            "const b=document.querySelector('button[data-name=\"search\"]'); if (b) b.click();"
        )
        logger.info("🔍 已点击 Search")
        return True

    def _click_export(self) -> None:
        """
        点击“Export”按钮，触发订单导出。
        """
        logger.info("📦 等待 Export 按钮…")
        btn = WebDriverWait(self.driver, 30).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "#rc-tabs-1-panel-4 button[data-name='export']")
            )
        )
        safe_click(self.driver, btn, delay=0.5)
        logger.info("📥 已点击 Export")

    # =====================================================
    # 💾 文件处理
    # =====================================================

    def _wait_for_download(self, timeout: int = 180) -> Path:
        """
        等待 Chrome 下载完成并返回最终文件路径。

        Args:
            timeout (int, optional): 等待超时时间（秒）。Defaults to 180.

        Returns:
            Path: 下载完成的文件路径。

        Raises:
            TimeoutException: 下载超时。
        """
        logger.info(f"⌛ 等待文件下载中... 目录：{self.download_dir}")
        end_time = time.time() + timeout
        before_files = set(self.download_dir.glob("*"))

        while time.time() < end_time:
            current_files = set(self.download_dir.glob("*"))
            new_files = current_files - before_files

            for f in new_files:
                if f.suffix.endswith(".crdownload"):
                    continue
                if f.exists() and f.stat().st_size > 0:
                    logger.info(f"✅ 检测到已完成下载的文件: {f}")
                    return f
            time.sleep(1)

        raise TimeoutException("❌ 等待下载文件超时")

    def _handle_duplicate(self, new_file_path: Path) -> None:
        """
        如果目标路径已存在文件，则删除旧文件，避免重名冲突。

        Args:
            new_file_path (Path): 目标文件路径。
        """
        if new_file_path.exists():
            try:
                logger.warning(f"⚠️ 目标文件已存在，准备覆盖: {new_file_path}")
                new_file_path.unlink()
            except Exception as e:
                logger.error(f"❌ 删除旧文件失败: {e}")
                raise

    def _rename(self) -> None:
        """
        重命名下载的携程订单文件为标准命名格式：
        CT_{start_date}_{end_date}.xlsx
        """
        downloaded_file = self._wait_for_download()
        new_file_name = f"CT_{self.start_date}_{self.end_date}.xlsx"
        self.new_path = self.download_dir / new_file_name
        self._handle_duplicate(self.new_path)
        os.rename(downloaded_file, self.new_path)
        logger.info(f"✅ 文件已保存并改名（已处理重名）: {self.new_path}")

    # =====================================================
    # 🧹 数据清洗与筛选
    # =====================================================

    def _read_and_clean(self) -> None:
        """
        读取下载的 Excel 订单文件，并完成：
        - 列名标准化
        - 删除取消订单
        - 重置索引
        """
        usecols = [
            "Booked Resource Name",
            "Date of Use",
            "Contact Name",
            "Contact Mobile",
            "Tickets Booked",
            "Additional Information",
            "Booking Status",
            "Contact Email",
        ]
        try:
            tourist_orders = pd.read_excel(
                self.new_path,
                sheet_name="Things to Do",
                skiprows=5,
                usecols=usecols,
                dtype={"Contact Mobile": "string"},
                parse_dates=["Date of Use"],
                engine="openpyxl",
            )
        except FileNotFoundError:
            raise FileNotFoundError(f"❌ 找不到文件: {self.new_path}")
        except Exception as e:
            raise RuntimeError(f"❌ 读取 Excel 失败: {e}")

        # ✅ 列名标准化
        tourist_orders.columns = (
            tourist_orders.columns.astype(str)
            .str.strip()
            .str.replace(r"\s+", "_", regex=True)
            .str.replace(r"[^0-9A-Za-z_]", "", regex=True)
        )

        if "Booking_Status" not in tourist_orders.columns:
            raise KeyError("❌ 找不到 Booking Status 列，请检查文件格式")

        # ✅ 删除取消订单
        before = len(tourist_orders)
        tourist_orders = tourist_orders[tourist_orders["Booking_Status"] != "Cancelled"]
        after = len(tourist_orders)
        logger.info(f"🧹 删除 {before - after} 条 Cancelled 订单，剩余 {after} 条")

        self.tourist_orders = tourist_orders.reset_index(drop=True)

    def _filter_by_date(self) -> None:
        """
        按设定的起止日期筛选订单记录，结果保存在 `self.clean_orders`。

        Raises:
            RuntimeError: 若尚未读取文件。
        """
        if self.tourist_orders is None:
            raise RuntimeError("请先调用 _read_and_clean()")

        start = pd.to_datetime(self.start_date).date()
        end = pd.to_datetime(self.end_date).date()

        mask = (self.tourist_orders["Date_of_Use"].dt.date >= start) & (
            self.tourist_orders["Date_of_Use"].dt.date <= end
        )
        filtered = self.tourist_orders.loc[mask].reset_index(drop=True)
        logger.info(f"📅 按 {start} ~ {end} 筛选，剩余 {len(filtered)} 条记录")
        self.clean_orders = filtered
