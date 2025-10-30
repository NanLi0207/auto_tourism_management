import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from .browser import init_driver
from .config import (
    CITY_CENTER_LAT,
    CITY_CENTER_LNG,
    CITY_CENTER_ZOOM,
    APPEND_CITY_TO_QUERY,
    CITY_FOR_QUERY_EN,
    SEARCH_THROTTLE_SECONDS,
    SELENIUM_SHORT_WAIT,
)


def accept_cookies(driver):
    """自动接受 Google Maps cookies"""
    try:
        btn = WebDriverWait(driver, 4).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@aria-label, 'Accept')]")
            )
        )
        btn.click()
        time.sleep(0.3)
    except:
        pass


def clean_country_suffix(addr: str) -> str:
    """去掉地址中的国家后缀"""
    if not addr:
        return ""
    addr = re.sub(r",?\s*(the\s+)?netherlands\s*$", "", addr, flags=re.I).strip()
    return addr.rstrip(",")


def extract_coords_from_url(url: str):
    """从 URL 中提取经纬度"""
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


def extract_place_name(driver):
    """提取详情页的标题名称"""
    try:
        el = WebDriverWait(driver, 4).until(
            EC.presence_of_element_located(
                (By.XPATH, "//h1[contains(@class,'DUwDvf')]")
            )
        )
        return el.text.strip()
    except:
        return ""


def extract_address_and_coords(driver):
    """提取详情页地址和坐标"""
    addr, lat, lng = "", None, None
    try:
        el = WebDriverWait(driver, 4).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[starts-with(@aria-label,'Address:')]")
            )
        )
        label = el.get_attribute("aria-label") or ""
        addr = label.split(":", 1)[1].strip() if ":" in label else el.text.strip()
    except:
        pass
    addr = clean_country_suffix(addr)
    lat, lng = extract_coords_from_url(driver.current_url)
    return addr, lat, lng


def click_first_result_if_list_page(driver):
    """
    检测是否是搜索列表页，如果是，则点击第一个非广告结果
    ------------------------------------------------------
    列表页的 URL 一般形如：
        https://www.google.com/maps/search/Amsterdam+Central+Station/...
    非广告结果的元素 XPath 一般为：
        //a[contains(@href, '/maps/place/') and not(ancestor::div[contains(@aria-label,'Ads')])]
    """
    if "/maps/search/" not in driver.current_url:
        return

    try:
        # 找到第一个非广告的结果
        first_result = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable(
                (By.XPATH, "(//a[contains(@href, '/maps/place/')])[1]")
            )
        )
        driver.execute_script("arguments[0].click();", first_result)
        # 等待跳转到详情页
        WebDriverWait(driver, 8).until(lambda d: "/maps/place/" in d.current_url)
    except Exception as e:
        print(f"[警告] 无法点击第一个搜索结果: {e}")


def search_place(query: str):
    """
    主函数：通过 Google Maps 搜索地点
    ------------------------------------------------------
    Args:
        query (str): 搜索关键词

    Returns:
        dict: {
            "official_name": 名称,
            "address": 地址,
            "lat": 纬度,
            "lng": 经度
        }
    """
    driver = init_driver()
    wait = WebDriverWait(driver, SELENIUM_SHORT_WAIT)

    # 打开地图主页
    driver.get(
        f"https://www.google.com/maps/@{CITY_CENTER_LAT},{CITY_CENTER_LNG},{CITY_CENTER_ZOOM}z?hl=en&gl=us"
    )
    accept_cookies(driver)

    # 构建搜索字符串
    q = (
        query
        if (not APPEND_CITY_TO_QUERY or "amsterdam" in query.lower())
        else f"{query} near {CITY_FOR_QUERY_EN}"
    )

    # 输入搜索关键词
    box = wait.until(lambda d: d.find_element(By.ID, "searchboxinput"))
    box.clear()
    box.send_keys(q)
    box.send_keys(Keys.RETURN)

    # 等待页面响应
    WebDriverWait(driver, 8).until(
        lambda d: "/maps/place/" in d.current_url or "/maps/search/" in d.current_url
    )

    # ✅ 如果是列表页，点击第一个搜索结果
    click_first_result_if_list_page(driver)

    # 抓取详情信息
    official_name = extract_place_name(driver)
    address, lat, lng = extract_address_and_coords(driver)

    time.sleep(SEARCH_THROTTLE_SECONDS)

    return {
        "official_name": official_name or query,
        "address": address,
        "lat": lat,
        "lng": lng,
    }
