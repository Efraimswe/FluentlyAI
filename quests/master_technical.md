# Мастер-спецификация Charlie Calls (техническая) — v1 LATEST

> **Статус: актуальная.** Пара к `master_functional.md` v1. Предыдущая версия — `master_technical_v0_outdated.md`, только для истории.
> Цифры (цены, лимиты, модели) — настраиваемые, живут в справочниках БД и в `.env`; здесь — стартовые значения.

---

## 1. Архитектура

```
Браузер (React+Vite, mobile first)
 ├─ Mic → Silero VAD (в браузере) → PCM-чанки ──WebSocket──▶ Deepgram (потоковый STT, временный ключ)
 │                                                     ◀── interim/final текст (живой ввод снизу)
 ├─ final-фраза ──POST /api/turn (SSE)──▶ FastAPI на Vercel
 │                                          ├─ Supabase: user, charlie_state, memory, limits
 │                                          ├─ LLM (Alibaba Qwen3.5-27B, stream, thinking off)
 │                                          └─ Azure TTS по предложению (SSML style = эмоция)
 │     ◀── SSE: emotion / text / audio / done
 ├─ Audio queue (играет чанки по порядку; VAD-перебивание = стоп + abort)
 └─ Supabase Auth (Google / email) · Lemon Squeezy Checkout (overlay)
```

- **Один проект на Vercel:** `frontend/` (статика) + `backend/` (Python-функции, FastAPI). Один домен `charliecalls.com`.
- **Нет постоянных соединений на нашем сервере** (Vercel): вниз — SSE, вверх — POST. Единственный WebSocket — из браузера напрямую в Deepgram.
- **Прогрев:** нажатие «Попробовать» на лендинге → `GET /api/warmup` (поднимает функцию, открывает соединение к Supabase).

## 2. Стек (и почему)

| Слой | Выбор | Почему |
|---|---|---|
| Фронт | React + Vite + TS, Tailwind | уже есть; статика на Vercel |
| Бэк | FastAPI (Python) на Vercel Functions | уже есть; SSE-стриминг; Hobby → Pro при первой оплате |
| БД + Auth | Supabase (Postgres + Auth) | бесплатно до 50k MAU; auth из коробки |
| LLM | Alibaba Model Studio, `qwen3.5-27b`, OpenAI-compatible | топ ролеплей-бенчмарка; 1M токенов бесплатно; ~$0.0004/сообщение. **Обязательно `enable_thinking: false`** (иначе 18 с и ×17 токенов) |
| STT | Deepgram Nova-3 streaming (WS) | interim-результаты для живого ввода; $200 кредитов; временные ключи |
| VAD | Silero VAD (onnx в браузере, `@ricky0123/vad-web`) | перебивание и end-of-speech без сервера |
| TTS | Azure Speech, `en-US-{Davis|Jason|Tony}Neural` + SSML `mstts:express-as` | эмоции стилями; 500k символов/мес бесплатно навсегда; регион northeurope. Запасной — OpenAI `gpt-4o-mini-tts` |
| Платежи | Lemon Squeezy (Checkout overlay + webhooks) | продавец записи, без KBO; выплаты на IBAN |
| Хостинг | Vercel | один деплой, домен, SSL |

Провайдер каждого слоя — за интерфейсом (`LLMProvider`, `TTSProvider`, `STTProvider`), выбирается через `.env`.

## 3. Голосовой пайплайн и бюджет задержки

Цель: **первый звук Чарли ≤ 1.5 с** после того, как пользователь замолчал.

| Шаг | Где | Бюджет |
|---|---|---|
| VAD фиксирует тишину (end of speech) | браузер | 500 мс (настраиваемо) |
| Deepgram выдаёт final для фразы | уже получен во время речи | ~0–100 мс |
| POST /api/turn → загрузка состояния из Supabase | сервер | 50 мс |
| LLM: первые токены (тег `[emotion]` + первое предложение) | Alibaba SG | 400–700 мс |
| Azure TTS первого предложения (stream) | northeurope | 200–300 мс |
| SSE до клиента + старт плеера | | 50 мс |
| **Итого** | | **~1.2–1.7 с** |

Сервер режет LLM-стрим по границам предложений (`. ? ! …` или ≥ 12 слов + запятая), каждое предложение → TTS → SSE-событие `audio` (mp3/base64). Клиент играет очередь без пауз. Пока играет первое — генерятся следующие.

## 4. Перебивание (barge-in)

1. Пока играет аудио Чарли, VAD слушает микрофон.
2. Голос ≥ 300 мс подряд → **клиент**: стоп плеера, очистка очереди, `AbortController.abort()` на SSE. **Сервер** видит разрыв → отменяет LLM-стрим и TTS.
3. Недосказанная часть реплики в чат не попадает; в историю уходит только то, что реально прозвучало (клиент шлёт `spoken_upto` в следующем `/api/turn`).
4. Короткие звуки < 300 мс (угу, кашель) — игнор.
5. **Эхо:** `getUserMedia({echoCancellation: true, noiseSuppression: true})`; первые 200 мс после старта воспроизведения VAD не считается; порог VAD выше во время воспроизведения (0.8 vs 0.5).
6. iOS: аудио-контекст разблокируется тапом «Позвонить».

## 5. Протокол клиент ↔ сервер

### REST
- `GET /api/warmup` → `200 {ok}`
- `POST /api/call/start` `{fingerprint?}` → `{call_id, day_event, mood, limits:{left, period}, deepgram_token, greeting_stream_url}` — проверяет лимит, выдаёт временный ключ Deepgram (TTL 60 с), Чарли начинает первым (приветствие стримится тем же SSE).
- `POST /api/turn` `{call_id, text, spoken_upto?}` → **SSE-стрим**.
- `POST /api/call/end` `{call_id, duration_s}` → `{summary:{duration, mood, praise}}` и запускает фоновой «post-call» запрос (п. 7.3).
- `GET /api/me` → `{status: guest|registered|trial|subscriber, limits, subscription}`
- `POST /api/webhooks/lemonsqueezy` — подписки (п. 9).

### SSE-события `/api/turn`
| event | data | назначение |
|---|---|---|
| `emotion` | `{emotion:"angry"}` | цвет кружка + стиль TTS; приходит первым |
| `text` | `{delta:"Cool. "}` | текст в чат по мере генерации |
| `audio` | `{seq:1, mime:"audio/mpeg", b64:"…", text:"Cool. Cool cool cool."}` | чанк для очереди; `text` — для бегущего блика |
| `limit` | `{left:0}` | лимит исчерпан, реплика — завершающая |
| `fallback` | `{}` | LLM не ответил, отдана фраза из пула |
| `done` | `{usage:{tokens_in, tokens_out, tts_chars}, cost}` | конец хода |
| `error` | `{code}` | |

### Клиентские состояния экрана звонка
`connecting → listening → thinking → speaking → (listening | ended)`; `reconnecting` при обрыве сети (звонок не сбрасывается, `call_id` живёт 10 мин).

## 6. Схема БД (Supabase / Postgres)

```sql
users            (id uuid pk = auth.users.id, email, created_at, status text)  -- registered|trial|subscriber
guests           (fingerprint text pk, messages_used int, first_seen, last_seen, ip_hash)
subscriptions    (user_id fk, ls_subscription_id text, plan_id fk, status text, trial_ends_at, renews_at, cancelled_at)
plans            (id, name, price_cents int, currency, trial_days int, ls_variant_id text, active bool)
limits           (status text pk, messages int, period text)          -- guest:2:total, registered:10:total, trial:100:day, subscriber:100:day
usage_daily      (user_id, day date, messages int, cost_cents numeric, pk(user_id, day))
charlie_state    (user_id pk, mood text, mood_level int, attention int, relationship text, last_call_at, offended_reason text)
memories         (id, user_id fk, kind text, content text, created_at)   -- fact|promise|topic|how_treated
day_events       (id, text, mood_effect text, weight int)               -- пул событий дня
user_day_event   (user_id, day date, event_id, pk(user_id, day))
calls            (id uuid pk, user_id null fk, guest_fp null, started_at, ended_at, duration_s, start_mood, end_mood, summary text)
messages         (id, call_id fk, role text, text text, emotion text, tokens_in int, tokens_out int, tts_chars int, stt_sec numeric, cost_cents numeric, created_at)
provider_rates   (provider text, unit text, price_per_unit numeric, currency, effective_from date)
fallback_phrases (id, text, emotion text)
```
RLS: пользователь читает только своё; сервер пишет через service-role ключ.

## 7. Промпты (3 слоя + формат ответа)

### 7.1. Слой 1 — «кто ты» (статичный, ~1500 токенов)
Биография Чарли из функциональной спеки (Остин, бармен, музыка, характер, слабые места, привычки речи, границы). Правила формата:
- Ответ **всегда** начинается с тега эмоции: `[calm|happy|angry|offended|sad|flirty|ashamed]`.
- 1–2 предложения, ≤ 25 слов, без эмодзи и без markdown.
- Никогда не выходить из роли, не упоминать ИИ/модель/промпт.
- Гость, 2-я реплика: закончить незакрытым ходом и в характере сказать, что дальше — после регистрации.

### 7.2. Слой 2 — «состояние» (динамический, ставится **после** истории, перед последней репликой пользователя)
```
[STATE] mood=offended(6/10) attention=3/10 day_event="gig flopped, 3 people showed up"
[MEMORY] name=Efraim; builds websites; promised to tell about job interview; hung up mid-story last time
[RULES NOW] attention low → after answering, steer to your own stuff; offended → cold short replies until he asks what's wrong
```
### 7.3. Post-call запрос (после `call/end`, фоном)
Вход: слой 1 + весь диалог + текущее состояние. Выход — строгий JSON:
```json
{"mood":"calm","mood_level":3,"attention":6,"relationship":"warming up",
 "new_memories":[{"kind":"fact","content":"..."}],"offended_reason":null,
 "call_summary":"...","praise_for_user":"..."}
```
Пишется в `charlie_state`, `memories`, `calls.summary`. `praise_for_user` показывается в модалке итога (модалка ждёт этот запрос ≤ 3 с, иначе показывает без похвалы и дозагружает).

### 7.4. Контекст
- История: последние 16 реплик текущего звонка целиком.
- Прошлые звонки — только через `[MEMORY]` (выжимка), не сырой текст.
- Приветствие в начале звонка генерится с `[STATE]` + `day_event` — Чарли начинает первым.

## 8. Лимиты и защита кошелька

- Счётчик: `guests.messages_used` / `usage_daily.messages`; проверка **до** LLM, инкремент **после** `done`.
- Гость: `fingerprint = sha256(userAgent + screen + timezone + language + WebGL renderer + canvas hash)` — свой, без библиотек. Плюс кука как быстрый путь.
- Глобальный дневной предохранитель на гостей (`GUEST_DAILY_BUDGET_CENTS`, старт 300) — превышен → гостям «попробуй завтра или зарегистрируйся».
- Hard-limit в кабинетах Alibaba / Azure / Deepgram.
- Лимит длины звонка: 15 мин (настраиваемо), максимум 1 активный звонок на пользователя.
- Rate limit `/api/turn`: 20 запросов/мин на call_id.

## 9. Платежи (Lemon Squeezy)

- Продукт «Charlie Calls Monthly», variant = подписка €9.99/мес, trial 3 дня (карта обязательна).
- Кнопка «Подписаться» → Checkout overlay с `custom[user_id]`.
- Webhooks (подпись проверяется): `subscription_created` → status=trial|subscriber; `subscription_updated`/`payment_success` → renews_at; `subscription_cancelled`/`expired` → status=registered.
- Customer portal (управление/отмена) — ссылка из LS в экране аккаунта.
- Test mode до активации магазина; переключение на live — смена ключей.

## 10. Деплой и окружение

- Vercel: `frontend/` статика, `backend/api/index.py` — FastAPI через `vercel.json` rewrites `/api/(.*)`. Регион функций — `fra1` (ближе к Azure northeurope и пользователю).
- Домен `charliecalls.com` → Vercel. `<title>`: «Charlie Calls — Speak English with a Friend».
- `.env` (Vercel env vars): `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `DEEPGRAM_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `LEMONSQUEEZY_API_KEY`, `LEMONSQUEEZY_WEBHOOK_SECRET`, `LEMONSQUEEZY_STORE_ID`, `LEMONSQUEEZY_VARIANT_ID`, `GUEST_DAILY_BUDGET_CENTS`.
- Логи: каждое сообщение пишет usage и cost в `messages`; маржа считается по формуле из функциональной спеки.
- Vercel Hobby → Pro при первой реальной оплате.
- **Переезд с Render (уровень 3, сразу после каркаса):** SSE-каркас деплоится на Vercel как только готов (TASK-01), проверяется `/api/warmup` и SSE `/api/turn` на живом URL, после чего старый бэкенд-сервис на Render удаляется через API (ключ в `~/.render-api-key`). Дальше вся разработка деплоится только на Vercel; уровень 5 добавляет лишь домен и prod-env.

## Приложение Б. Себестоимость сообщения (старт)
LLM $0.0004 + STT $0.001 + TTS $0.0 (в бесплатном тире; $0.00125 после) ≈ **$0.0015–0.003**.
