import httpx
from bs4 import BeautifulSoup
import json
import asyncio
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

COMPANIES_FILE = "companies.txt"
STATE_FILE = "state.json"
README_FILE = "README.md"


def load_companies() -> list[str]:
    """讀取 companies.txt，回傳 [代號, ...]"""
    companies = []
    for line in Path(COMPANIES_FILE).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            companies.append(line)
    return companies


def load_state() -> dict:
    """讀取上次的日期記錄"""
    if Path(STATE_FILE).exists():
        return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    return {}


def save_state(state: dict):
    Path(STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def generate_readme(companies: list[str], state: dict, updates: list[str], names: dict):
    """生成易讀的 README.md"""
    taipei_tz = timezone(timedelta(hours=8))
    now = datetime.now(taipei_tz).strftime("%Y/%m/%d %H:%M")

    # 先按更新日期（新到舊），再按法說會日期（舊到新）
    def sort_key(co_id):
        data = state.get(co_id, {})
        if isinstance(data, dict):
            updated = data.get("updated", "")
            content = data.get("content", "")
        else:
            updated = ""
            content = ""
        # 更新日期反轉（新的在前），法說會日期正常（舊的在前）
        return (-int(updated.replace("/", "")) if updated else 0, content)

    sorted_companies = sorted(companies, key=sort_key)

    lines = [
        "# 法說會追蹤",
        "",
        "built by [小嚴](https://linkedin.com/in/syen9904)",
        "",
        f"最後執行：{now} (UTC+8)",
        "",
    ]

    if updates:
        lines.append("## 🔔 本次更新")
        lines.append("")
        for u in updates:
            lines.append(f"- {u}")
        lines.append("")

    lines.append("## 追蹤清單")
    lines.append("")
    lines.append("- 每日盤前盤後自動更新（確切時間以伺服器排程為主）")
    lines.append("- 排序：更新日期（新→舊），再依法說會開始日期（舊→新）")
    lines.append("")
    lines.append("| 代號 | 公司 | 法說會日期 | 更新日期 |")
    lines.append("|------|------|-----------|---------|")

    for co_id in sorted_companies:
        name = names.get(co_id, co_id)
        data = state.get(co_id, {})
        if isinstance(data, dict):
            content = data.get("content", "-")
            updated = data.get("updated", "-")
        else:
            content = data if data else "-"
            updated = "-"
        lines.append(f"| {co_id} | {name} | {content} | {updated} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("要新增公司？編輯 `companies.txt`，一行一個代號")

    Path(README_FILE).write_text("\n".join(lines), encoding="utf-8")


async def fetch_content(client: httpx.AsyncClient, co_id: str) -> tuple[str | None, str | None]:
    """從 HTML 抓公司名稱和法說會日期，回傳 (name, date)"""
    try:
        res = await client.post(
            "https://mopsov.twse.com.tw/mops/web/ajax_t100sb07_1",
            data={
                "encodeURIComponent": "1",
                "step": "1",
                "firstin": "true",
                "off": "1",
                "TYPEK": "all",
                "co_id": co_id,
            },
        )
        # 被 rate limit 就等 30 秒再試
        if "Overrun" in res.text:
            print(f"  {co_id}: RATE LIMITED, sleeping 30s...")
            await asyncio.sleep(30)
            return await fetch_content(client, co_id)

        soup = BeautifulSoup(res.text, "html.parser")

        # 抓公司名稱（在 "公司名稱：" 後面）
        name = None
        text = soup.get_text()
        if "公司名稱：" in text:
            name = text.split("公司名稱：")[1].split()[0].strip()

        # 抓法說會日期
        date = None
        for tr in soup.select("tr"):
            if "召開法人說明會日期" in tr.get_text():
                td = tr.select("td")[-1] if tr.select("td") else None
                if td:
                    blues = [f.get_text().strip() for f in td.select("font[color=blue]")]
                    dates = [b for b in blues if "/" in b and len(b) >= 8]
                    if len(dates) >= 2:
                        start, end = dates[0], dates[1]
                        date = start if start == end else f"{start} ~ {end[4:]}"
                    elif dates:
                        date = dates[0]
                break

        return name, date
    except Exception as e:
        print(f"Error fetching {co_id}: {e}")
        return None, None


async def main():
    companies = load_companies()
    state = load_state()
    print(f"追蹤 {len(companies)} 間公司")

    updates = []
    names = {}  # co_id -> name (stateless)

    today = datetime.now().strftime("%Y/%m/%d")

    async with httpx.AsyncClient(timeout=30, verify=False) as client:
        for co_id in companies:
            old = state.get(co_id, {})
            old_content = old.get("content", "") if isinstance(old, dict) else old

            name, new_content = await fetch_content(client, co_id)
            names[co_id] = name or co_id

            if new_content and new_content != old_content:
                updates.append(f"**{co_id} {name or ''}**")
                state[co_id] = {"content": new_content, "updated": today}
                print(f"  {co_id} {name}: UPDATED")
            else:
                print(f"  {co_id} {name}: no change")

            await asyncio.sleep(0.1)

    save_state(state)
    generate_readme(companies, state, updates, names)

    if updates:
        print(f"\n更新 {len(updates)} 筆")
    else:
        print("\n無更新")


if __name__ == "__main__":
    asyncio.run(main())
