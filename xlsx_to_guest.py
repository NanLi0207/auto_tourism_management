import pandas as pd
import re
from datetime import datetime

# ====== 导游信息 ======
guide_info = {
    "PT": {
        "name": "Pete",
        "phone": "+31 6 38 68 38 39",
        "plate": "ZV-653-G",
        "car": "Black Mercedes van",
        "lang": "EN",
    },
    "RE": {
        "name": "Reinier",
        "phone": "+31 6 18 01 07 47",
        "plate": "G-746-NF",
        "car": "Black Mercedes van",
        "lang": "EN",
    },
    "LZ": {
        "name": "Leidse",
        "phone": "+31 6 41 32 32 64",
        "plate": "NK-125-S",
        "car": "Black Mercedes van",
        "lang": "EN",
    },
    "KA": {
        "name": "Kai",
        "phone": "+31 6 29 17 27 81",
        "plate": "R-278-JT",
        "car": "Black Mercedes van",
        "lang": "EN",
    },
    "LY": {
        "name": "Eric",
        "phone": "+31 6 38 37 65 77",
        "plate": "X-010-ZF",
        "car": "Black Mercedes van",
        "lang": "EN",
    },
    "SM": {
        "name": "Simon",
        "phone": "+31 6 47 05 07 46",
        "plate": "T-278-JF",
        "car": "Brown Mercedes van",
        "lang": "EN",
    },
    "SR": {
        "name": "苏瑞 苏导",
        "phone": "+31 6 51 22 21 38",
        "plate": "G-746-NF",
        "car": "黑色奔驰商务车",
        "lang": "CN",
    },
    "KD": {
        "name": "Kendall 邓导",
        "phone": "+31 6 86 05 77 66",
        "plate": "KB-585-F",
        "car": "银色奔驰商务车",
        "lang": "CN",
    },
    "Unknown": {
        "name": "Unknown",
        "phone": "N/A",
        "plate": "N/A",
        "car": "Mercedes van",
        "lang": "EN",
    },
}

# ====== 团代码映射 ======
tour_map = {
    "GAZ": "Zaanse Schans, Afsluitdijk and Giethoorn",
    "GZZ": "Zaanse Schans, Lego Village and Giethoorn",
    "GZ": "Zaanse Schans and Giethoorn",
    "RDD": "Rotterdam, Delft and The Hague",
    "RDD-D": "Rotterdam, Delft and The Hague",
    "RDD-M": "Rotterdam, Delft and The Hague",
}

# ====== 读取 Excel ======
df = pd.read_excel("a251010_full_ad.xlsx")


def parse_note(note: str) -> dict:
    """
    将 note 按行解析成 {KEY: value} 字典，只取同一行冒号后的内容。
    例如：'HOTEL: Amsterdam Marriott Hotel, ...' → {'HOTEL': 'Amsterdam Marriott Hotel, ...'}
    """
    fields = {}
    for raw in note.splitlines():
        m = re.match(r"^\s*([A-Za-z]+)\s*:\s*(.*)\s*$", raw)
        if m:
            key = m.group(1).upper()
            value = m.group(2).strip()
            fields[key] = value  # 如果同一个 key 多次出现，以最后一次为准
    return fields


# ====== 提取信息函数 ======
def extract_info(full_name, note):
    parts = full_name.split()
    if len(parts) < 5:
        return "⚠️ 信息格式错误，请检查输入。"

    # --- 基本解析 ---
    tour_date, country, people = parts[0], parts[1], parts[2]

    # 判断是否中文团（含 CN 或 CT）
    is_cn = "CN" in parts

    # 游客姓名提取
    if is_cn:
        guest_name = " ".join(parts[3:-4])
    else:
        guest_name = " ".join(parts[3:-3])

    # 导游代码
    guide_code = parts[-1] if parts[-1] in guide_info else "Unknown"
    guide = guide_info[guide_code]

    # 团名识别
    tour_code = next((p for p in parts if p in tour_map), None)
    tour_name = tour_map.get(tour_code, "your booked tour")

    # === note 字段提取 ===
    fields = parse_note(note)
    hotel_raw = fields.get("HOTEL", "") or fields.get("H")
    boat_raw = fields.get("BOAT", "") or fields.get("B")
    t_raw = fields.get("T", "")
    meeting_raw = fields.get("L", "")
    reason_raw = fields.get("N", "")
    other_raw = fields.get("O", "")

    # 只取 T 行的第一个时间（如 T: 8:20 (8:25) → 8:20）
    m_time = re.search(r"\b\d{1,2}:\d{2}\b", t_raw)
    pickup_time = m_time.group(0) if m_time else ""

    # === 分离酒店信息 ===
    hotel_name, hotel_street, hotel_zipcode = "", "", ""
    if "," in hotel_raw:
        parts_hotel = [p.strip() for p in hotel_raw.split(",")]
        if len(parts_hotel) >= 3:
            hotel_name = parts_hotel[0]
            hotel_street = parts_hotel[1]
            hotel_zipcode = ", ".join(parts_hotel[2:])
        elif len(parts_hotel) == 2:
            hotel_name = parts_hotel[0]
            hotel_street = parts_hotel[1]
        elif len(parts_hotel) == 1:
            hotel_name = parts_hotel[0]
    else:
        hotel_name = hotel_raw.strip()

    # === 分离meeting point信息 ===
    meeting_name, meeting_street, meeting_zipcode = "", "", ""
    if "," in meeting_raw:
        parts_meeting = [p.strip() for p in meeting_raw.split(",")]
        if len(parts_meeting) >= 3:
            meeting_name = parts_meeting[0]
            meeting_street = parts_meeting[1]
            meeting_zipcode = ", ".join(parts_meeting[2:])
        elif len(parts_meeting) == 2:
            meeting_name = parts_meeting[0]
            meeting_street = parts_meeting[1]
        elif len(parts_meeting) == 1:
            meeting_name = parts_meeting[0]
    else:
        meeting_name = meeting_raw.strip()

    # === 模板类型判断 ===
    if "CS" in reason_raw:
        template_type = 3
    elif meeting_raw:
        template_type = 2
    else:
        template_type = 1

    # === 时间问候 ===
    hour = datetime.now().hour
    if hour < 12:
        greeting = "早上好" if guide["lang"] == "CN" else "Good morning"
    elif hour < 18:
        greeting = "下午好" if guide["lang"] == "CN" else "Good afternoon"
    else:
        greeting = "晚上好" if guide["lang"] == "CN" else "Good evening"

    # === 模板生成 ===
    if guide["lang"] == "CN":
        if template_type == 1:
            text = f"""{greeting} {guest_name},

您预订了明天的行程：{tour_name.replace(" and ", "和")}。

首先欢迎来到荷兰，感谢您选择我们。

明天您的司机兼导游是：{guide["name"]}
电话号码：{guide["phone"]}
汽车车牌号码：{guide["plate"]}
{guide["car"]}。

请确认您的酒店名称和地址：
{hotel_name},
{hotel_street},
{hotel_zipcode}

我们的司导将在早上{pickup_time}右到您酒店接您。
烦请确认上面信息并回复，非常感谢。

祝好，
Dan
"""
        elif template_type == 2:
            text = f"""{greeting} {guest_name},

您预订了明天的行程：{tour_name.replace(" and ", "和")}。

首先欢迎来到荷兰，感谢您选择我们。

明天您的司机兼导游是：{guide["name"]}
电话号码：{guide["phone"]}
汽车车牌号码：{guide["plate"]}
{guide["car"]}。

请确认您的酒店名称和地址：
{hotel_name},
{hotel_street},
{hotel_zipcode}

***手动输入原因***明天您可以在您酒店旁边下面的这个见面地址上车。离您酒店走路大概***手动输入步行时间***分钟。

见面地址：
{meeting_name},
{meeting_street},
{meeting_zipcode}

我们的司导将在早上{pickup_time}分左右在这个见面地址接您。

烦请确认上面信息并回复，非常感谢。

祝好，
Dan
"""
        else:
            text = f"""{greeting} {guest_name},

您预订了明天的行程：{tour_name.replace(" and ", "和")}。
首先欢迎来到荷兰，感谢您选择我们。

明天您的司机兼导游是：{guide["name"]}
电话号码：{guide["phone"]}
汽车车牌号码：{guide["plate"]}
{guide["car"]}。

***这个是车站相关的***

见面地址：
{meeting_name},
{meeting_street},
{meeting_zipcode}

我们的司导将在早上{pickup_time}分左右在这个见面地址接您。

烦请确认上面信息并回复，非常感谢。

祝好，
Dan
"""
    else:  # 英文模板
        if template_type == 1:
            text = f"""{greeting} {guest_name},

You booked a tour with us tomorrow to {tour_name}.
First welcome to the Netherlands, and thank you for booking with us.

Tomorrow your driver and tour guide is: {guide["name"]}, mobile number: {guide["phone"]}. Car license plate number: {guide["plate"]}. {guide["car"]}.

Could you please confirm your hotel name and address?

{hotel_name},
{hotel_street},
{hotel_zipcode}

Tomorrow our tour guide will pick you up from your hotel around {pickup_time}.
Thanks!!! Could you reply to confirm?

Regards,
Dan
"""
        elif template_type == 2:
            text = f"""{greeting} {guest_name},

You booked a tour with us tomorrow to {tour_name}.
First welcome to the Netherlands, and thank you for booking with us.

Tomorrow your driver and tour guide is: {guide["name"]}, mobile number: {guide["phone"]}. Car license plate number: {guide["plate"]}. {guide["car"]}.

Could you please confirm your hotel name and address?

{hotel_name},
{hotel_street},
{hotel_zipcode}

手动输入原因 Tomorrow could you please meet us at the following meeting point near your hotel?

Meeting point:
{meeting_name},
{meeting_street},
{meeting_zipcode}

手动输入位置信息
Tomorrow our tour guide will pick you up there around {pickup_time}.
Thanks!!! Could you reply to confirm?

Regards,
Dan
"""
        else:
            text = f"""{greeting} {guest_name},

First welcome to the Netherlands, and thank you for booking with us.

Tomorrow your driver and tour guide is: {guide["name"]}, mobile number: {guide["phone"]}. Car license plate number: {guide["plate"]}. {guide["car"]}.

Tomorrow could you please meet us at the following meeting point near Amsterdam central station?

Meeting point: 
{meeting_name},
{meeting_street},
{meeting_zipcode}

This meeting point is about 手动输入步行时间 from central station.  

Tomorrow our tour guide will pick you up there around {pickup_time}.
Thanks!!! Could you reply to confirm?

Regards,
Dan
"""
    return text


# ====== 应用函数并导出 ======
df["Email_text"] = df.apply(lambda x: extract_info(x["full_name"], x["note"]), axis=1)
output_file = "tour_emails_output.xlsx"
df.to_excel(output_file, index=False)
print(f"✅ 已生成邮件文本并保存至 {output_file}")
