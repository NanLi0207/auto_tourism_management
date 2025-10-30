# -*- coding: utf-8 -*-
""" """

import os
import re
import time
import math
import sqlite3
from typing import Optional, Dict, Tuple, List, Union
from difflib import SequenceMatcher
from datetime import datetime

# Selenium imports (集中在顶部)
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

# ===================== 路径与文件名 =====================
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DB_FOLDER = os.path.join(PROJECT_ROOT, "databases")
os.makedirs(DB_FOLDER, exist_ok=True)

DB_FILES = {
    "hotels": "hotels.db",
    "pickup": "pickup_location.db",
}
LINK_TABLE_DB = "pickup"  # 绑定表存放在 pickup_location.db 内


def _db_path(db_kind: str) -> str:
    if db_kind not in DB_FILES:
        raise ValueError("db_kind must be 'hotels' or 'pickup'")
    return os.path.join(DB_FOLDER, DB_FILES[db_kind])


def _table_name(db_kind: str) -> str:
    return "hotels" if db_kind == "hotels" else "pickup_locations"


# ===================== 地图/搜索配置 =====================
CITY_CENTER_LAT, CITY_CENTER_LNG, CITY_CENTER_ZOOM = 52.3728, 4.8936, 13
CITY_FOR_QUERY_EN, APPEND_CITY_TO_QUERY = "Amsterdam", True
SELENIUM_SHORT_WAIT, SELENIUM_LONG_WAIT = 4, 12
SEARCH_THROTTLE_SECONDS = 0.6

# 精确匹配参数（只比 keywords）
JACCARD_MIN, EDIT_SIM_MIN, TOP2_MARGIN_MIN = 0.80, 0.92, 0.05

# ===================== 浏览器会话 =====================
driver = None
wait = None


def init_driver():
    """启动单例 Chrome（英文界面），可复用到进程结束/手动 quit。"""
    global driver, wait
    if driver:
        return
    opts = Options()
    opts.add_argument("--lang=en")
    opts.add_argument("--incognito")
    # 如需无头：opts.add_argument("--headless=new")
    opts.add_experimental_option(
        "prefs", {"profile.default_content_setting_values.geolocation": 2}
    )
    driver = webdriver.Chrome(options=opts)
    wait = WebDriverWait(driver, SELENIUM_SHORT_WAIT)


def quit_driver():
    """关闭全局浏览器实例。"""
    global driver
    if driver:
        try:
            driver.quit()
        except:
            pass
        driver = None


# ===================== 文本与相似度 =====================
STOPWORDS_BASE = {
    "amsterdam",
    "hotel",
    "hotels",
    "the",
    "by",
    "hostel",
    "inn",
    "apartment",
    "apartments",
    "residence",
    "collection",
    "city",
    "center",
    "centre",
    "netherlands",
}


def _stopwords():
    sw = set(STOPWORDS_BASE)
    if CITY_FOR_QUERY_EN:
        sw.add(CITY_FOR_QUERY_EN.lower())
    return sw


def normalize_keyword(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def token_set(s: str) -> List[str]:
    tokens = normalize_keyword(s).split()
    sw = _stopwords()
    seen, out = set(), []
    for t in tokens:
        if t in sw:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def edit_sim(a: str, b: str) -> float:
    a2 = " ".join(token_set(a))
    b2 = " ".join(token_set(b))
    return SequenceMatcher(None, a2, b2).ratio()


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ===================== 地址清理与坐标解析 =====================
def _clean_country_suffix(addr: str) -> str:
    if not addr:
        return ""
    addr = re.sub(r",?\s*(the\s+)?netherlands\s*$", "", addr, flags=re.I).strip()
    return addr.rstrip(",")


def _split_address(addr: str) -> Tuple[str, str]:
    """拆 street/city(最后一段最后一个词)，用于可视化/统计；失败返回空。"""
    addr = _clean_country_suffix(addr or "")
    if not addr:
        return "", ""
    parts = [p.strip() for p in addr.split(",") if p.strip()]
    if not parts:
        return "", ""
    street = parts[0]
    city = parts[-1].split()[-1] if parts else ""
    return street, city


def _extract_coords_from_url(url: str):
    """优先 !3d<lat>!4d<lng>；其次 !2d<lng>!3d<lat>；最后 @lat,lng"""
    if not url:
        return None, None
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)", url)
    if m:
        return float(m.group(2)), float(m.group(1))
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


# ===================== Selenium 抓取 =====================
def _accept_cookies():
    try:
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
        if href:
            driver.get(href)
            WebDriverWait(driver, SELENIUM_LONG_WAIT).until(
                lambda d: "/maps/place/" in d.current_url
            )
            return True
        return False
    except:
        return False


def _extract_place_name() -> str:
    try:
        el = WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            EC.presence_of_element_located(
                (By.XPATH, "//h1[contains(@class,'DUwDvf')]")
            )
        )
        return el.text.strip()
    except:
        return ""


def _extract_address_and_coords() -> Tuple[str, Optional[float], Optional[float]]:
    addr, lat, lng = "", None, None
    try:
        el = WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[starts-with(@aria-label,'Address:')]")
            )
        )
        label = el.get_attribute("aria-label") or ""
        addr = label.split(":", 1)[1].strip() if ":" in label else el.text.strip()
    except:
        pass
    # 清尾部国家
    addr = _clean_country_suffix(addr)
    # 坐标
    try:
        lat, lng = _extract_coords_from_url(driver.current_url)
    except:
        lat, lng = None, None
    return addr, lat, lng


# ===================== DB 建表/迁移（两库 + 绑定表） =====================
def init_db(db_kind: str = "hotels"):
    """初始化指定库；若 db_kind='pickup' 同时确保绑定表存在。"""
    dbp = _db_path(db_kind)
    table = _table_name(db_kind)

    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    c.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            keywords TEXT,
            street TEXT,
            city TEXT,
            address TEXT,
            latitude REAL,
            longitude REAL,
            place_id TEXT,
            created_at TEXT,
            updated_at TEXT,
            notes TEXT
        )
    """)
    # 迁移确保列
    c.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in c.fetchall()}
    for col, ddl in {
        "keywords": "TEXT",
        "street": "TEXT",
        "city": "TEXT",
        "address": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL",
        "place_id": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "notes": "TEXT",
    }.items():
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl};")

    conn.commit()
    conn.close()

    # 绑定表（放在 pickup_location.db 内）
    if db_kind == LINK_TABLE_DB:
        _ensure_link_table()

    print(f"✅ DB ready: {dbp} (table={table})")


def _ensure_link_table():
    """在 pickup_location.db 内确保 hotel_pickup_links 存在。"""
    dbp = _db_path("pickup")
    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS hotel_pickup_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hotel_id INTEGER,             -- 来自 hotels.db 的 id（不做外键约束）
            hotel_name TEXT,
            pickup_id INTEGER,            -- 来自 pickup_location.db 的 id
            pickup_name TEXT,
            priority INTEGER DEFAULT 1,   -- 数字越小优先级越高
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


# ===================== DB 工具与匹配 =====================
def _row_to_obj(row) -> Dict:
    keys = [
        "id",
        "name",
        "keywords",
        "street",
        "city",
        "address",
        "latitude",
        "longitude",
        "place_id",
        "created_at",
        "updated_at",
        "notes",
    ]
    d = dict(zip(keys, row))
    # 兼容命名
    d["lat"] = d.pop("latitude")
    d["lng"] = d.pop("longitude")
    return d


def _merge_keywords(old: str, new: str) -> str:
    old_list = [normalize_keyword(k) for k in (old or "").split(";") if k and k.strip()]
    new_norm = normalize_keyword(new or "")
    if new_norm and new_norm not in old_list:
        old_list.append(new_norm)
    return ";".join(sorted(set(old_list)))


def _append_keyword_to_id(db_kind: str, rec_id: int, new_kw: str):
    dbp = _db_path(db_kind)
    table = _table_name(db_kind)
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(f"SELECT keywords FROM {table} WHERE id=?", (rec_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    merged = _merge_keywords(row[0] or "", new_kw)
    if merged != (row[0] or ""):
        cur.execute(
            f"UPDATE {table} SET keywords=?, updated_at=? WHERE id=?",
            (merged, _now(), rec_id),
        )
        conn.commit()
        print(f"[DB:{db_kind}] ➕ keyword appended to id={rec_id}")
    conn.close()


def find_in_db_exact_keywords_only(query: str, db_kind: str) -> Optional[Dict]:
    q = normalize_keyword(query)
    dbp = _db_path(db_kind)
    table = _table_name(db_kind)
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    conn.close()
    for r in rows:
        obj = _row_to_obj(r)
        kw_list = [
            normalize_keyword(k)
            for k in (obj.get("keywords") or "").split(";")
            if k.strip()
        ]
        if q in kw_list:
            print(f"[DB:{db_kind}] Exact keyword hit: {obj['name']}")
            return obj
    return None


def _best_kw_metrics(query: str, kw_text: str):
    """在该记录的 keywords 中逐个对比，返回 (best_score, best_j, best_e)"""
    kws = [k for k in (kw_text or "").split(";") if k.strip()]
    if not kws:
        return 0.0, 0.0, 0.0
    best_s, best_j, best_e = 0.0, 0.0, 0.0
    q_tokens = token_set(query)
    for k in kws:
        j = jaccard(q_tokens, token_set(k))
        e = edit_sim(query, k)
        s = 0.6 * j + 0.4 * e
        if s > best_s:
            best_s, best_j, best_e = s, j, e
    return best_s, best_j, best_e


def find_best_in_db_precise(query: str, db_kind: str) -> Optional[Dict]:
    dbp = _db_path(db_kind)
    table = _table_name(db_kind)
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return None
    scored = []
    for r in rows:
        obj = _row_to_obj(r)
        s, j, e = _best_kw_metrics(query, obj.get("keywords", "") or "")
        scored.append((s, j, e, obj))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_j, top_e, top_obj = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = top_score - second_score
    if (
        (top_j >= JACCARD_MIN)
        and (top_e >= EDIT_SIM_MIN)
        and (margin >= TOP2_MARGIN_MIN)
    ):
        print(
            f"[DB:{db_kind}] Precise hit: {top_obj['name']} (score={top_score:.3f}, j={top_j:.3f}, e={top_e:.3f}, Δ={margin:.3f})"
        )
        return top_obj
    print(
        f"[DB:{db_kind}] No precise match (best={top_score:.3f}, j={top_j:.3f}, e={top_e:.3f}, Δ={margin:.3f})"
    )
    return None


# ===================== 保存/更新 =====================
def save_or_update_db(
    db_kind: str,
    official_name: str,
    new_keyword: str,
    address: str,
    lat: Optional[float],
    lng: Optional[float],
    place_id: str = "",
    notes: str = "",
) -> Dict:
    """按 name 合并（单条策略），追加 keywords，更新地址与坐标。"""
    dbp = _db_path(db_kind)
    table = _table_name(db_kind)
    addr = _clean_country_suffix(address or "")
    street, city = _split_address(addr)
    now = _now()
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(
        f"SELECT id, keywords, address, latitude, longitude, place_id FROM {table} WHERE name=?",
        (official_name,),
    )
    row = cur.fetchone()
    if row:
        rec_id, old_kw, old_addr, old_lat, old_lng, old_pid = row
        merged_kw = _merge_keywords(old_kw, new_keyword)
        cur.execute(
            f"""
            UPDATE {table}
               SET keywords=?, address=?, street=?, city=?,
                   latitude=?, longitude=?, place_id=?, notes=?, updated_at=?
             WHERE id=?
        """,
            (
                merged_kw,
                addr,
                street,
                city,
                lat or old_lat,
                lng or old_lng,
                place_id or (old_pid or ""),
                notes or "",
                now,
                rec_id,
            ),
        )
        conn.commit()
        conn.close()
        print(f"[DB:{db_kind}] Updated: {official_name}")
        return {
            "id": rec_id,
            "name": official_name,
            "keywords": merged_kw,
            "address": addr,
            "street": street,
            "city": city,
            "lat": lat or old_lat,
            "lng": lng or old_lng,
            "place_id": place_id or (old_pid or ""),
            "notes": notes,
        }
    else:
        cur.execute(
            f"""
            INSERT INTO {table}
            (name, keywords, street, city, address, latitude, longitude, place_id, created_at, updated_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                official_name,
                normalize_keyword(new_keyword),
                street,
                city,
                addr,
                lat or 0.0,
                lng or 0.0,
                place_id or "",
                now,
                now,
                notes or "",
            ),
        )
        rec_id = cur.lastrowid
        conn.commit()
        conn.close()
        print(f"[DB:{db_kind}] Saved new: {official_name}")
        return {
            "id": rec_id,
            "name": official_name,
            "keywords": normalize_keyword(new_keyword),
            "address": addr,
            "street": street,
            "city": city,
            "lat": lat or 0.0,
            "lng": lng or 0.0,
            "place_id": place_id or "",
            "notes": notes,
        }


# ===================== 主查询接口 =====================
def search_address(query: str, db_kind: str = "hotels") -> Optional[Dict]:
    """
    在指定库中查/补地址:
      - 先 local: 精确关键词 → 精准评分
      - 未命中: 打开 Google Maps 英文界面抓取，保存并返回
    返回 dict: {id,name,keywords,address,street,city,lat,lng,place_id,notes}
    """
    if not query:
        return None
    init_db(db_kind)  # 确保库就绪

    # 1) 本地
    local = find_in_db_exact_keywords_only(query, db_kind) or find_best_in_db_precise(
        query, db_kind
    )
    if local:
        if "id" in local and local["id"]:
            _append_keyword_to_id(db_kind, local["id"], query)
        return local

    # 2) Google Maps
    print(f"[Google:{db_kind}] Searching: {query} ...")
    if not driver:
        init_driver()
    driver.get(
        f"https://www.google.com/maps/@{CITY_CENTER_LAT},{CITY_CENTER_LNG},{CITY_CENTER_ZOOM}z?hl=en&gl=us"
    )
    _accept_cookies()
    q = (
        query
        if (not APPEND_CITY_TO_QUERY or "amsterdam" in query.lower())
        else f"{query} near {CITY_FOR_QUERY_EN}"
    )
    try:
        box = wait.until(lambda d: d.find_element(By.ID, "searchboxinput"))
        box.clear()
        box.send_keys(q)
        box.send_keys(Keys.RETURN)
        WebDriverWait(driver, SELENIUM_SHORT_WAIT).until(
            lambda d: "/maps/place/" in d.current_url
            or d.find_elements(By.XPATH, "//div[@role='feed']//div[@role='article']")
        )
        if "search" in driver.current_url and "/maps/place/" not in driver.current_url:
            if not _goto_first_place_from_list():
                return None
        official_name = _extract_place_name()
        address, lat, lng = _extract_address_and_coords()
        saved = save_or_update_db(
            db_kind, official_name or query, query, address, lat, lng
        )
        return saved
    except Exception as e:
        print(f"[Error:{db_kind}] Google Maps fetch failed: {e}")
        return None
    finally:
        time.sleep(SEARCH_THROTTLE_SECONDS)


# --- 距离计算：haversine（米） ---
def _haversine_m(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except:
        return float("inf")
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


# --- 搜集“搜索列表页”的多个候选，并返回 [ {name,address,lat,lng}, ... ] ---
def _collect_search_results_topk(query: str, topk: int = 6) -> List[Dict]:
    results = []
    # 进入列表页（若直接进详情也能处理）
    base_url = f"https://www.google.com/maps/@{CITY_CENTER_LAT},{CITY_CENTER_LNG},{CITY_CENTER_ZOOM}z?hl=en&gl=us"
    driver.get(base_url)
    _accept_cookies()

    q = (
        query
        if (not APPEND_CITY_TO_QUERY or "amsterdam" in query.lower())
        else f"{query} near {CITY_FOR_QUERY_EN}"
    )
    box = wait.until(lambda d: d.find_element(By.ID, "searchboxinput"))
    box.clear()
    box.send_keys(q)
    box.send_keys(Keys.RETURN)

    # 1) 若直接跳详情页，抓这一个候选
    WebDriverWait(driver, SELENIUM_LONG_WAIT).until(
        lambda d: "/maps/place/" in d.current_url
        or d.find_elements(
            By.XPATH, "//div[@role='feed']//a[contains(@href,'/maps/place/')]"
        )
    )
    if "/maps/place/" in driver.current_url:
        nm = _extract_place_name()
        addr, lat, lng = _extract_address_and_coords()
        if nm or addr:
            results.append(
                {"name": nm or query, "address": addr, "lat": lat, "lng": lng}
            )
        return results

    # 2) 列表页：取前 topk 个卡片的链接，逐个进入抓三元组
    anchors = driver.find_elements(
        By.XPATH, "//div[@role='feed']//a[contains(@href,'/maps/place/')]"
    )
    hrefs = []
    for a in anchors:
        href = a.get_attribute("href")
        if href and href not in hrefs:
            hrefs.append(href)
        if len(hrefs) >= topk:
            break

    for href in hrefs:
        driver.get(href)
        WebDriverWait(driver, SELENIUM_LONG_WAIT).until(
            lambda d: "/maps/place/" in d.current_url
        )
        nm = _extract_place_name()
        addr, lat, lng = _extract_address_and_coords()
        if nm or addr:
            results.append(
                {"name": nm or query, "address": addr, "lat": lat, "lng": lng}
            )
        time.sleep(0.15)  # 轻微节流
    return results


# --- 就近选择主函数：在 pickup/hotels 任一库中查询，按给定坐标选最近 ---
def search_address_near(
    query: str, near_lat: float, near_lng: float, db_kind: str = "pickup"
) -> Optional[Dict]:
    """
    以 near_lat/lng 为参考，从本地库或 Google Maps 返回“与 query 相符、且距离最近”的地点。
    - 优先：本地库中把“相似度达标”的候选全部取出，选与 near_* 最近的一个；
    - 其次：Google Maps 列表取前若干个候选，选最近，并把该条写入到 db_kind 指定的库；
    返回：和 search_address 一致的结构（至少含 name/address/lat/lng/id/...）
    """
    if query is None or query.strip() == "":
        return None
    init_db(db_kind)

    # 1) 本地候选：把所有记录算分，保留分数达标的一批，选距离最近
    dbp = _db_path(db_kind)
    table = _table_name(db_kind)
    conn = sqlite3.connect(dbp)
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()
    conn.close()

    pool = []
    for r in rows:
        obj = _row_to_obj(r)
        s, j, e = _best_kw_metrics(query, obj.get("keywords", "") or "")
        # 门槛放宽一点以便收集多候选
        if s >= 0.55 or (j >= 0.50 and e >= 0.75):
            dist = _haversine_m(near_lat, near_lng, obj.get("lat"), obj.get("lng"))
            pool.append((dist, s, obj))
    pool.sort(key=lambda x: (x[0], -x[1]))
    if pool and math.isfinite(pool[0][0]):
        best = pool[0][2]
        # 合并关键词
        if best.get("id"):
            _append_keyword_to_id(db_kind, best["id"], query)
        return best

    # 2) 走 Google：收集多候选 → 选最近 → 写库
    if not driver:
        init_driver()
    cands = _collect_search_results_topk(query, topk=6)
    if not cands:
        return None
    # 计算距离
    for c in cands:
        c["distance_m"] = _haversine_m(near_lat, near_lng, c.get("lat"), c.get("lng"))
    cands = [c for c in cands if math.isfinite(c["distance_m"])]
    if not cands:
        # 如果没拿到坐标，退回单候选保存
        chosen = (
            cands[0]
            if cands
            else {"name": query, "address": "", "lat": None, "lng": None}
        )
    else:
        cands.sort(key=lambda x: x["distance_m"])
        chosen = cands[0]

    saved = save_or_update_db(
        db_kind=db_kind,
        official_name=chosen.get("name") or query,
        new_keyword=query,
        address=chosen.get("address") or "",
        lat=chosen.get("lat"),
        lng=chosen.get("lng"),
        place_id="",
        notes=f"nearest to ({near_lat},{near_lng})",
    )
    return saved


# ===================== 绑定管理 (保存在 pickup_location.db) =====================
def link_hotel_to_pickup(
    hotel_query: str,
    pickup_query: str,
    priority: int = 1,
    notes: str = "",
    create_if_missing: bool = True,
) -> Optional[Dict]:
    """
    建立/更新：酒店 ↔ 见面点 的绑定。
    - hotel_query 在 hotels.db 内查/补
    - pickup_query 在 pickup_location.db 内查/补
    - 记录写入 pickup_location.db 的 hotel_pickup_links
    """
    init_db("hotels")
    init_db("pickup")  # 确保绑定表
    # 确保实体存在（必要时自动创建）
    h = find_in_db_exact_keywords_only(
        hotel_query, "hotels"
    ) or find_best_in_db_precise(hotel_query, "hotels")
    if not h and create_if_missing:
        h = search_address(hotel_query, db_kind="hotels")
    p = find_in_db_exact_keywords_only(
        pickup_query, "pickup"
    ) or find_best_in_db_precise(pickup_query, "pickup")
    if not p and create_if_missing:
        p = search_address(pickup_query, db_kind="pickup")
    if not (h and p):
        print("[Link] Missing hotel or pickup; cannot link.")
        return None

    dbp = _db_path("pickup")
    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    now = _now()
    # 若已存在则更新 priority/notes
    c.execute(
        """
        SELECT id FROM hotel_pickup_links WHERE hotel_id=? AND pickup_id=?
    """,
        (h["id"], p["id"]),
    )
    row = c.fetchone()
    if row:
        link_id = row[0]
        c.execute(
            """
            UPDATE hotel_pickup_links
               SET hotel_name=?, pickup_name=?, priority=?, notes=?, updated_at=?
             WHERE id=?
        """,
            (h["name"], p["name"], priority, notes or "", now, link_id),
        )
    else:
        c.execute(
            """
            INSERT INTO hotel_pickup_links
            (hotel_id, hotel_name, pickup_id, pickup_name, priority, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (h["id"], h["name"], p["id"], p["name"], priority, notes or "", now, now),
        )
        link_id = c.lastrowid
    conn.commit()
    conn.close()
    print(f"[Link] {h['name']}  ⇄  {p['name']}  (priority={priority})")
    return {
        "link_id": link_id,
        "hotel": h,
        "pickup": p,
        "priority": priority,
        "notes": notes or "",
    }


def get_pickups_for_hotel(
    hotel: Union[int, str], top_n: Optional[int] = None
) -> List[Dict]:
    """根据 hotel id 或关键字/名称，返回其绑定的见面点（按 priority 升序）。"""
    # 找到酒店
    if isinstance(hotel, int):
        dbp_h = _db_path("hotels")
        conn_h = sqlite3.connect(dbp_h)
        cur_h = conn_h.cursor()
        cur_h.execute("SELECT * FROM hotels WHERE id=?", (hotel,))
        row = cur_h.fetchone()
        conn_h.close()
        if not row:
            return []
        h = _row_to_obj(row)
    else:
        h = find_in_db_exact_keywords_only(hotel, "hotels") or find_best_in_db_precise(
            hotel, "hotels"
        )
        if not h:
            return []

    # 取绑定
    dbp = _db_path("pickup")
    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    c.execute(
        """
        SELECT pickup_id, pickup_name, priority, notes
          FROM hotel_pickup_links
         WHERE hotel_id=?
         ORDER BY priority ASC, id ASC
    """,
        (h["id"],),
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return []

    # 拉取 pickup 信息
    dbp_p = _db_path("pickup")
    connp = sqlite3.connect(dbp_p)
    curp = connp.cursor()
    results = []
    count = 0
    for pid, pname, prio, notes in rows:
        curp.execute("SELECT * FROM pickup_locations WHERE id=?", (pid,))
        rr = curp.fetchone()
        if rr:
            obj = _row_to_obj(rr)
            obj["priority"] = prio
            obj["notes_link"] = notes
            results.append(obj)
            count += 1
            if top_n and count >= top_n:
                break
    connp.close()
    return results


def get_hotels_for_pickup(pickup: Union[int, str]) -> List[Dict]:
    """反查：某个见面点关联的酒店列表（按 priority）。"""
    if isinstance(pickup, int):
        dbp_p = _db_path("pickup")
        connp = sqlite3.connect(dbp_p)
        curp = connp.cursor()
        curp.execute("SELECT * FROM pickup_locations WHERE id=?", (pickup,))
        row = curp.fetchone()
        connp.close()
        if not row:
            return []
        p = _row_to_obj(row)
    else:
        p = find_in_db_exact_keywords_only(pickup, "pickup") or find_best_in_db_precise(
            pickup, "pickup"
        )
        if not p:
            return []

    dbp = _db_path("pickup")
    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    c.execute(
        """
        SELECT hotel_id, hotel_name, priority, notes
          FROM hotel_pickup_links
         WHERE pickup_id=?
         ORDER BY priority ASC, id ASC
    """,
        (p["id"],),
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return []

    dbp_h = _db_path("hotels")
    connh = sqlite3.connect(dbp_h)
    curh = connh.cursor()
    results = []
    for hid, hname, prio, notes in rows:
        curh.execute("SELECT * FROM hotels WHERE id=?", (hid,))
        rr = curh.fetchone()
        if rr:
            obj = _row_to_obj(rr)
            obj["priority"] = prio
            obj["notes_link"] = notes
            results.append(obj)
    connh.close()
    return results


def unlink_hotel_pickup(hotel: Union[int, str], pickup: Union[int, str]) -> int:
    """删除某个酒店与见面点的绑定，返回删除条数。"""
    # 解析 hotel id
    if isinstance(hotel, int):
        hid = hotel
    else:
        h = find_in_db_exact_keywords_only(hotel, "hotels") or find_best_in_db_precise(
            hotel, "hotels"
        )
        if not h:
            return 0
        hid = h["id"]
    # 解析 pickup id
    if isinstance(pickup, int):
        pid = pickup
    else:
        p = find_in_db_exact_keywords_only(pickup, "pickup") or find_best_in_db_precise(
            pickup, "pickup"
        )
        if not p:
            return 0
        pid = p["id"]

    dbp = _db_path("pickup")
    conn = sqlite3.connect(dbp)
    c = conn.cursor()
    c.execute(
        "DELETE FROM hotel_pickup_links WHERE hotel_id=? AND pickup_id=?", (hid, pid)
    )
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"[Unlink] removed {deleted} link(s).")
    return deleted
