import re
import phonenumbers
from phonenumbers import region_code_for_number


def format_phone_number(phone: str) -> str:
    """
    将电话号码中的空格、短横线、括号等去掉，保留 + 和数字。
    例如：'+1 360-421-2668' -> '+13604212668'
    """
    if not phone:
        return ""
    # 去掉除 + 和 数字 以外的字符
    return re.sub(r"[^\d+]", "", phone)


def extract_country_code_from_phone(phone: str) -> str:
    """
    根据手机号提取国家缩写（如 +31 -> NL, +91 -> IN）。
    如果解析失败，返回 'XX'。
    """
    if not phone:
        return "XX"
    try:
        clean_phone = format_phone_number(phone)
        parsed = phonenumbers.parse(clean_phone, None)
        country_code = region_code_for_number(parsed)
        return country_code if country_code else "XX"
    except Exception:
        return "XX"


def format_booking_line(order):
    """
    格式化订单信息为：
    aYYMMDD Country Count Name GroupName GYG Notes: Phone: xxx Hotel: xxx
    """

    # 获取字段
    date_str = order.get("activityDate", "a000000")
    country = order.get("travelerCountry", "XX")
    count = order.get("travelerCount", 0)
    name = order.get("travelerName", "Unknown")
    group = order.get("groupName", "Unknown")
    language = order.get("language", "EN")
    phone = order.get("travelerPhone", "Unknown")
    hotel = order.get("travelerHotel", "Unknown")
    platform = order.get("platformName", "Unknown")

    # 拼接输出
    # 📌 按顺序收集要输出的字段
    parts = [date_str, country, str(count), name, group]

    # 📌 只有语言不是 EN 时才加
    if language and language.upper() != "EN":
        parts.append(language)

    parts.append(platform)

    # 📌 拼 Notes
    notes = f"Notes: Phone: {phone} Hotel: {hotel}"

    # 拼接成一行
    line = " ".join(parts) + " " + notes
    return line


def save_orders_to_txt(orders, output_path="orders.txt", sort_by=None, append=False):
    """
    保存订单信息到 txt 文件
    - orders: 订单列表
    - output_path: 输出文件路径
    - sort_by: 可选，按照某个字段排序
    - append: 是否追加写入（True）或覆盖（False）
    """
    if sort_by:
        orders = sorted(orders, key=lambda x: x.get(sort_by, ""))

    mode = "a" if append else "w"
    with open(output_path, mode, encoding="utf-8") as f:
        for order in orders:
            f.write(format_booking_line(order) + "\n")

    print(
        f"✅ 已将 {len(orders)} 条订单写入 {output_path} （{'追加' if append else '覆盖'}）"
    )
