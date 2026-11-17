# Keitaro Campaign Editor

Веб-редактор кампаний для трекера Keitaro. Бэкенд на FastAPI + SQLAlchemy работает посредником
к Keitaro Admin API, фронтенд на Vue 3 + Vite даёт интерфейс для создания и редактирования кампаний.

```
backend/            FastAPI, SQLAlchemy (SQLite), httpx - клиент Keitaro Admin API
frontend/           Vue 3, vue-router, Vite; в Docker раздаётся через nginx
docker-compose.yml  запуск всего стека одной командой
```

## Что умеет

- **Создание кампании** одной формой: название, оффер (или несколько), страны (гео).
  Приложение создаёт кампанию в Keitaro, группу и источник подставляет из конфига.
- **Два потока на кампанию**: выбранные страны уходят на `google.com`, все остальные посетители
  уходят на офферы кампании.
- **Офферы**: добавление, удаление, поиск по названию и ID, веса. Веса распределяются поровну
  (сумма 100%), вес можно закрепить вручную, закреплённый вес не меняется при добавлении
  и удалении других офферов.
- **Редактирование** параметров кампании: название, alias, статус, группа, источник, тип и
  стоимость, заметки.
- Список кампаний с включением и выключением.
- Журнал изменений в локальной базе (`GET /api/changes`).

## Быстрый старт в Docker

Нужны Docker и Docker Compose v2.

1. **Создайте файл с секретами** до первого запуска. Он не попадает в git.

   ```bash
   cp backend/local_config.example.yaml backend/local_config.yaml
   ```

   Заполните в нём `base_url` (адрес трекера без `/admin_api/v1`) и `api_key`
   (Keitaro: *Maintenance → Users → Admin API keys*).

   > Если файл не создать до `docker compose up`, Docker создаст вместо него каталог,
   > и приложение завершится с ошибкой «это каталог, а не файл».

2. **Проверьте общие настройки** в `backend/config.yaml`, особенно `campaign_defaults`:
   - `domain` - имя домена, добавленного в Keitaro (*Settings → Domains*);
   - `group_name`, `traffic_source_name` - имена группы и источника трафика в Keitaro.

3. **Запустите стек:**

   ```bash
   docker compose up -d --build
   ```

   Откройте **http://localhost:8080**. Порт меняется переменной `FRONTEND_PORT`:
   `FRONTEND_PORT=9000 docker compose up -d`.

4. **Проверьте, что всё работает:** `docker compose ps` (бэкенд должен быть `healthy`),
   `curl http://localhost:8080/api/health` должен вернуть `{"status":"ok"}`.

### Полезные команды

| Задача | Команда |
|--------|---------|
| Логи всех сервисов | `docker compose logs -f` |
| Логи бэкенда (там видны ответы Keitaro при ошибках) | `docker compose logs -f backend` |
| Остановить | `docker compose down` |
| Обновить после изменения кода | `docker compose up -d --build` |
| Перезапустить после правки конфига | `docker compose restart backend` |

Данные (SQLite с журналом и закреплёнными весами) хранятся в томе `backend-data`.
`docker compose down` его не удаляет, а `docker compose down -v` удаляет **вместе с данными**.

### Keitaro на той же машине

Из контейнера `localhost` указывает на сам контейнер. Если Keitaro работает на этом же
компьютере, укажите в `local_config.yaml`:

```yaml
keitaro:
  base_url: http://host.docker.internal
```

Адрес `host.docker.internal` настроен в `docker-compose.yml`.

## Локальная разработка без Docker

Бэкенд (Python 3.11+ и [uv](https://docs.astral.sh/uv/) или обычный venv):

```bash
cd backend
cp local_config.example.yaml local_config.yaml   # заполните адрес и ключ Keitaro
uv venv .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python run.py                          # http://127.0.0.1:8000
```

Запускайте через `run.py` или `uvicorn app.main:app`. Не запускайте `python app/main.py`:
приложение работает как пакет `app`, и такой запуск даёт `ImportError`.

Фронтенд (Node.js 20+, в отдельном терминале):

```bash
cd frontend
npm install
npm run dev                                      # http://localhost:5173, /api проксируется на :8000
```

Тесты бэкенда (Keitaro не нужен, используется заглушка транспорта):

```bash
cd backend && .venv/bin/python -m pytest -q
```

## Конфигурация

Конфиг собирается из двух YAML-файлов в `backend/`:

- `config.yaml` - общие настройки, хранятся в git: база, CORS, заголовок ключа, значения
  по умолчанию для кампаний и параметры потоков.
- `local_config.yaml` - адрес трекера и API-ключ. В git не попадает (в `.gitignore`).

Значения из `local_config.yaml` переопределяют `config.yaml`. Всё проверяется Pydantic:
неизвестные ключи, пустой ключ, адрес с `/admin_api` и неверные значения приводят к понятной
ошибке при старте. Каталог с конфигами можно сменить переменной `CAMPAIGN_EDITOR_CONFIG_DIR`.

Основные параметры в `config.yaml`:

| Ключ | Что задаёт |
|------|------------|
| `keitaro.campaign_defaults.domain` | домен кампании (имя из Keitaro) |
| `keitaro.campaign_defaults.group_name` | группа кампании (ищется по имени) |
| `keitaro.campaign_defaults.traffic_source_name` | источник трафика (ищется по имени) |
| `keitaro.campaign_defaults.campaign_type` | значение `type` при создании кампании (по умолчанию `position`) |
| `keitaro.stream.geo_redirect` | поток выбранных стран: схема, URL редиректа, позиция |
| `keitaro.stream.offer` | поток офферов: схема, позиция |
| `keitaro.stream.country_filter` | имя фильтра страны и его режим (`accept`) |

## Как создаётся кампания

1. Проверяется, что все офферы существуют в Keitaro, и что домен, группа и источник найдены.
   Если что-то не найдено, кампания не создаётся.
2. Создаётся кампания с alias, сгенерированным автоматически.
3. Создаётся поток **«выбранные страны → google.com»** (позиция 1) с фильтром по странам.
4. Создаётся поток **«остальные → офферы»** (позиция 2) без фильтров, с весами офферов.
5. Закреплённые веса сохраняются в локальной базе.

Если какой-то из потоков не создался, кампания выключается, а в ответе перечисляются
уже созданные потоки.

## Офферы и веса

- Веса считаются приложением: сумма всегда 100%, незакреплённые офферы делят остаток поровну,
  остаток по одному проценту получают первые офферы.
- Закрепить вес можно вводом значения от 1 до 100 в таблице. Кнопка **«Авто»** снимает закрепление.
- Нельзя закрепить вес так, чтобы остальным офферам не осталось хотя бы 1%.
  Если все офферы закреплены, их веса должны в сумме давать 100.
- Закрепления хранятся в локальной таблице `offer_pins`, а не в Keitaro.

## API бэкенда

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/api/campaign-creator` | создать кампанию с потоками |
| GET | `/api/campaigns` | список кампаний |
| GET | `/api/campaigns/{id}` | одна кампания |
| PATCH | `/api/campaigns/{id}` | редактирование кампании |
| GET | `/api/campaigns/{id}/offers` | офферы кампании с весами |
| POST | `/api/campaigns/{id}/offers` | добавить оффер |
| DELETE | `/api/campaigns/{id}/offers/{offer_id}` | удалить оффер |
| PUT | `/api/campaigns/{id}/offers/{offer_id}/weight` | закрепить вес (`share` 1–100) или снять (`null`) |
| POST | `/api/offer-weights/preview` | веса по правилам приложения, без записи в Keitaro |
| GET | `/api/meta/offers` | офферы Keitaro |
| GET | `/api/meta/groups` | группы кампаний |
| GET | `/api/meta/traffic-sources` | источники трафика |
| GET | `/api/meta/countries` | страны ISO 3166-1 alpha-2 |
| GET | `/api/meta/creator-defaults` | домен, группа и источник из конфига |
| GET | `/api/changes?limit=50` | журнал изменений |
| GET | `/api/health` | проверка работоспособности |

Интерактивная документация FastAPI доступна на `http://localhost:8000/docs` при локальном запуске
бэкенда (в Docker порт 8000 не публикуется наружу).
