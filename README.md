# Мини-приложение GdeRabota для MAX

Человек вводит город, профессию и зарплату и получает подходящие вакансии из фида GdeRabota.
Если точных совпадений нет, показываются похожие вакансии.

- `site/index.html` — мини-приложение
- `scripts/build.py` — скачивает фид и собирает `site/vacancies.json`
- `.github/workflows/update.yml` — обновляет вакансии каждый час и публикует сайт на GitHub Pages

Сменить фид: в `scripts/build.py` поменяйте `FEED_URL`.
