# ./atm_2_save_contacts.py
from modules.converters.TxtToVcfConverter import TxtToVcfConverter
import logging

# ✅ 初始化日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ===================== 可配置项 =====================
start_date = "2025-10-31"
end_date = "2025-10-31"
FULL_ADDRESS = True
if start_date == end_date:
    file = f"a{start_date.replace('-', '')[2:]}"
else:
    file = f"a{start_date.replace('-', '')[2:]}_a{end_date.replace('-', '')[2:]}"
INPUT_FILE = f"{file}.txt"
OUTPUT_VCF = f"{file}.vcf"


converter = TxtToVcfConverter(INPUT_FILE, OUTPUT_VCF, FULL_ADDRESS)
converter.convert()
