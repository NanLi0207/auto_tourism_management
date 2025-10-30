#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 vCard (.vcf) 文件转换为 Excel (.xlsx)，并根据规则清理姓名。
规则：
1. 如果姓名以英文问号 ? 或中文问号 ？ 结尾，去掉末尾问号并保留。
2. 如果姓名以 "XX" 或 "KZ" 结尾（不区分大小写），丢弃该联系人。
3. 保留备注（NOTE），多行合并，不同 NOTE 之间空一行。
"""

import vobject
import pandas as pd

# 固定输入输出文件路径
filename = r"a251028"
vcf_file = f"{filename}.vcf"  # 输入 vCard 文件
out_file = f"{filename}.xlsx"  # 输出 Excel 文件


def clean_trailing_question_mark(name: str) -> tuple[str, bool]:
    """
    如果姓名以英文问号 ? 或中文问号 ？ 结尾，去掉末尾的一个问号并返回 (新姓名, True)；
    否则返回原姓名和 False。
    """
    if not name:
        return name, False
    n = name.rstrip()  # 去除末尾空白后检查
    if n.endswith("?") or n.endswith("？"):
        return n[:-1].rstrip(), True
    return name, False


def process_vcf():
    contacts = []
    total, kept, dropped_suffix = 0, 0, 0
    kept_due_to_qmark = 0

    # 读取并处理 vCard
    with open(vcf_file, "r", encoding="utf-8") as f:
        for vcard in vobject.readComponents(f):
            total += 1

            # 1) 取 full name（FN）；若没有 FN，这条就跳过
            fn_prop = getattr(vcard, "fn", None)
            if not fn_prop or not getattr(fn_prop, "value", "").strip():
                continue
            full_name_raw = fn_prop.value.strip()

            # 2) 规则处理：问号优先
            name_clean, had_qmark = clean_trailing_question_mark(full_name_raw)
            if had_qmark:
                kept_due_to_qmark += 1
            else:
                # 没有问号才检查 xx/KZ（不区分大小写）
                name_upper = name_clean.strip().upper()
                if name_upper.endswith("XX") or name_upper.endswith("KZ"):
                    dropped_suffix += 1
                    continue  # 丢弃

            # 3) 备注（全部 NOTE，保留原有多行；不同 NOTE 之间空一行）
            note_chunks = []
            for note_prop in vcard.contents.get("note", []):
                val = str(getattr(note_prop, "value", ""))
                val = val.replace("\r\n", "\n").replace("\r", "\n")
                note_chunks.append(val)
            note_text = "\n\n".join([c for c in note_chunks if c.strip() != ""])

            contacts.append({"full_name": name_clean, "note": note_text})
            kept += 1

    # 导出到 Excel（只保留姓名和备注）
    df = pd.DataFrame(contacts, columns=["full_name", "note"])
    df.to_excel(out_file, index=False)

    print(f"✅ 已导出到 {out_file}")
    print(f"总计读取: {total} 条")
    print(f"保留: {kept} 条（其中因尾部问号而保留: {kept_due_to_qmark} 条）")
    print(f"因以 xx/KZ 结尾被丢弃: {dropped_suffix} 条")


if __name__ == "__main__":
    process_vcf()
