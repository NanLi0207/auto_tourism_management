# crawler/base_crawler.py
from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional
import time
import logging

# ✅ 初始化日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 如果项目中没有全局 logger 配置，可以为基础爬虫添加简单的 StreamHandler
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class BaseCrawler(ABC):
    """
    🕸️ BaseCrawler

    所有爬虫类的抽象基类，定义了最核心的三个接口：
    - open_page(): 打开目标页面
    - extract_booking_info(): 提取当前页面的订单数据
    - go_to_next_page(): 翻页

    子类需实现以上抽象方法。
    crawl_all_pages() 提供了一个通用的翻页 + 数据采集主流程。
    """

    def __init__(self, driver: Any, start_date: str, end_date: str):
        """
        初始化基础爬虫类。

        Args:
            driver (Any): Selenium WebDriver 对象，用于浏览器自动化操作。
        """
        self.start_date = start_date
        self.end_date = end_date
        self.driver = driver

    @abstractmethod
    def open_page(self) -> None:
        """
        打开目标页面。

        子类必须实现该方法，通常包括：
        - 拼接目标 URL
        - 调用 driver.get()
        - 等待页面加载完成
        """
        pass

    @abstractmethod
    def extract_booking_info(self) -> List[Dict[str, Any]]:
        """
        从当前页面提取订单信息。

        Returns:
            List[Dict[str, Any]]: 当前页所有订单信息的列表，每条订单为一个字典。
        """
        pass

    @abstractmethod
    def go_to_next_page(self) -> bool:
        """
        点击“下一页”按钮实现翻页。

        Returns:
            bool:
                - True: 成功翻到下一页
                - False: 没有下一页，结束采集
        """
        pass

    def crawl_all_pages(self, delay_between_pages: int = 5) -> List[Dict[str, Any]]:
        """
        通用的多页爬取流程：
        - 调用 extract_booking_info() 抓取当前页订单
        - 调用 go_to_next_page() 翻页
        - 直到没有下一页为止

        Args:
            delay_between_pages (int): 翻页之间的等待时间，单位秒。

        Returns:
            List[Dict[str, Any]]: 所有页面采集的订单数据。
        """
        all_orders = []
        page_num = 1
        self.open_page()
        while True:
            logger.info(f"📄 正在处理第 {page_num} 页...")
            try:
                page_orders = self.extract_booking_info()
                order_count = len(page_orders) if page_orders else 0
                logger.info(f"✅ 抓取 {order_count} 条订单")
                all_orders.extend(page_orders or [])
            except Exception as e:
                logger.error(f"❌ 第 {page_num} 页采集失败: {e}", exc_info=True)
                break
            # 翻页
            if not self.go_to_next_page():
                logger.info("🏁 没有下一页了，采集结束。")
                break

            page_num += 1
            time.sleep(delay_between_pages)

        logger.info(f"📊 共采集 {len(all_orders)} 条订单")
        return all_orders
