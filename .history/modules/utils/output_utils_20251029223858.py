# utils/phone_and_format.py
# =====================================================
# 📞 电话号码清洗 & 📄 订单格式化工具
# - 清洗和解析国际电话号码
# - 提取国家代码
# - 格式化订单行
# - 保存订单列表到 TXT
# =====================================================

import re
from typing import Dict, List, Optional, Union
import phonenumbers
from phonenumbers import region_code_for_number


# =====================================================
# 📞 电话号码处理
# =====================================================


def format_phone_number(phone: str) -> str:
    """
    清洗电话号码，仅保留 `+` 与数字。

    示例：
        '+1 360-421-2668' -> '+13604212668'

    Args:
        phone (str): 原始电话号码字符串。

    Returns:
        str: 清洗后的电话号码。若输入为空则返回空字符串。
    """
    if not phone:
        return ""
    return re.sub(r"[^\d+]", "", phone)


def extract_country_code_from_phone(phone: str) -> str:
    """
    根据电话号码提取国家缩写（如 +31 -> NL, +91 -> IN）。

    使用 `phonenumbers` 库进行国际号码解析。

    Args:
        phone (str): 电话号码字符串（支持含空格、括号、短横线的原始格式）。

    Returns:
        str: 国家 ISO2 缩写（如 "NL", "IN"）。解析失败时返回 "XX"。
    """
    if not phone:
        return "XX"
    try:
        clean_phone = format_phone_number(phone)
        parsed = phonenumbers.parse(clean_phone, None)
        country_code = region_code_for_number(parsed)
        return country_code if country_code else "XX"
    except Exception as e:
        # ⚠️ 在生产环境中建议改成 logger.warning
        print(f"⚠️ 电话号码解析失败: {phone} ({e})")
        return "XX"


# =====================================================
# 📄 订单格式化
# =====================================================


def format_booking_line(order: Dict[str, Union[str, int, None]]) -> str:
    """
    将订单信息格式化为标准文本行。

    格式：
        aYYMMDD Country Count Name GroupName [Language] Platform Notes: Phone: xxx Hotel: xxx [Boat: xxx]

    示例：
        a240823 NL 3 Zhang San TourEN EN CT Notes: Phone: +31612345678 Hotel: Hilton Boat: 包船

    Args:
        order (dict): 包含订单信息的字典。常见字段：
            - activityDate (str): 活动日期（如 a240823）
            - travelerCountry (str): 国家缩写
            - travelerCount (int): 人数
            - travelerName (str): 姓名
            - groupName (str): 团代码
            - language (str): 语言（EN/CN）
            - travelerPhone (str): 电话
            - travelerHotel (str): 酒店
            - platformName (str): 平台名称
            - isBoat (str): 是否包含船信息

    Returns:
        str: 格式化后的订单行字符串。
    """
    date_str = str(order.get("activityDate", "a000000"))
    country = str(order.get("travelerCountry", "XX"))
    count = str(order.get("travelerCount", 0))
    name = str(order.get("travelerName", "Unknown"))
    group = str(order.get("groupName", "Unknown"))
    language = str(order.get("language", "EN"))
    phone = str(order.get("travelerPhone", "Unknown"))
    hotel = str(order.get("travelerHotel", "Unknown"))
    platform = str(order.get("platformName", "Unknown"))
    isboat = str(order.get("isBoat") or "")

    # 📌 组装主字段
    parts = [date_str, country, count, name, group]

    # 仅当语言不是 EN 时追加
    if language and language.upper() != "EN":
        parts.append(language)

    parts.append(platform)

    # 📌 组装备注 Notes
    notes_parts = [f"Notes: Phone: {phone}", f"Hotel: {hotel}"]
    if isboat:
        notes_parts.append(f"Boat: {isboat}")

    return " ".join(parts) + " " + " ".join(notes_parts)


def save_orders_to_txt(
    orders: List[Dict[str, Union[str, int, None]]],
    output_path: str = "orders.txt",
    sort_by: Optional[str] = None,
    append: bool = False,
) -> None:
    """
    将订单列表保存为 TXT 文件，每行一个订单。

    Args:
        orders (list[dict]): 订单信息列表。
        output_path (str, optional): 输出文件路径。默认为 "orders.txt"。
        sort_by (str, optional): 若指定，则按该字段排序输出。
        append (bool, optional): 是否追加写入，默认为 False（覆盖写入）。

    Notes:
        - 若订单列表为空，将不会创建文件。
        - 若 sort_by 对应字段缺失，将按空字符串排序。

    Example:
        >>> save_orders_to_txt(order_list, "output.txt", sort_by="activityDate", append=True)
        ✅ 已将 10 条订单写入 output.txt （追加）
    """
    if not orders:
        print("⚠️ 订单列表为空，未生成文件")
        return

    if sort_by:
        orders = sorted(orders, key=lambda x: str(x.get(sort_by, "")))

    mode = "a" if append else "w"
    with open(output_path, mode, encoding="utf-8") as f:
        for order in orders:
            f.write(format_booking_line(order) + "\n")

    action = "追加" if append else "覆盖"
    print(f"✅ 已将 {len(orders)} 条订单写入 {output_path} （{action}）")
