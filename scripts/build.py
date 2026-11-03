#!/usr/bin/env python3
"""Скачивает XML-фид GdeRabota и собирает компактный site/vacancies.json для мини-приложения."""
import collections, html, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET

# Фиды GdeRabota. Вакансии из всех фидов объединяются, дубли по ссылке убираются.
FEED_URLS = os.environ.get("FEED_URLS", " ".join([
    "https://gderabota.ru/storage/feed_our_and_promoted.xml",
    "https://gderabota.ru/storage/feed_our_exclude_trudvsem.xml",
])).split()
SITE = os.path.join(os.path.dirname(__file__), "..", "site")
OUT = os.path.join(SITE, "vacancies.json")
DESC_DIR = os.path.join(SITE, "desc")
CHUNK = 300  # описаний в одном файле desc/N.json

# Защита от «пустого» фида: адрес уже опубликованного vacancies.json и допустимое падение.
PREV_URL = os.environ.get("PREV_URL", "")            # например https://gderabota.github.io/gderabota-max/vacancies.json
MIN_RATIO = float(os.environ.get("MIN_RATIO", "0.5"))  # меньше половины от прошлого раза — не публикуем
FORCE = os.environ.get("FORCE", "") == "1"            # ручной запуск с force: опубликовать всё равно


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


STOP_HEADS = ("работа", "вахт", "контракт", "срочно", "требу", "вакансия", "подработ")


def title_head(title):
    """«Грузчик на склад / вахта» -> «грузчик»"""
    head = re.split(r"[/(,:;–—!|]| - | в | на | для | с ", title.lower().replace("ё", "е"))[0].strip(" .-")
    if not (3 <= len(head) <= 40) or re.search(r"\d", head) or len(head.split()) > 4:
        return None
    if any(w in head for w in STOP_HEADS):
        return None
    return head


def build_profs(root):
    """Список подсказок для поля «Профессия»: специализации + частые названия вакансий."""
    specs, heads = collections.Counter(), collections.Counter()
    for v in root.iter("vacancy"):
        specs.update({text(c, "specialization") for c in v.iter("category")} - {"", "Другое"})
        h = title_head(text(v, "job-name"))
        if h:
            heads[h] += 1
    out = {}
    for name, n in specs.items():
        out[name.lower().replace("ё", "е")] = [name, n]
    for h, n in heads.items():
        if n >= 3 and h not in out:
            out[h] = [h[0].upper() + h[1:], n]
    return sorted(out.values(), key=lambda x: -x[1])[:600]


def load_feed(src):
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "gderabota-max-miniapp/1.0"})
        data = urllib.request.urlopen(req, timeout=300).read()
    else:
        data = open(src, "rb").read()
    return ET.fromstring(data)


def previous_count():
    """Сколько вакансий опубликовано сейчас (None — неизвестно, например первая публикация)."""
    if not PREV_URL:
        return None
    try:
        req = urllib.request.Request(PREV_URL, headers={"User-Agent": "gderabota-max-miniapp/1.0"})
        return len(json.load(urllib.request.urlopen(req, timeout=60))["items"])
    except Exception as e:
        print(f"Не удалось узнать прошлое число вакансий ({e}), проверку пропускаю")
        return None


def check_drop(new_count):
    prev = previous_count()
    if prev is None:
        return
    print(f"Было опубликовано: {prev}, сейчас: {new_count}")
    if new_count < prev * MIN_RATIO and not FORCE:
        sys.exit(f"СТОП: вакансий стало {new_count} вместо {prev} (меньше {int(MIN_RATIO * 100)}%). "
                 "Похоже, фид пришёл неполным. Публикация отменена, на сайте остаются прежние вакансии. "
                 "Если сокращение настоящее, запустите сборку вручную с параметром force.")


def main():
    # можно передать локальные файлы: python3 scripts/build.py feed1.xml feed2.xml
    sources = sys.argv[1:] or FEED_URLS
    roots = []
    for src in sources:
        r = load_feed(src)
        n = sum(1 for _ in r.iter("vacancy"))
        print(f"{src}: {n} вакансий")
        if n == 0 and not FORCE:
            sys.exit(f"СТОП: фид {src} пустой. Публикация отменена, на сайте остаются прежние вакансии.")
        roots.append(r)
    # объединяем фиды, дубли по ссылке убираем
    root = ET.Element("source", {"creation-time": max(r.get("creation-time", "") for r in roots)})
    seen = set()
    for r in roots:
        for v in r.iter("vacancy"):
            u = text(v, "url")
            if u and u not in seen:
                seen.add(u)
                root.append(v)
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
    check_drop(len(items))
    # описания выносим в отдельные небольшие файлы, чтобы основной список грузился быстро
    descs = [i.pop("d") for i in items]
    os.makedirs(DESC_DIR, exist_ok=True)
    for old in os.listdir(DESC_DIR):
        os.remove(os.path.join(DESC_DIR, old))
    for n in range(0, len(descs), CHUNK):
        with open(os.path.join(DESC_DIR, f"{n // CHUNK}.json"), "w", encoding="utf-8") as f:
            json.dump(descs[n:n + CHUNK], f, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": root.get("creation-time", ""), "chunk": CHUNK, "profs": build_profs(root), "items": items}, f,
                  ensure_ascii=False, separators=(",", ":"))
    print(f"OK: {len(items)} вакансий -> {OUT}")


if __name__ == "__main__":
    main()
