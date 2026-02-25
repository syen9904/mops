"""從 TWSE/TPEx API 抓取所有上市＋上櫃公司名稱，寫入 names.json"""

import httpx
import json
from pathlib import Path

NAMES_FILE = "names.json"

NAMES_APIS = [
    ("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
     "公司代號", "公司簡稱", "英文簡稱"),
    ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
     "SecuritiesCompanyCode", "CompanyAbbreviation", "Symbol"),
]

names = {}
for label, url, key_code, key_zh, key_en in NAMES_APIS:
    res = httpx.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()
    count = 0
    for item in data:
        code = item.get(key_code, "").strip()
        if code:
            names[code] = {
                "zh": item.get(key_zh, "").strip(),
                "en": item.get(key_en, "").strip(),
            }
            count += 1
    print(f"{label}：{count} 間")

Path(NAMES_FILE).write_text(
    json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"\n共 {len(names)} 間，已寫入 {NAMES_FILE}")
