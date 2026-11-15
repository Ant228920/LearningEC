# Currency Converter API

REST-сервіс на FastAPI, який конвертує суму з однієї валюти в іншу за крос-курсом. Курси щодоби завантажуються з API Національного банку України в PostgreSQL; якщо валюти немає в базі, сервіс питає зовнішнього провайдера, а при його недоступності повертає запасний курс із позначкою `degraded_fallback`. Додатково є модуль приватності (GDPR): експорт даних, анонімізація, керування згодами.

**Для кого:** розробники та QA, які підтримують сервіс; DevOps, що його розгортає; бізнес-замовник, якому потрібна швидка конвертація без залежності від зовнішнього сервісу в кожному запиті.

## Швидкий старт (5 хвилин)

Потрібні: Docker з Docker Compose, Git.

```bash
git clone https://github.com/Ant228920/LearningEC.git
cd LearningEC
git checkout init/currency-app
cd my_fastapi_app
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
# у .env замініть your_secret_password_here на власний пароль (в обох місцях)
docker compose up --build
```

Сервіс стартує на `http://localhost:8000`, інтерактивна документація — `http://localhost:8000/docs`.

Перевірка:

```bash
curl "http://localhost:8000/api/v1/tasks/api/convert?amount=100&from_currency=USD&to_currency=EUR"
```

Відповідь містить `converted_amount`, `cross_rate` і `system_status` (`healthy` або `degraded_fallback`).

Ручний запуск синхронізації курсів (за розкладом вона працює щодня о 03:00 в контейнері `currency_cron`):

```bash
docker compose exec currency_cron python -m scripts.sync_nbu
```

## Тести

```bash
cd my_fastapi_app
pip install -r requirements.txt
pytest
```

Тести створюють застосунок із підключенням до PostgreSQL, тому база має бути доступною. Для запуску з хоста запустіть `docker compose up -d currency_db` і в `.env` вкажіть `DB_HOST=localhost`, `DB_PORT=5424`.

## Основні ендпоінти

| Метод і шлях | Призначення |
|---|---|
| `GET /api/v1/tasks/api/convert` | Конвертація: `amount`, `from_currency`, `to_currency` |
| `GET /api/v1/users/{id}/personal-data` | Експорт персональних даних (заголовок `X-User-Id`) |
| `POST /api/v1/users/{id}/anonymize` | Анонімізація користувача |
| `POST /api/v1/users/{id}/consents/grant` · `/revoke` | Керування згодами |
| `POST /api/v1/users/{id}/actions/send-marketing` | Маркетингова дія з перевіркою згоди |

Повні контракти: [docs/sdd.md](docs/sdd.md#5-api-контракти).

## Документація

| Документ | Про що |
|---|---|
| [docs/sdd.md](docs/sdd.md) | Архітектура: контейнери, компоненти, модель даних, API |
| [docs/isd.md](docs/isd.md) | Інфраструктура: середовища, CI/CD, моніторинг, бекапи, RTO/RPO |
| [docs/architecture/adr/](docs/architecture/adr/) | Журнал архітектурних рішень |
| [docs/audience-matrix.md](docs/audience-matrix.md) | Хто і де шукає відповіді |

## Шлях онбордингу нового розробника

1. Прочитайте цей README і запустіть проєкт за розділом «Швидкий старт».
2. Відкрийте `http://localhost:8000/docs` і виконайте запит конвертації.
3. Прочитайте [SDD](docs/sdd.md): діаграма контейнерів і розділ про компоненти.
4. Запустіть `pytest` і перегляньте `my_fastapi_app/tests/` як специфікацію поведінки.
5. Перед першою зміною прочитайте [ISD](docs/isd.md) і розділ 6 SDD («Відомі розбіжності й технічний борг»).

## Відомі обмеження

Перелік розбіжностей між кодом і наміром (назва шляху `/tasks`, заголовок Swagger, ідентифікація користувача за `X-User-Id` без автентифікації тощо) ведеться в [SDD, розділ 6](docs/sdd.md#6-відомі-розбіжності-й-технічний-борг).
