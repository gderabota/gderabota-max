#!/usr/bin/env python3
"""Скачивает XML-фид GdeRabota и собирает компактный site/vacancies.json для мини-приложения."""
import html, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET

FEED_URL = os.environ.get("FEED_URL", "https://gderabota.ru/storage/feed_our_and_promoted.xml")
SITE = os.path.join(os.path.dirname(__file__), "..", "site")
OUT = os.path.join(SITE, "vacancies.json")
DESC_DIR = os.path.join(SITE, "desc")
CHUNK = 300  # описаний в одном файле desc/N.json


def text(el, path):
    v = el.findtext(path)
    return (v or "").strip()


def strip_html(s, limit=300):
    s = re.sub(r"<br\s*/?>|</p>|</li>", " ", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "…"


def parse_salary(s):
    s = s.replace(" ", " ").lower()
    nums = [int(n) for n in re.findall(r"\d+", s.replace(" ", ""))] if "-" not in s else \
        [int(re.sub(r"\D", "", p)) for p in s.split("-") if re.sub(r"\D", "", p)]
    if not nums:
        return None, None
    if s.startswith("до"):
        return None, nums[0]
    if s.startswith("от") or len(nums) == 1:
        return nums[0], None
    return nums[0], nums[1]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:
        data = open(src, "rb").read()
    else:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": "gderabota-max-miniapp/1.0"})
        data = urllib.request.urlopen(req, timeout=120).read()
    root = ET.fromstring(data)
    items = []
    for v in root.iter("vacancy"):
        url = text(v, "url")
        title = text(v, "job-name")
        if not url or not title:
            continue
        sal_raw = text(v, "salary")
        sfrom, sto = parse_salary(sal_raw)
        cities = []
        for a in v.iter("address"):
            loc = text(a, "location")
            if loc:
                city, _, region = loc.partition(",")
                cities.append([city.strip(), region.strip()])
        tags = [text(c, "specialization") for c in v.iter("category")] + \
               [text(c, "industry") for c in v.iter("category")]
        items.append({
            "url": url,
            "t": title,
            "sf": sfrom,
            "st": sto,
            "s": sal_raw if sfrom is None and sto is None else "",
            "c": cities,
            "co": text(v, "company/name"),
            "e": text(v, "employment"),
            "x": text(v, "experience"),
            "tg": [t for t in dict.fromkeys(tags) if t],
            "d": strip_html(v.findtext("description")),
            "u": text(v, "update-date")[:10],
        })
    items.sort(key=lambda i: i["u"], reverse=True)
    # описания выносим в отдельные небольшие файлы, чтобы основной список грузился быстро
    descs = [i.pop("d") for i in items]
    os.makedirs(DESC_DIR, exist_ok=True)
    for old in os.listdir(DESC_DIR):
        os.remove(os.path.join(DESC_DIR, old))
    for n in range(0, len(descs), CHUNK):
        with open(os.path.join(DESC_DIR, f"{n // CHUNK}.json"), "w", encoding="utf-8") as f:
            json.dump(descs[n:n + CHUNK], f, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": root.get("creation-time", ""), "chunk": CHUNK, "items": items}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"OK: {len(items)} вакансий -> {OUT}")


if __name__ == "__main__":
    main()
