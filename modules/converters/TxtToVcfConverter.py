# -*- coding: utf-8 -*-
# ./modules/converter/txt_to_vcf.py
"""
将特定格式文本转为 iPhone vCard（.vcf）

此模块封装为 TxtToVcfConverter 类，便于调用和集成。
原本的函数逻辑已保留，对“阿姆斯特丹中央车站”进行特判，输出 “CS” 作为地名标记。
"""

import re
import unicodedata
from typing import Optional, Tuple, List


class TxtToVcfConverter:
    """
    将特定格式 TXT 文本中的联系人信息解析并转换为 iPhone 兼容的 vCard 3.0 文件。

    ------------------------------
    【输入 TXT 行格式】
    ------------------------------
    <日期> <国家> <人数> <姓名(可含空格)> <团名> [<语言>] <平台> Notes: Phone: <电话> Hotel: <酒店> [Boat: <Yes/No>] [Email: <邮箱>]

    示例：
        a251025 CN 1 Yuchen Gong GZ CN CT Notes: Phone: +8618728436260 Hotel: 阿姆斯特丹斯洛特迪克智选假日酒店 Boat: No Email: 1057683850@qq.com

    ------------------------------
    【输出】
    ------------------------------
    - 文件名：aYYMMDD.vcf（或日期区间 aYYMMDD_aYYMMDD.vcf）
    - 每行联系人 → 一张 vCard 名片
    - NOTE 字段格式：
        H: <地名（Hotel 逗号前）或 CS（中央车站）>
        B: <Yes/No/Unknown>

        T:
        L:
        N:
        O:
    """

    COLON = r"[:：]"
    LINE_PATTERN = re.compile(
        rf"^(?P<last>.*?)\s+Notes{COLON}\s*Phone{COLON}\s*(?P<phone>\S+)\s+Hotel{COLON}\s*(?P<hotel>.*?)(?:\s+Boat{COLON}\s*(?P<boat>\S+))?(?:\s+Email{COLON}\s*(?P<email>\S+))?\s*$"
    )

    def __init__(
        self,
        input_file: str,
        output_file: str,
        enable_special_cases: bool = True,
        suppress_address_for_ams_central: bool = True,
    ):
        self.input_file = input_file
        self.output_file = output_file
        self.enable_special_cases = enable_special_cases
        self.suppress_address_for_ams_central = suppress_address_for_ams_central

    # ===================== 工具方法 =====================
    @staticmethod
    def vcard_escape(value: str) -> str:
        value = value.replace("\\", "\\\\")
        value = value.replace("\r", "")
        value = value.replace("\n", "\\n")
        value = value.replace(",", "\\,")
        value = value.replace(";", "\\;")
        return value

    @staticmethod
    def fold_vcard_line(line: str, limit_bytes: int = 75) -> str:
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

    # ===================== 解析 TXT =====================
    def parse_line(
        self, line: str
    ) -> Tuple[str, str, str, Optional[str], Optional[str]]:
        line = line.strip()
        if not line:
            raise ValueError("空行")
        m = self.LINE_PATTERN.match(line)
        if not m:
            raise ValueError(f"无法解析该行：{line}")
        last = m.group("last") or ""
        phone = m.group("phone") or ""
        hotel = m.group("hotel") or ""
        boat = m.group("boat") or ""
        email = m.group("email") or ""
        return last, phone, hotel, boat, email

    # ===================== 文本规范化 =====================
    @staticmethod
    def _normalize_text(s: str) -> str:
        s = unicodedata.normalize("NFKC", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.lower().strip()
        s = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def extract_place_from_pickup(hotel: str) -> str:
        return "" if not hotel else hotel

    # ===================== 特判：阿姆斯特丹中央车站 =====================
    def is_ams_central_alias(self, place: str) -> bool:
        raw = place or ""
        norm = self._normalize_text(raw)
        aliases = {
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
        return norm in aliases

    def should_suppress_address(self, place: str) -> bool:
        if not self.enable_special_cases or not self.suppress_address_for_ams_central:
            return False
        return self.is_ams_central_alias(place)

    # ===================== vCard 生成 =====================
    def make_vcard_contact(
        self,
        last: str,
        phone: str,
        hotel: str,
        boat: Optional[str],
        email: Optional[str],
        suppress_address: bool = False,
    ) -> str:
        place = self.extract_place_from_pickup(hotel)
        line1 = "CS" if suppress_address else (place or (hotel or "").strip())

        boat_flag = "Unknown"
        if boat:
            b = boat.strip().lower()
            if b in ["yes", "y", "true", "1", "包船", "含船"]:
                boat_flag = "Yes"
            elif b in ["no", "n", "false", "0", "不包船", "不含船"]:
                boat_flag = "No"

        note_text = f"H: {line1.strip()}\nB: {boat_flag}\n\nT: \nL: \nN: \nO: "
        last_esc = self.vcard_escape(last.strip())
        fn_esc = last_esc
        note_esc = self.vcard_escape(note_text)

        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"N:{last_esc};;;;",
            f"FN:{fn_esc}",
            f"TEL;TYPE=CELL:{phone or ''}",
            f"EMAIL;TYPE=INTERNET:{email or ''}",
            f"NOTE:{note_esc}",
            "END:VCARD",
        ]
        folded = [self.fold_vcard_line(l) for l in lines]
        return "\r\n".join(folded)

    # ===================== 主转换逻辑 =====================
    def convert(self) -> List[str]:
        errors = []
        vcards = []
        with open(self.input_file, "r", encoding="utf-8") as f:
            for ln, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    last, phone, hotel, boat, email = self.parse_line(raw)
                    suppress_addr = self.should_suppress_address(
                        self.extract_place_from_pickup(hotel)
                    )
                    vcards.append(
                        self.make_vcard_contact(
                            last=last,
                            phone=phone,
                            hotel=hotel,
                            boat=boat,
                            email=email,
                            suppress_address=suppress_addr,
                        )
                    )
                except Exception as e:
                    errors.append(f"Line {ln}: {e}")

        content = "\r\n".join(vcards) + ("\r\n" if vcards else "")
        with open(self.output_file, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return errors
