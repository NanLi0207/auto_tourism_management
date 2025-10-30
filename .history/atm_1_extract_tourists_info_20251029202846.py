from modules.utils.browser_connector import (
    close_all_chrome,
    start_chrome_with_debug,
    connect_to_existing_browser,
)
from modules.crawlers.CTCrawler import CTCrawler
from modules.crawlers.GYGCrawler import GYGCrawler
from modules.crawlers.KLKCrawler import KLKCrawler
from modules.crawlers.ViatorCrawler import ViatorCrawler
from modules.utils.output_utils import (
    format_booking_line,
    save_orders_to_txt,
)

start_date = "2025-11-01"
end_date = "2025-11-01"
if start_date == end_date:
    output_file = f"a{start_date.replace('-', '')[2:]}.txt"
else:
    output_file = (
        f"a{start_date.replace('-', '')[2:]}_a{end_date.replace('-', '')[2:]}.txt"
    )

# 1️⃣ 清理旧浏览器
close_all_chrome()

# 2️⃣ 启动并接管浏览器
start_chrome_with_debug()
driver = connect_to_existing_browser()


# =========================
# 🧾 CT
# =========================

crawler = CTCrawler(driver, start_date, end_date, "./downloads/")
# 4️⃣ 自动翻页并采集
all_orders = crawler.crawl_all_pages()
# print(all_orders)
save_orders_to_txt(all_orders, output_file, append=False)
# 5️⃣ 格式化输出
for order in all_orders:
    output = format_booking_line(order)
    print(output)


# =========================
# 🧾 GYG
# =========================

crawler = GYGCrawler(driver, start_date, end_date)
# 4️⃣ 自动翻页并采集
all_orders = crawler.crawl_all_pages()
# print(all_orders)
save_orders_to_txt(all_orders, output_file, append=True)
# 5️⃣ 格式化输出
for order in all_orders:
    output = format_booking_line(order)
    print(output)


# =========================
# 🧾 KLK
# =========================

crawler = KLKCrawler(driver, start_date, end_date)
# 4️⃣ 自动翻页并采集
all_orders = crawler.crawl_all_pages()
# print(all_orders)
save_orders_to_txt(all_orders, output_file, append=True)
# 5️⃣ 格式化输出
for order in all_orders:
    output = format_booking_line(order)
    print(output)


# =========================
# 🧾 Viator
# =========================

for i in range(3):
    crawler = ViatorCrawler(driver, start_date, end_date)
    # 4️⃣ 自动翻页并采集
    all_orders = crawler.crawl_all_pages()
    # print(all_orders)
    save_orders_to_txt(all_orders, output_file, append=True)
    # 5️⃣ 格式化输出
    for order in all_orders:
        output = format_booking_line(order)
        print(output)
