# -*- coding: utf-8 -*-
"""
从两列 Excel（fullname, note）生成每位导游的接客清单。

- fullname 两种格式：
  a251009 CN 1 Zhu ZhenXing GZZ CN FZ SR
  a251009 CA 2 Paul Rodie GAZ V1 RE
  规则：第1段a日期，第2段国家缩写，第3段人数，倒数1=导游，倒数2=平台，
        倒数3可为CN（中文团标记，可没有），倒数4=团名。中间为游客姓名。
- note 六键：
  H/Hotel: 初始地点
  B/Boat: Yes/No/Y/N → 输出“包船/不包船”
  T: 时间；若“08:00 (08:10)”，给导游取括号内的08:10，否则取外侧08:00
  L: 见面地点；为空→用Hotel；不空→用“L + (Hotel首个逗号前简称)”
  N: 给客人的提示（本脚本不输出）
  O: 其它（本脚本不输出）

输出：每位导游一个文件 schedules/schedule_<导游>.txt
"""

import os
import re
import unicodedata
from collections import defaultdict
import pandas as pd
from modules.utils.google_maps_lookup import (
    init_db as gm_init_db,
    init_driver as gm_init_driver,
    quit_driver as gm_quit_driver,
    search_address as gm_search_address,
    search_address_near as gm_search_address_near,  # ← 新增
    link_hotel_to_pickup as gm_link_hotel_to_pickup,
)


# ========= 基本配置 =========
INPUT_XLSX = "a251028.xlsx"
OUTPUT_DIR = "schedules"
GREETING_LINE = "哈喽 明天"
ITINERARY_FALLBACK = "（请填写行程）"

PLATFORMS = {"FZ", "V1", "V2", "V3", "GYG", "KLK", "CT", "WB"}
GUIDE_ORDER = ["PT", "RE", "LZ", "KA", "LY", "SM", "SR", "KD", "Unknown"]
COUNTRY_MAP = {
    "AU": "Australia",
    "US": "USA",
    "USA": "USA",
    "UK": "United Kingdom",
    "GB": "United Kingdom",
    "CN": "China",
    "KR": "Korea",
    "JP": "Japan",
    "DE": "Germany",
    "FR": "France",
    "NL": "Netherlands",
    "IT": "Italy",
    "ES": "Spain",
    "PT": "Portugal",
    "BE": "Belgium",
    "CH": "Switzerland",
    "AT": "Austria",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "FI": "Finland",
    "IE": "Ireland",
    "CA": "Canada",
    "NZ": "New Zealand",
    "SG": "Singapore",
    "MY": "Malaysia",
    "TH": "Thailand",
    "VN": "Vietnam",
    "PH": "Philippines",
    "IN": "India",
    "BR": "Brazil",
    "AR": "Argentina",
    "MX": "Mexico",
    "ZA": "South Africa",
    "HK": "HK",
    "TW": "Taiwan",
    "MO": "Macau",
    "MAU": "Mauritius",
    "IL": "Israel",
    "AE": "United Arab Emirates",
}


# ========= 小工具 =========
def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s) if s is not None else s


def country_display(code: str) -> str:
    if not code:
        return ""
    return COUNTRY_MAP.get(str(code).strip().upper(), str(code).strip())


def safe_filename(s: str) -> str:
    s = str(s or "UNKNOWN").strip()
    # Windows非法字符: \/:*?"<>| 以及控制字符
    s = re.sub(r'[\\/:*?"<>|\x00-\x1F]', "_", s)
    # 去掉结尾的点和空格，避免 Windows 特殊规则
    s = s.rstrip(" .")
    return s or "UNKNOWN"


def decide_itinerary_for_guide(items):
    groups = {
        str(r.get("group_code") or "").strip().upper()
        for r in items
        if r.get("group_code")
    }
    if "GAZ" in groups:
        return "风车村+拦海大坝+羊角村"
    elif "GZZ" in groups:
        return "风车村+乐高小镇+羊角村"
    elif "GZ" in groups and not ({"GAZ", "GZZ"} & groups):
        return "风车村+羊角村"
    elif "RDD-D" in groups:
        return "鹿特丹+代尔夫特+海牙Royal Delft, 不去Madurodam"
    elif "RDD-M" in groups:
        return "鹿特丹+代尔夫特+海牙Madurodam, 不去Royal Delft"
    elif "RDD" in groups and not ({"RDD-D", "RDD-M"} & groups):
        return "鹿特丹+代尔夫特+海牙"
    else:
        return ITINERARY_FALLBACK


# ========= fullname 解析 =========
def parse_fullname(fullname: str):
    """
    返回：
      {
        date_code, country_code, people_count, passenger_name,
        group_code, lang_cn(bool), platform, guide
      }
    """
    res = {
        "date_code": None,
        "country_code": None,
        "people_count": 0,
        "passenger_name": "",
        "group_code": None,
        "lang_cn": False,
        "platform": None,
        "guide": "UNKNOWN",
    }
    if not fullname:
        return res

    toks = nfkc(fullname).split()
    if len(toks) < 6:
        # 尝试兜底取末尾为导游
        if toks:
            res["guide"] = toks[-1]
        return res

    res["date_code"] = toks[0]
    res["country_code"] = toks[1]

    # 人数
    try:
        m = re.search(r"\d+", toks[2])
        res["people_count"] = int(m.group()) if m else 0
    except:
        res["people_count"] = 0

    # 尾部倒序解析
    res["guide"] = toks[-1]
    res["platform"] = toks[-2] if toks[-2].upper() in PLATFORMS else toks[-2]
    idx = -3
    lang_cn = False
    if len(toks) >= 7 and toks[idx].upper() == "CN":
        lang_cn = True
        idx -= 1
    res["lang_cn"] = lang_cn

    # 团名（可能缺失）
    group_code = toks[idx].upper() if (len(toks) >= abs(idx)) else None
    res["group_code"] = group_code

    # 姓名：第3段（下标3）到 group_code 前一段
    end_pos = len(toks) + idx  # group_code 的索引
    if 3 <= end_pos <= len(toks):
        name_tokens = toks[3:end_pos]
    else:
        # 如果 group_code 缺失，默认到 -2（平台）之前
        name_tokens = toks[3:-2] if len(toks) > 5 else []
    res["passenger_name"] = " ".join(name_tokens).strip()

    # 引导清洗：导游如果是“？”等非法字符，文件名会处理，这里保留原样
    return res


# ========= note 解析（结构化六键） =========
_STRUCT_KEY_RE = re.compile(r"^\s*([A-Za-z]+)\s*:\s*(.*)$")
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])\s*[:：]\s*([0-5]?\d)(?!\d)")


def _norm_time_to_hhmm(s: str, default="08:00"):
    if not s:
        return default
    m = TIME_RE.search(s)
    if not m:
        return default
    h, mm = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mm:02d}"


def _pick_guide_time(t_raw: str, default="08:00"):
    # "08:00 (08:10)" → 括号内；否则外侧
    if not t_raw:
        return default
    m = re.search(r"\(([^)]+)\)", t_raw)
    if m:
        return _norm_time_to_hhmm(m.group(1), default)
    return _norm_time_to_hhmm(t_raw, default)


def _parse_yes_no(v: str):
    if v is None:
        return None
    low = v.strip().lower()
    if low in {"yes", "y", "true", "1", "含船", "包船"}:
        return True
    if low in {"no", "n", "false", "0", "不含船", "不包船"}:
        return False
    return None


def _hotel_short_name(hotel_line: str) -> str:
    if not hotel_line:
        return ""
    return hotel_line.split(",", 1)[0].strip()


def extract_pickups_structured(note_text: str, default_time="08:00"):
    """
    返回列表：每项 dict(
        time_txt,          # 给导游用的时间（括号内优先）
        meeting_text,      # 见面地点（不含括号）
        boat_label,        # "包船"/"不包船"/""
        initial_short,     # HOTEL 逗号前简称
        hotel_full,        # HOTEL 完整行（用于查库与建绑定）
        changed            # 是否由 L 改过见面地点
    )
    """
    if not note_text:
        return []

    hotel_full = ""
    hotel_short = ""
    boat = None
    cur_T = None
    cur_L = None
    pickups = []

    def _pick_guide_time(t_raw: str, default="08:00"):
        if not t_raw:
            return default
        m = re.search(r"\(([^)]+)\)", t_raw)
        if m:
            return _norm_time_to_hhmm(m.group(1), default)
        return _norm_time_to_hhmm(t_raw, default)

    def flush_if_ready():
        nonlocal cur_T, cur_L
        if cur_T is None and cur_L is None:
            return
        guide_time = _pick_guide_time(cur_T or "", default=default_time)

        # 见面地点与是否改动（meeting_text 不加括号）
        if cur_L and cur_L.strip():
            meeting = cur_L.strip()
            changed = True
        else:
            meeting = hotel_full.strip()
            changed = False

        boat_label = "包船" if boat is True else ("不包船" if boat is False else "")

        pickups.append(
            {
                "time_txt": guide_time,
                "meeting_text": meeting,
                "boat_label": boat_label,
                "initial_short": _hotel_short_name(hotel_full),
                "hotel_full": hotel_full,
                "changed": changed,
            }
        )
        cur_T, cur_L = None, None

    lines = nfkc(note_text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for raw in lines:
        line = raw.strip()
        if not line:
            flush_if_ready()
            continue
        m = _STRUCT_KEY_RE.match(line)
        if not m:
            continue
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        if key in {"hotel", "h"}:
            flush_if_ready()
            hotel_full = val
            hotel_short = _hotel_short_name(val)
        elif key in {"boat", "b"}:
            boat = _parse_yes_no(val)
        elif key in {"t", "time"}:
            if cur_T or cur_L:
                flush_if_ready()
            cur_T = val
        elif key in {"l", "loc", "location", "meet", "meeting"}:
            cur_L = val
        elif key in {"n", "name", "o", "other", "note"}:
            pass
        else:
            pass

    flush_if_ready()
    return pickups


def _format_place_line(name: str, address: str, fallback: str) -> str:
    """
    优先输出：<地点全称>, <完整地址>
    其次：仅地址
    最后：fallback（原有文本）
    并做一点去重，避免 name 已经是 address 的一部分时重复。
    """
    name = (name or "").strip()
    address = (address or "").strip()
    if name and address:
        # 避免重复，比如有时 Maps 的 name 就是门牌地址
        if name.lower() in address.lower():
            return address
        return f"{name}, {address}"
    if address:
        return address
    if name:
        return name
    return fallback


def standardize_pickups_and_link(items_by_guide):
    """
    对所有导游的条目：
      - 若 changed=True（有 L），先用酒店坐标做“就近选择”的补全（pickup库），
        然后把 meeting_text 设置为“地点全称, 完整地址”（若无名称则退回地址/原文）；
        并在 pickup 库建立/更新：酒店(HOTEL) ↔ 见面点(L) 绑定（priority=1）
      - 若 changed=False（L 为空），可选：把酒店显示也统一成“酒店名, 地址”
    """
    gm_init_db("hotels")
    gm_init_db("pickup")
    gm_init_driver()
    try:
        for guide, items in items_by_guide.items():
            for r in items:
                pickup_query = (r.get("meeting_text") or "").strip()
                hotel_query = (r.get("hotel_full") or "").strip()

                # ---------- 情况 A：有 L（changed=True） ----------
                if r.get("changed"):
                    # 1) 先拿酒店坐标（就近选择要用）
                    hotel_lat = hotel_lng = None
                    if hotel_query:
                        try:
                            h = gm_search_address(hotel_query, db_kind="hotels") or {}
                            hotel_lat, hotel_lng = h.get("lat"), h.get("lng")
                        except Exception as e:
                            print(f"[Hotel enrich] '{hotel_query}' failed: {e}")

                    # 2) 对 L 做“就近选择”或普通补全
                    try:
                        if hotel_lat is not None and hotel_lng is not None:
                            meet = (
                                gm_search_address_near(
                                    pickup_query, hotel_lat, hotel_lng, db_kind="pickup"
                                )
                                or {}
                            )
                        else:
                            meet = (
                                gm_search_address(pickup_query, db_kind="pickup") or {}
                            )
                        name = (meet.get("name") or "").strip()
                        addr = (meet.get("address") or "").strip()

                        # ★ 关键行：把 meeting_text 设为“地点全称, 完整地址”（自动去重、兜底）
                        r["meeting_text"] = _format_place_line(
                            name, addr, r["meeting_text"]
                        )
                    except Exception as e:
                        print(f"[Pickup enrich near] '{pickup_query}' failed: {e}")

                    # 3) 建立/更新绑定（语义绑定，哪怕没取到完整地址也建立）
                    try:
                        if hotel_query:
                            gm_link_hotel_to_pickup(
                                hotel_query, pickup_query, priority=1, notes=""
                            )
                    except Exception as e:
                        print(f"[Link] {hotel_query} ⇄ {pickup_query} failed: {e}")

                # ---------- 情况 B：无 L（changed=False） ----------
                else:
                    # 可选：把酒店也标准化为“酒店名, 地址”，看起来更统一
                    if hotel_query:
                        try:
                            h = gm_search_address(hotel_query, db_kind="hotels") or {}
                            r["meeting_text"] = _format_place_line(
                                h.get("name"), h.get("address"), r["meeting_text"]
                            )
                        except Exception as e:
                            print(f"[Hotel enrich display] '{hotel_query}' failed: {e}")

    finally:
        gm_quit_driver()


# ========= 主流程 =========
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = pd.read_excel(INPUT_XLSX, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"full_name", "note"}.issubset(df.columns):
        raise ValueError("输入表必须包含列：full_name, note")

    # 为了计算“每位导游总人数”，按“行（订单）”去重累计
    orders_by_guide = defaultdict(list)  # guide -> list of order_people
    items_by_guide = defaultdict(list)  # guide -> list of output items

    for row_idx, row in df.iterrows():
        fullname = (row.get("full_name") or "").strip()
        note = row.get("note") or ""

        f = parse_fullname(fullname)
        guide = f.get("guide") or "UNKNOWN"
        people_count = int(f.get("people_count") or 0)
        passenger_name = f.get("passenger_name") or ""
        country_full = country_display(f.get("country_code"))
        group_code = f.get("group_code")

        # 记录该订单用于总人数（每行只计一次）
        orders_by_guide[guide].append(people_count)

        # 解析 note → 多个时段
        pickups = extract_pickups_structured(note, default_time="08:00")
        if not pickups:
            # 没有结构化信息就跳过（也可创建一个默认时段）
            continue

        for pk in pickups:
            items_by_guide[guide].append(
                {
                    "group_code": f["group_code"],
                    "lang_cn": bool(f.get("lang_cn")),  # 是否中文团（订单级别）
                    "time_txt": pk["time_txt"],
                    "meeting_text": pk[
                        "meeting_text"
                    ],  # 先是原始文本，稍后补全为完整地址
                    "people_count": int(f.get("people_count") or 0),
                    "passenger_name": f.get("passenger_name") or "",
                    "country_full": country_display(f.get("country_code")),
                    "boat_label": pk["boat_label"],
                    "changed": pk.get("changed", False),  # 是否改过地点（有 L）
                    "initial_short": pk.get(
                        "initial_short", ""
                    ),  # HOTEL 简称（括号在第二行拼）
                    "hotel_full": pk.get(
                        "hotel_full", ""
                    ),  # HOTEL 完整行（查库与建绑定用）
                }
            )

    # —— 在输出前，先对 L 做补全并写入绑定 ——
    # standardize_pickups_and_link(items_by_guide)

    # 输出每位导游

    for guide in [g for g in GUIDE_ORDER if g in items_by_guide]:
        items = items_by_guide[guide]

        # 行程由该导游名下所有 group_code 推断
        itinerary = decide_itinerary_for_guide(items)
        # 总人数：该导游名下所有订单人数相加（按行累计）
        total_people = sum(orders_by_guide.get(guide, []))

        # 时间排序
        def time_key(t):
            m = re.match(r"^(\d{1,2}):(\d{2})$", t or "")
            if not m:
                return (99, 99)
            return (int(m.group(1)), int(m.group(2)))

        items_sorted = sorted(
            items, key=lambda r: (time_key(r["time_txt"]), r["meeting_text"] or "")
        )

        # 是否存在中文团（任意订单带 CN 即为 True）
        any_cn = any(r.get("lang_cn") for r in items)

        lines = []
        lines.append(GREETING_LINE)
        lines.append(f"行程: {itinerary}")
        lines.append(f"{total_people}人")
        lines.append("")

        for r in items_sorted:
            # ① 第一行：时间 + 见面地点（不带括号）
            lines.append(f"{r['time_txt']} {r['meeting_text']}".rstrip())

            # ② 第二行：人数、姓名、国家、固定串；若 CN 再加包/不包船；若改地点再加（酒店简称）
            second = f"{r['people_count']}人, {r['passenger_name']}, {r['country_full']}, Whatsapp/微信/iMessage"
            if r.get("lang_cn") and r.get("boat_label"):
                second += f", {r['boat_label']}"
            if r.get("changed") and r.get("initial_short"):
                second += f"(住{r['initial_short']})"
            lines.append(second.rstrip(", "))
            lines.append("")

        # ③ 文件末尾：如该导游下任意订单带 CN，则加“中文团”
        if any_cn:
            lines.append("中文团")

        text = "\n".join(lines).rstrip() + "\n"

        # 文件名清洗，避免 schedule_?.txt 之类错误
        out_file = f"schedule_{safe_filename(guide)}.txt"
        out_path = os.path.join(OUTPUT_DIR, out_file)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        # 控制台输出预览
        print("=" * 60)
        print(f"导游：{guide}")
        print(text, end="")
        print("=" * 60)

    print(f"\n✅ 已输出至目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
