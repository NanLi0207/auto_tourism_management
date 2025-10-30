# -*- coding: utf-8 -*-
"""
将特定格式文本转为 iPhone vCard（.vcf）。

变更要点（2025-10-06）
- 备注 NOTE 现在只输出一行“地名 + 详细地址”（若有 Boat，则作为第二行单独输出）。
- “地名”取自 Hotel 的**首段**（逗号前），用于避免 Hotel 本身带有完整地址时的重复。
- “详细地址”取自 Google Maps 抓到的地址；会自动去重（若地址里重复出现与地名相同片段、
  或出现重复城市名/片段，将移除重复，仅保留一份）。
- 仍保留“阿姆斯特丹中央车站”特判：命中时**不写地址**，仅保留地名。
"""

import re
import time
import unicodedata
from typing import Optional, Tuple, List, Dict

# ===================== 可配置项 =====================
date = "a251025"

INPUT_FILE = f"{date}.txt"
OUTPUT_VCF = f"{date}.vcf"

# 是否启用 Google Maps 地址抓取（不影响“中央车站”的不写地址策略）
ENABLE_MAPS_LOOKUP = True

# Google Maps 界面与地址语言："en" / "zh-CN" / "zh-TW" 等
MAPS_HL = "en"

# 仅在抓到地址时才写入“Address:” 行（本版已不使用文本标签，仅控制是否尝试写入地址）；
# 若为 False，未抓到时也不会写“未找到”，而是仅输出地名。
ONLY_WRITE_ADDRESS_IF_FOUND = True

# Selenium 等待时间（秒）
SELENIUM_SHORT_WAIT = 4
SELENIUM_LONG_WAIT = 12

# ======== 固定城市中心：阿姆斯特丹市中心（Dam Square 一带）========
CENTER_MAP_AT_CITY_CENTER = True
CITY_CENTER_LAT = 52.3728
CITY_CENTER_LNG = 4.8936
CITY_CENTER_ZOOM = 13  # 12~14: 覆盖整个阿姆斯特丹较合适

# 搜索词是否自动追加“near Amsterdam / 附近 阿姆斯特丹”（避免跨城干扰）
APPEND_CITY_TO_QUERY = True
CITY_FOR_QUERY_EN = "Amsterdam"
CITY_FOR_QUERY_ZH = "阿姆斯特丹"

# 请求节流（每次搜索间隔秒数，避免频繁请求）
SEARCH_THROTTLE_SECONDS = 0.6

# --------- 特判：阿姆斯特丹中央车站 ----------
ENABLE_SPECIAL_CASES = True
# 对“central/centraal/中央车站”等泛称，若未写“Amsterdam/阿姆斯特丹”，是否仍默认视为阿姆斯特丹中央？
ASSUME_AMS_FOR_GENERIC_CENTRAL = True
# 是否对阿姆斯特丹中央车站 **抑制写 Address 行**
SUPPRESS_ADDRESS_FOR_AMS_CENTRAL = True

# ===================== 解析与 vCard 工具 =====================
COLON = r"[:：]"

LINE_PATTERN = re.compile(
    rf"^(?P<last>.*?)\s+Notes{COLON}\s*Phone{COLON}\s*(?P<phone>\S+)\s+Hotel{COLON}\s*(?P<hotel>.*?)(?:\s+Boat{COLON}\s*(?P<boat>\S+))?(?:\s+Email{COLON}\s*(?P<email>\S+))?\s*$"
)


def vcard_escape(value: str) -> str:
    """vCard 字段转义：反斜杠、换行、逗号、分号"""
    value = value.replace("\\", "\\\\")
    value = value.replace("\r", "")
    value = value.replace("\n", "\\n")
    value = value.replace(",", "\\,")
    value = value.replace(";", "\\;")
    return value


def fold_vcard_line(line: str, limit_bytes: int = 75) -> str:
    """按 vCard 规范做行折叠（UTF-8 字节计数）"""
    encoded = line.encode("utf-8")
    if len(encoded) <= limit_bytes:
        return line
    parts = []
    remaining = line
    while True:
        acc, acc_bytes = "", 0
        for ch in remaining:
            b = len(ch.encode("utf-8"))
            if acc_bytes + b > limit_bytes:
                break
            acc += ch
            acc_bytes += b
        parts.append(acc)
        if len(acc) == len(remaining):
            break
        remaining = " " + remaining[len(acc) :]
        if len(remaining.encode("utf-8")) <= limit_bytes:
            parts.append(remaining)
            break
    return "\r\n".join(parts)


def parse_line(line: str) -> Tuple[str, str, str, Optional[str], Optional[str]]:
    line = line.strip()
    if not line:
        raise ValueError("空行")
    m = LINE_PATTERN.match(line)
    if not m:
        raise ValueError(f"无法解析该行：{line}")
    last = m.group("last") or ""
    phone = m.group("phone") or ""
    hotel = m.group("hotel") or ""
    boat = m.group("boat") or ""
    email = m.group("email") or ""
    return last, phone, hotel, boat, email


# ===================== 文本规范化/去重工具 =====================
def _normalize_text(s: str) -> str:
    """NFKC 统一、去音标、转小写；保留中英文和数字；其它记号转空格"""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # 去音标
    s = s.lower().strip()
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_key(s: str) -> str:
    """用于去重的 key：去音标 + casefold + 去首尾标点空白"""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip(" ,;.-").casefold()


def extract_place_from_pickup(hotel: str) -> str:
    """
    从 Hotel 中提取“地名”。
    规则：优先取第一个逗号前的部分；若无逗号，则直接返回原串。
    例：
      "The Hoxton, Amsterdam, Herengracht 255, 1016 BJ" -> "The Hoxton"
      "Die Port Van Cleve, Nieuwezijds Voorburgwal 176-180, 1012 SJ Amsterdam" -> "Die Port Van Cleve"
      "Wittenberg by Cove" -> "Wittenberg by Cove"
    """
    if not hotel:
        return ""
    head, sep, tail = hotel.partition(",")
    return (head if sep else hotel).strip()


def merge_place_and_address(place: str, address: str) -> str:
    """
    生成“地名 + 详细地址”单行文本；自动去掉重复片段（含地名重复、城市名重复等）。
    - place: 地名（酒店/景点名等）
    - address: 从 Google Maps 解析出的地址字符串（通常以逗号分隔各字段）
    """
    place = (place or "").strip()
    address = (address or "").strip()

    if not place and not address:
        return ""

    # 将地址按逗号切片，逐段去重（保留顺序）
    parts_raw = [p.strip() for p in address.split(",") if p.strip()]
    place_key = _norm_key(place) if place else None

    out_parts: List[str] = []
    seen: set = set()

    for p in parts_raw:
        key = _norm_key(p)
        # 跳过与地名等价的片段（避免地址里又重复地名）
        if place and key == place_key:
            continue
        # 跳过已出现过的片段（如 "Amsterdam" 重复两次）
        if key in seen:
            continue
        seen.add(key)
        out_parts.append(p)

    if place and out_parts:
        return f"{place}, " + ", ".join(out_parts)
    elif place and not out_parts:
        return place
    else:
        return ", ".join(out_parts)


# ===================== 离线特判：阿姆斯特丹中央车站（用于“是否抑制 Address 行”） =====================
def is_ams_central_alias(place: str) -> bool:
    """
    判断文本是否表示阿姆斯特丹中央车站的“各种写法”
    """
    raw = place or ""
    norm = _normalize_text(raw)
    CENTRAL_STATION = {
        "中央車站",
        "中央车站",
        "中心車站",
        "中心车站",
        "火车总站",
        "火車总站",
        "中央火车站",
        "中央火車站",
        "中心火车站",
        "中心火車站",
        "阿姆斯特丹",
        "阿姆斯特丹车站",
        "阿姆斯特丹車站",
        "阿姆斯特丹火车站",
        "阿姆斯特丹火車站",
        "阿姆斯特丹中心站",
        "阿姆斯特丹中央车站",
        "阿姆斯特丹中央車站",
        "阿姆斯特丹中心车站",
        "阿姆斯特丹中心車站",
        "阿姆斯特丹中央火车站",
        "阿姆斯特丹中央火車站",
        "阿姆斯特丹中心火车站",
        "阿姆斯特丹中心火車站",
        "阿姆斯特丹中央车站上车",
        "阿姆斯特丹中央車站上車",
        "阿姆斯特丹中心车站上车",
        "阿姆斯特丹中心車站上車",
        "阿姆斯特丹中心站(Amsterdam Centraal)",
        "荷兰中央火车火车站",
        "荷兰中央火車火車站",
        "Central Station",
        "Amsterdam Central Station",
        "Amsterdam centraal station",
        "Amsterdam Central Bus Station",
        "Amsterdam Central Train Station",
        "Centraal Station Metro Station",
        "Train station central Amsterdam",
        "amsterdam central station",
        "Amsterdam central train station",
        "Amsterdam  central station",
        "Amsterdam cent r a a l station",
        "Amsterdam Centraal Station, J Platform (Bus)",
        "Amsterdam central railway station",
        "Station Amsterdam Centraal",
    }

    # 中文强匹配
    if norm in CENTRAL_STATION:
        return True

    return False


def should_suppress_address(place: str) -> bool:
    """是否因“阿姆斯特丹中央车站”而抑制 Address 行"""
    if not ENABLE_SPECIAL_CASES or not SUPPRESS_ADDRESS_FOR_AMS_CENTRAL:
        return False
    return is_ams_central_alias(place)


# ===================== Selenium + Google Maps 抓取 =====================
driver = None
wait = None
_pickup_cache: Dict[str, str] = {}  # 简单缓存


def _init_driver():
    """启动 Chrome，禁用地理定位"""
    global driver, wait
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait

    options = Options()
    options.add_argument(f"--lang={MAPS_HL}")
    options.add_argument("--incognito")
    # 如需无头运行请放开：
    # options.add_argument("--headless=new")
    # options.add_argument("--window-size=1280,900")

    # 禁用地理定位，避免按当前物理位置偏置结果
    options.add_experimental_option(
        "prefs",
        {"profile.default_content_setting_values.geolocation": 2},  # 2=block
    )
    options.add_argument("--disable-geolocation")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, SELENIUM_SHORT_WAIT)


def _accept_cookies():
    """快速接受 Cookie 弹窗（如有）"""
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        btn = WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@aria-label, 'Accept')]")
            )
        )
        btn.click()
        time.sleep(0.3)
    except:
        pass


def _goto_first_place_from_list() -> bool:
    """在搜索列表页，抓取左侧 feed 中首个 /maps/place/ 链接进入详情"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='feed']"))
        )
        anchors = driver.find_elements(
            By.XPATH, "//div[@role='feed']//a[contains(@href, '/maps/place/')]"
        )
        if not anchors:
            return False
        href = anchors[0].get_attribute("href")
        if not href:
            return False
        driver.get(href)
        WebDriverWait(driver, SELENIUM_LONG_WAIT).until(
            lambda d: "/maps/place/" in d.current_url
        )
        return True
    except:
        return False


def _extract_address() -> str:
    """
    提取详情页地址：
    1) 优先：按钮 aria-label 以 "Address:"（英文）或 "地址"（中文）开头
    2) 兜底：data-item-id='address' 或常见 class
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    # 1) aria-label 方式
    try:
        addr_btn = WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//button[starts-with(@aria-label,'Address:') or starts-with(@aria-label,'地址') or @data-item-id='address']",
                )
            )
        )
        label = addr_btn.get_attribute("aria-label") or ""
        if label:
            for sep in [":", "：", " - "]:
                if sep in label:
                    return label.split(sep, 1)[1].strip()
        txt = addr_btn.text.strip()
        if txt:
            return txt
    except:
        pass

    # 2) 详情面板常见块
    for xp in [
        "//div[@data-item-id='address']//div[contains(@class,'Io6YTe')]",
        "//div[contains(@class,'Io6YTe')][contains(., ',')]",  # 粗略兜底
    ]:
        try:
            el = WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
                EC.presence_of_element_located((By.XPATH, xp))
            )
            txt = el.text.strip()
            if txt:
                return txt
        except:
            continue

    return ""


def _search_address(place: str) -> str:
    """以阿姆斯特丹市中心为默认地图中心进行搜索并抓取地址"""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait

    if not place:
        return ""

    # 命中缓存直接返回
    if place in _pickup_cache:
        return _pickup_cache[place]

    # 固定在阿姆斯特丹市中心
    if CENTER_MAP_AT_CITY_CENTER:
        base_url = (
            f"https://www.google.com/maps/@{CITY_CENTER_LAT},{CITY_CENTER_LNG},{CITY_CENTER_ZOOM}z"
            f"?hl={MAPS_HL}&gl=nl"
        )
    else:
        base_url = f"https://www.google.com/maps?hl={MAPS_HL}&gl=nl"

    driver.get(base_url)
    _accept_cookies()

    # 智能追加城市限定，避免跨城匹配（含中文/英文）
    text_lower = place.lower()
    has_city = ("amsterdam" in text_lower) or ("阿姆斯特丹" in place)
    query = place
    if APPEND_CITY_TO_QUERY and not has_city:
        if MAPS_HL.startswith("en"):
            query = f"{place} near {CITY_FOR_QUERY_EN}"
        else:
            query = f"{place} 附近 {CITY_FOR_QUERY_ZH}"

    try:
        search_box = wait.until(lambda d: d.find_element(By.ID, "searchboxinput"))
        search_box.clear()
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)

        WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            lambda d: "/maps/place/" in d.current_url
            or d.find_elements(By.XPATH, "//div[@role='feed']//div[@role='article']")
        )

        # 列表页 → 进入第一条详情
        if "search" in driver.current_url and "/maps/place/" not in driver.current_url:
            ok = _goto_first_place_from_list()
            if not ok:
                _pickup_cache[place] = ""
                time.sleep(SEARCH_THROTTLE_SECONDS)
                return ""

        addr = _extract_address().strip()
        _pickup_cache[place] = addr
        time.sleep(SEARCH_THROTTLE_SECONDS)
        return addr
    except Exception:
        _pickup_cache[place] = ""
        time.sleep(SEARCH_THROTTLE_SECONDS)
        return ""


# ===================== vCard 生成 =====================
def make_vcard_contact(
    last: str,
    phone: str,
    hotel: str,
    boat: Optional[str],
    email: Optional[str],
    pickup_address: Optional[str],
    suppress_address: bool = False,
) -> str:
    """
    NOTE 多行（本版简化为 1~2 行）：
      1) <Place + Address>   # 从 hotel 提取地名，与抓到的地址合并并去重；若抑制或未抓到地址，仅为地名
      2) <Boat>              # 若存在
    """
    # 从 Hotel 提取 “地名”（首段）
    place = extract_place_from_pickup(hotel)

    # 生成 NOTE 的第一行
    if suppress_address:
        line1 = place or (hotel or "").strip()
    else:
        if pickup_address:
            line1 = merge_place_and_address(place or hotel, pickup_address)
        else:
            # 未抓到地址：仅输出地名
            line1 = place or (hotel or "").strip()

    # 判断是否包船
    boat_flag = "Yes"

    if boat:
        b = boat.strip().lower()
        if b in ["yes", "y", "true", "1", "包船", "含船"]:
            boat_flag = "Yes"
        elif b in ["no", "n", "false", "0", "不包船", "不含船"]:
            boat_flag = "No"
        else:
            boat_flag = "Unknown"

    # 构建新格式 NOTE 内容
    note_text = (
        f"H: {line1.strip() if line1 else ''}\nB: {boat_flag}\n\nT: \nL: \nN: \nO: "
    )

    last_esc = vcard_escape((last or "").strip())
    fn_esc = last_esc
    note_esc = vcard_escape(note_text)

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{last_esc};;;;",  # 姓填充，名留空
        f"FN:{fn_esc}",
        f"TEL;TYPE=CELL:{phone or ''}",
        f"EMAIL;TYPE=INTERNET:{email or ''}",
        f"NOTE:{note_esc}",
        "END:VCARD",
    ]
    folded = [fold_vcard_line(l) for l in lines]
    return "\r\n".join(folded)


# ===================== 主转换逻辑 =====================
def convert_file_to_vcf(input_path: str, output_path: str) -> List[str]:
    errors = []
    vcards = []
    need_driver = ENABLE_MAPS_LOOKUP

    try:
        if need_driver:
            _init_driver()

        with open(input_path, "r", encoding="utf-8") as f:
            for ln, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    last, phone, hotel, boat, email = parse_line(raw)

                    # 是否因为“阿姆斯特丹中央车站”而抑制 Address 行
                    place_for_check = extract_place_from_pickup(hotel)
                    suppress_addr = should_suppress_address(place_for_check or hotel)

                    pickup_addr = ""
                    if (hotel and not suppress_addr) and ENABLE_MAPS_LOOKUP:
                        # 这里仍用原始 hotel 去搜，命中率更高；合并时再只取地名
                        pickup_addr = _search_address(hotel)

                    vcards.append(
                        make_vcard_contact(
                            last=last,
                            phone=phone,
                            hotel=hotel,
                            boat=boat,
                            email=email,
                            pickup_address=(pickup_addr if pickup_addr else None),
                            suppress_address=suppress_addr,
                        )
                    )
                except Exception as e:
                    errors.append(f"Line {ln}: {e}")
    finally:
        if need_driver and driver is not None:
            try:
                driver.quit()
            except:
                pass

    content = "\r\n".join(vcards) + ("\r\n" if vcards else "")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)

    return errors


if __name__ == "__main__":
    errs = convert_file_to_vcf(INPUT_FILE, OUTPUT_VCF)
    if errs:
        print("以下行无法解析或写入，请检查：")
        for e in errs:
            print("  -", e)
    else:
        print(f"转换完成：{OUTPUT_VCF}")
