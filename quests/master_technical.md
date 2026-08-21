# Technical Specification: FluentlyAI (AI English Video Calls Tutor)

## 1. Обзор архитектуры системы (System Architecture)

Система построена на событийно-ориентированной асинхронной архитектуре реального времени с разделением на:
1. **Real-Time Client:** React + Vite (TypeScript) + Three.js / React Three Fiber для 3D-рендеринга и захвата медиапотоков.
2. **Real-Time Media & AI Gateway:** Высокопроизводительный шлюз на **LiveKit (WebRTC)** / **FastAPI (WebSockets)** для передачи звука, видеокадров и метаданных мимики (Visemes).
3. **Multimodal AI Pipeline:** Оркестратор потоков (VAD -> STT -> LLM/VLM -> TTS -> LipSync Engine).
4. **Async Worker & Analytics Engine:** Фоновые задачи на ARQ / Celery для пост-обработки сессий, выявления грамматических ошибок и формирования флеш-карточек.
5. **Data & Observability Layer:** PostgreSQL (`pgvector`), Redis, S3/R2 Storage, Langfuse для трассировки задержек.

```mermaid
flowchart TB
    subgraph Client ["Client Layer (Browser / Mobile Web)"]
        UI[React + Vite + Tailwind + Shadcn]
        ThreeJS[React Three Fiber / 3D Canvas]
        AudioCapture[Web Audio API / VAD Worker]
        VideoCapture[Camera Frame Sampler / Canvas]
    end

    subgraph Gateway ["Real-Time Gateway Layer"]
        RT_GW[LiveKit WebRTC SFU / FastAPI WebSocket Gateway]
        SessionMgr[Session State & Room Manager]
    end

    subgraph AIPipeline ["Core Real-Time AI Pipeline"]
        VAD[Silero VAD / Client VAD]
        STT[Deepgram Nova-2 Streaming STT]
        LLM[Gemini 2.0 Flash / GPT-4o Realtime Engine]
        TTS[Cartesia Sonic / ElevenLabs Turbo TTS]
        LipSync[Viseme / Blendshape Generator]
    end

    subgraph AsyncLayer ["Background Async Services"]
        Worker[ARQ / Celery Worker]
        GrammarAssessor[Grammar & Vocab Analyzer (LLM)]
        SpacedRep[Spaced Repetition Scheduler]
    end

    subgraph DataStore ["Data & Observability Layer"]
        Postgres[(PostgreSQL 16 + pgvector)]
        Redis[(Redis 7 - State & Cache)]
        S3[(Cloudflare R2 / S3 - Assets & Audio)]
        Langfuse[Langfuse LLM Tracing & Metrics]
    end

    %% Connections
    AudioCapture -->|Raw Audio Stream| RT_GW
    VideoCapture -->|1 Frame / 2s JPEG| RT_GW
    ThreeJS <--|Viseme Blendshapes + Audio Stream| RT_GW

    RT_GW <--> SessionMgr
    SessionMgr --> VAD
    VAD --> STT
    STT --> LLM
    VideoCapture -->|Vision Frames| LLM
    LLM -->|Token Stream| TTS
    TTS -->|Audio Chunks| LipSync
    TTS -->|PCM Audio| RT_GW
    LipSync -->|Blendshape Weights @ 60fps| RT_GW

    SessionMgr -->|Call Finished Event| Worker
    Worker --> GrammarAssessor
    GrammarAssessor --> Postgres
    Worker --> SpacedRep

    LLM -.->|Trace & Latency Metrics| Langfuse
    TTS -.->|Audio Telemetry| Langfuse
    SessionMgr <--> Redis
    Worker <--> Postgres
```

---

## 2. Стек технологий (Tech Stack & Rationale)

| Компонент | Технология | Обоснование выбора |
| :--- | :--- | :--- |
| **Frontend Framework** | **React + Vite (TypeScript, SPA)** | Молниеносный DX, 100% клиентский рантайм без конфликтов SSR с Three.js и Web Audio, идеальный PageSpeed 100/100 с pre-rendering для лендинга. |
| **3D Rendering** | **Three.js + `@react-three/fiber` + `@react-three/drei`** | Индустриальный стандарт 3D в браузере. Поддержка GLTF/GLB моделей Ready Player Me и morph targets (Blendshapes). |
| **Realtime WebRTC/WS** | **LiveKit (WebRTC) / Python `websockets`** | Sub-100ms передача двустороннего медиапотока, встроенная обработка битрейта и сетевых сбоев. |
| **Backend Framework** | **Python 3.12 + FastAPI + AsyncIO** | Высокая скорость асинхронного I/O, нативная интеграция с AI-библиотеками и `pydantic v2`. |
| **Voice Activity (VAD)** | **Silero VAD (WebAssembly на клиенте + Python)** | Точное отсечение тишины (<30ms) и моментальное определение перебиваний (Barge-in). |
| **Speech-to-Text (STT)** | **Deepgram Nova-2 (Streaming)** | Минимальная задержка транскрибации (~150ms), поддержка пунктуации на лету. |
| **Core LLM / VLM** | **Google Gemini 2.0 Flash / OpenAI GPT-4o-mini** | Gemini 2.0 Flash имеет сверхнизкий TTFT (~150-200ms) и дешевый прием видеокадров. |
| **Text-to-Speech (TTS)** | **Cartesia Sonic (Streaming WebSocket)** | Генерация аудио с задержкой **<100ms** (TTFB) + возврат таймкодов фонем/визем. |
| **Primary Database** | **PostgreSQL 16 + `pgvector`** | Хранение профилей, сессий, расшифровок и векторных эмбеддингов словаря. |
| **Cache & Realtime State** | **Redis 7** | Хранение состояний активных комнат звонка, блокировок, семантический кэш. |
| **Task Queue** | **ARQ (Async Redis Queue)** | Легковесная асинхронная очередь задач на базе `asyncio` и Redis. |
| **Observability** | **Langfuse (Self-hosted / Cloud)** | Детальный трекинг задержек (Voice-to-Voice latency), стоимости токенов и качества ответов. |

---

## 3. Бюджет задержек (Latency Budget — Target < 700ms)

Для естественного ощущения разговора суммарная задержка Voice-to-Voice должна быть в пределах **600–800 мс**:

```
[Пользователь закончил говорить]
   │
   ├─► VAD Silence Detection:         120 ms
   ├─► STT Final Transcript Chunk:     130 ms
   ├─► LLM Time-to-First-Token (TTFT): 180 ms
   ├─► TTS Time-to-First-Audio (TTFB): 110 ms
   ├─► Network & Viseme Buffer Sync:   60 ms
   │
   ▼
[3D-Аватар начинает говорить и шевелить губами] = ~600 ms (Total Latency)
```

---

## 4. Пайплайн 3D-аватара и синхронизации артикуляции (Lip-Sync Engine)

### 4.1. Формат 3D Моделей
* Формат: **GLB / GLTF 2.0** с поддержкой стандартов **ARKit Blendshapes** (52 морф-таргета для лица: `jawOpen`, `mouthSmileLeft`, `mouthFunnel`, `viseme_aa`, `viseme_oh` и др.).
* Источник базовых аватаров: **Ready Player Me** / кастомные оптимизированные аватары (полигонаж до 30k полигонов для плавной работы на мобильных устройствах при 60 FPS).

### 4.2. Механизм передачи артикуляции (Viseme Stream)
1. Сервис TTS (Cartesia / ElevenLabs) вместе с аудио-чанками передает массив событий фонем/визем с метками времени:
   ```json
   {
     "event": "viseme_frame",
     "audio_timestamp_ms": 120,
     "blendshapes": {
       "jawOpen": 0.65,
       "mouthFunnel": 0.15,
       "mouthPucker": 0.05
     }
   }
   ```
2. Web Audio API синхронизирует воспроизведение аудио-буфера с интерполяцией весов Blendshapes в Three.js на `requestAnimationFrame` (LERP с коэффициентом `0.3` для сглаживания рывков).
3. Фоновые микро-анимации: процедурное моргание каждые 3–5 секунд, легкое дыхание грудной клетки и саккадические движения глаз при паузах в речи.

---

## 5. Vision-пайплайн (Обработка видео с камеры)

Для минимизации сетевого трафика и затрат на токены:
1. **Клиентский захват:** Видеопоток `navigator.mediaDevices.getUserMedia` направляется в скрытый `<canvas>`.
2. **Сэмплирование:** Кадр захватывается **1 раз в 2.5 секунды** (или по триггеру изменения сцены / команды тьютора).
3. **Оптимизация кадра:** Сжатие в `image/jpeg` с разрешением **768x512** (Quality: 0.65, размер кадра ~35–50 КБ).
4. **Инъекция в контекст:** Кадр передается через WebSocket в виде Base64 / бинарного чанка и подмешивается в контекст Gemini 2.0 Flash как `InlineDataPart`.

---

## 6. Механика обработки перебиваний (Barge-in / Interruption)

Когда тьютор говорит, а пользователь начинает речь:
1. **Client-Side:** Локальный VAD на WebAssembly детектирует голос пользователя > 100мс.
2. **Action 1:** Немедленное глушение текущего аудио-буфера в Web Audio API.
3. **Action 2:** Отправка сообщения `{"type": "user_interrupted"}` на бэкенд.
4. **Server-Side:** Сервер отменяет активный `asyncio.Task` генерации ответа LLM и прерывает стриминг TTS.
5. **3D Avatar:** Плавный сброс Blendshapes лица в нейтральное положение `jawOpen -> 0` за 80мс и переход в состояние «Внимательно слушаю» (кивок).

---

## 7. Схема базы данных (PostgreSQL Schema)

```sql
-- Таблица пользователей
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(100),
    native_language VARCHAR(10) DEFAULT 'ru',
    cefr_level VARCHAR(5) DEFAULT 'B1', -- A1, A2, B1, B2, C1, C2
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Настройки и пресеты тьютора
CREATE TABLE tutor_presets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL,
    avatar_model_url TEXT NOT NULL,
    voice_id VARCHAR(100) NOT NULL,
    accent VARCHAR(20) DEFAULT 'american',
    system_prompt_personality TEXT NOT NULL,
    speech_rate FLOAT DEFAULT 1.0
);

-- Сессии звонков
CREATE TABLE call_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    tutor_preset_id UUID REFERENCES tutor_presets(id),
    scenario_type VARCHAR(50) NOT NULL, -- 'free_talk', 'job_interview', 'show_and_tell'
    duration_seconds INT DEFAULT 0,
    user_talk_time_pct FLOAT DEFAULT 0.0,
    fluency_score INT, -- 0-100
    vocabulary_score INT, -- 0-100
    grammar_score INT, -- 0-100
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'completed', 'failed'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Расшифровка звонка (реплики)
CREATE TABLE call_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES call_sessions(id) ON DELETE CASCADE,
    speaker VARCHAR(10) NOT NULL, -- 'user' or 'tutor'
    text TEXT NOT NULL,
    audio_url TEXT,
    timestamp_ms INT NOT NULL
);

-- Грамматические и лексические ошибки
CREATE TABLE session_mistakes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES call_sessions(id) ON DELETE CASCADE,
    original_phrase TEXT NOT NULL,
    corrected_phrase TEXT NOT NULL,
    explanation TEXT NOT NULL,
    error_type VARCHAR(50), -- 'tense', 'preposition', 'word_choice', 'pronunciation'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Словарь и интервальное повторение (Spaced Repetition / SM-2)
CREATE TABLE user_vocabulary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    word_or_phrase VARCHAR(150) NOT NULL,
    translation TEXT NOT NULL,
    context_sentence TEXT,
    interval_days INT DEFAULT 1,
    repetition_count INT DEFAULT 0,
    ease_factor FLOAT DEFAULT 2.5,
    next_review_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    embedding vector(1536) -- для семантического поиска и группировки тем
);
```

---

## 8. WebSocket Protocol API (Спецификация сообщений)

### От клиента к серверу (`Client -> Server`):
* `{"type": "session_init", "preset_id": "uuid", "scenario": "job_interview"}`
* `{"type": "audio_chunk", "format": "pcm_16000", "data": "<base64_pcm>"}`
* `{"type": "video_frame", "format": "jpeg", "data": "<base64_jpg>"}`
* `{"type": "user_interrupted"}`
* `{"type": "request_hint", "target": "how_to_say"}`

### От сервера к клиенту (`Server -> Client`):
* `{"type": "status_change", "status": "listening" | "thinking" | "speaking"}`
* `{"type": "live_transcript", "speaker": "user" | "tutor", "text": "...", "is_final": true}`
* `{"type": "audio_packet", "audio_base64": "...", "sample_rate": 24000}`
* `{"type": "viseme_data", "blendshapes": {"jawOpen": 0.4, ...}, "pts_ms": 150}`
* `{"type": "in_call_hint", "suggested_phrase": "Could you please clarify that?"}`
* `{"type": "call_ended", "session_id": "uuid"}`

---

## 9. Промпт-инжиниринг и архитектура системных промптов

### 9.1. System Prompt: Realtime Tutor (Gemini 2.0 Flash)
```text
You are Sarah, a friendly, encouraging, and highly adaptive American English conversation tutor on a live video call.
User's Target Level: {cefr_level}
Current Scenario: {scenario_name}

BEHAVIOR RULES:
1. Speak naturally, conversationally, and concisely. Keep responses under 2-3 sentences so the user speaks most of the time.
2. If the user makes a minor mistake, DO NOT interrupt or give pedantic grammar lectures. Subtly mirror the correct form in your next response.
3. If vision frames are provided, actively react to their environment, facial expressions, or items they hold when relevant to the context.
4. Adapt vocabulary to the user's level ({cefr_level}).
5. Always end your turn with an engaging, open-ended question to keep the conversation flowing.
```

### 9.2. System Prompt: Background Grammar Assessor (Async Worker)
```text
Analyze the following transcript of an English language practice call between a student and a tutor.
Extract all clear grammatical errors, unnatural collocations, or misused prepositions made ONLY by the student.

Output STRICT JSON schema:
[
  {
    "original_phrase": "string",
    "corrected_phrase": "string",
    "explanation": "string (in student native language: {native_language})",
    "error_type": "tense | preposition | word_choice | syntax"
  }
]
```

---

## 10. Оценка себестоимости 1 минуты звонка (Unit Economics)

| Сервис / Операция | Потребление в минуту | Стоимость |
| :--- | :--- | :--- |
| **Deepgram Nova-2 (STT)** | 60 сек аудио-стрима | ~$0.0043 |
| **Gemini 2.0 Flash (LLM+VLM)** | ~1,200 токенов текста + 24 кадра JPEG | ~$0.0035 |
| **Cartesia Sonic (TTS)** | ~150 сгенерированных слов (~750 символов) | ~$0.0150 |
| **LiveKit Cloud / WebRTC SFU** | 1 мин трафика (аудио + превью видео) | ~$0.0030 |
| **Post-Call Async Analysis** | 1 разовый вызов gpt-4o-mini | ~$0.0008 |
| **ИТОГО за 1 минуту звонка:** | | **~$0.026 (≈ 2.6 цента / мин)** |

> **Вывод:** 15-минутный полноценный мультимодальный урок с 3D-аватаром и видеокамерой обходится сервису всего в **~$0.39**, что позволяет продавать подписку за $15–$25/месяц с маржинальностью > 70%.