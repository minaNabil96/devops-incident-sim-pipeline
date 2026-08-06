# Case Study: DevOps Incident Simulation Pipeline

> **A Parameterized Prompt Engineering Framework for Reproducible SRE Incident Training**  
> *Validated against SPbETU Academic Paper (2026) — 100% Structural Compliance*

---

## [EN] Situation

**The Problem:** SRE incident response training suffers from a fundamental paradox — real incidents are too dangerous to practise on, while synthetic exercises lack realism and reproducibility. Traditional approaches rely on:

- **Chaos Engineering**: Effective but requires production-grade infrastructure, carries real blast radius risk, and cannot simulate complex multi-layer failure cascades (e.g., cache penetration → Redis OOM → pod OOMKill → 5xx cascade).
- **Tabletop exercises**: Safe but lack technical depth — no real kubectl commands, no Alertmanager JSON, no log/metric artifacts.
- **Manual scenario crafting**: Time-intensive, non-reproducible, and inconsistent across training sessions.

**The Gap:** There was no existing framework that could:
1. Generate a **complete, end-to-end incident lifecycle** with schema-compliant artifacts
2. Maintain **strict academic rigour** while being fully parameterized and reusable
3. Operate against a **production-grade LLM API** with streaming, retry, and sanitization
4. Enforce **SRE industry standards** (Alertmanager schema, Google SRE post-mortem, blameless culture)

---

## [EN] Task

Design and implement a **parameterized, reusable prompt engineering pipeline** that:

1. **Simulates the full 7-stage SRE incident lifecycle**: Scenario → Alert → Triage → RCA → Remediation → Communication → Post-mortem
2. **Achieves 100% structural compliance** with the academic paper *"Development of a set of prompt templates for simulation and response to incidents in DevOps"* (Saint Petersburg Electrotechnical University, 2026)
3. **Generates industry-standard artifacts**: Alertmanager v4 JSON, kubectl commands with `--dry-run=client`, Google SRE blameless post-mortem with SMART action items
4. **Maintains strict namespace consistency** (`production`) across all generated artifacts
5. **Operates reliably** against an external LLM API despite timeout and content-formatting challenges
6. **Supports dual-environment execution**: Google Colab (for teaching) and local development (for production use)

---

## [EN] Action

### Architecture Design

The system was built as a **chain-of-prompts architecture** with 7 sequential Jinja2 templates, each representing a distinct persona in the SRE incident response workflow:

```
Prompt N = Jinja2.render(parameters + context[0..N-1])
              ↓
       LLM.generate(Prompt N)  →  output_N
              ↓
       Post-process(regex strip <think>)  →  cleaned output
              ↓
       Saved to disk  →  injected as context into Stage N+1
```

### Layer 1: Jinja2 Template Engine

Each stage has a dedicated `.j2` template with:
- **Parameter slots** for scenario-specific configuration (20+ parameters)
- **Context injection** from all prior stages (`{{output_stage_0}}` through `{{output_stage_5}}`)
- **Hard constraints** embedded in natural language (namespace enforcement, schema requirements)
- **Conditional logic** using Jinja2 `{% if %}` blocks (e.g., multi-audience communication)

### Layer 2: LLM API Integration (NVIDIA build API / `mistralai/mistral-medium-3.5-128b`)

**Challenge 1 — Long-generation timeout:** Long streaming generations over HTTP can be terminated by intermediate gateways/origin timeouts, as the Kimi-K2.6 model can take 60–180s to generate a full response.

**Solution — SSE Streaming:**
```python
response = requests.post(API_URL, headers=self.headers, json=payload, stream=True, timeout=300)
for line in response.iter_lines():
    if line:
        decoded_line = line.decode('utf-8')
        if decoded_line.startswith('data: '):
            json_str = decoded_line[6:]
            collected_messages.append(data['choices'][0]['delta']['content'])
```
This converted the API interaction from a single blocking request to an **incremental token collection** loop, keeping the connection alive indefinitely.

**Challenge 2 — Reasoning Model Leakage:** Kimi-K2.6 is a "thinking" model that emits its internal monologue inside `<think>...</think>` tags. This contaminated output artifacts with meta-cognitive text.

**Solution — Regex Post-Processor:**
```python
output = re.sub(r'<think>.*?</turn>', '', output, flags=re.DOTALL).strip()
```

### Layer 3: Context Management

The `SREIncidentPipeline` class maintains a `self.context` dictionary that accumulates outputs as stages execute:

```python
def run_stage(self, stage_index, params):
    render_params = params.copy()
    for i in range(stage_index):
        render_params[f"output_stage_{i}"] = self.context.get(f"output_stage_{i}", "")
    prompt = self.render_prompt(stage_name, render_params)
    output = self.llm.generate(prompt, max_new_tokens=max_tokens)
    self.context[f"output_stage_{stage_index}"] = output
```

### Layer 4: Multi-Environment Key Resolution

To support both Colab and local execution without hardcoding secrets:

```python
def get_api_key():
    try:
        from google.colab import userdata
        return userdata.get('NVIDIA_API_KEY')
    except ImportError:
        return os.getenv('NVIDIA_API_KEY')
```

### Validation Protocol

The pipeline was tested against **20 structural compliance criteria** derived from the academic paper, including:

- **Schema validation**: Alertmanager JSON parsed and verified against v4 spec
- **Namespace audit**: All Kubernetes labels checked for `production` (not `securebank-prod` or `payments`)
- **Duration consistency**: 28-minute impact duration verified across 3 separate sections (Metadata, Timeline, Executive Summary)
- **Blameless audit**: No individual employee names in post-mortem
- **SMART checklist**: Each action item validated against the Specific-Measurable-Achievable-Relevant-Time-bound framework

---

## [EN] Result

### Quantitative Results

| Metric | Value |
|--------|-------|
| **Pipeline execution time** | 246.72 seconds (4.1 minutes) |
| **Total generated output** | 27,722 characters |
| **Stages completed** | 7/7 (100%) |
| **API retries required** | 0 |
| **Academic compliance** | 100% (20/20 criteria) |
| **Schema-valid artifacts** | Alertmanager JSON ✅, Post-mortem ✅ |

### Qualitative Outcomes

1. **Academic Validation**: The pipeline generated a complete SecureBank Pro incident report that passes every structural criterion in the SPbETU-2026 paper. The generated post-mortem includes:
   - A **28-minute timeline** with 7 events, each linked to a detection mechanism
   - **4 SMART action items** (PCI-1 through PCI-4) with owners, priorities, and due dates
   - **Blameless language** throughout: "Payments Platform Team" instead of individual names
   - **Root cause analysis** tracing a distributed cache-negative flood through Redis eviction, pod OOMKills, and 5xx error cascades

2. **Production-Grade Artifacts**: The pipeline generates:
   - **Valid Alertmanager v4 JSON** with `namespace: production` enforced
   - **Executable kubectl commands** with `--dry-run=client` previews and rollback steps
   - **Triple-audience communications** (Technical, Business, Executive) with appropriate tone and jargon level

3. **Reproducibility**: The same pipeline can generate infinite distinct scenarios by changing the parameter set — switching the application type, hidden cause, engineer level, or post-mortem style produces a completely new incident lifecycle without code changes.

### Key Engineering Contributions

| Contribution | Impact |
|-------------|--------|
| SSE Streaming integration | Eliminated long-generation timeouts entirely |
| Regex `<think>` tag sanitizer | Produced clean, artifact-ready output from reasoning model |
| Jinja2 chain-of-prompts with context injection | Achieved multi-stage coherence without fine-tuning |
| Multi-environment API key resolution | Enabled Colab teaching + local production deployment from single codebase |
| Strict schema enforcement via prompt constraints | Achieved 100% namespace consistency without post-hoc JSON patching |

---

## [EN] Technologies Used

| Technology | Purpose |
|-----------|---------|
| Python 3.12+ | Core pipeline engine and API integration |
| Jinja2 3.1 | Template rendering with parameter injection |
| NVIDIA build API (`mistralai/mistral-medium-3.5-128b`) | LLM inference with streaming support |
| Server-Sent Events | Real-time token collection from LLM |
| Regex (re.DOTALL) | Post-processing cleanup of reasoning tags |
| python-dotenv | Multi-environment secret management |
| Kubernetes 1.27 | Context for remediation commands |
| Alertmanager v4 | Alert schema standard |
| Google SRE Post-mortem | Blameless report template |

---

<br/>
<hr/>
<br/>

# Кейс: Конвейер симуляции инцидентов DevOps

> **Параметризированная структура prompt engineering для воспроизводимого обучения SRE-инцидентам**  
> *Валидировано по академической статье СПбГЭТУ (2026) — 100% структурное соответствие*

---

## [RU] Ситуация

**Проблема:** Обучение реагированию на SRE-инциденты страдает от фундаментального парадокса — реальные инциденты слишком опасны для практики, а синтетические упражнения лишены реализма и воспроизводимости. Традиционные подходы:

- **Chaos Engineering**: Эффективен, но требует production-инфраструктуры, несёт риск реального воздействия и не может симулировать сложные многоуровневые каскады отказов.
- **Tabletop-упражнения**: Безопасны, но не имеют технической глубины — нет реальных kubectl-команд, Alertmanager JSON, логов и метрик.
- **Ручное создание сценариев**: Трудоёмко, невоспроизводимо и нестабильно между сессиями.

**Пробел:** Не существовало фреймворка, способного:
1. Сгенерировать **полный сквозной жизненный цикл инцидента** с валидными артефактами
2. Сохранять **строгую академическую точность** при полной параметризации и переиспользовании
3. Работать через **production-grade LLM API** с streaming, retry и очисткой
4. Обеспечивать **стандарты SRE-индустрии** (Alertmanager, Google SRE post-mortem, blameless)

---

## [RU] Задача

Спроектировать и реализовать **параметризированную переиспользуемую структуру prompt engineering**, которая:

1. **Симулирует полный 7-этапный жизненный цикл SRE-инцидента**
2. **Достигает 100% структурного соответствия** академической статье СПбГЭТУ-2026
3. **Генерирует индустриальные артефакты**: Alertmanager v4 JSON, kubectl-команды, Google SRE post-mortem
4. **Обеспечивает строгое единообразие namespace** (`production`) во всех артефактах
5. **Работает надёжно** через внешний LLM API, несмотря на таймауты и проблемы форматирования
6. **Поддерживает два окружения**: Google Colab (обучение) и локальную разработку

---

## [RU] Действия

### Архитектура

Система построена как **chain-of-prompts архитектура** с 7 последовательными Jinja2-шаблонами:

```
Prompt N = Jinja2.render(параметры + контекст[0..N-1])
              ↓
       LLM.generate(Prompt N)  →  output_N
              ↓
       Post-process(regex удаление <think>)  →  очищенный вывод
              ↓
       Сохранён на диск  →  контекст для Этапа N+1
```

### Уровень 1: Jinja2 Template Engine

Каждый этап имеет шаблон `.j2` с:
- **Параметрическими слотами** (20+ параметров)
- **Инъекцией контекста** из предыдущих этапов
- **Жёсткими ограничениями** на естественном языке
- **Условной логикой** через `{% if %}`

### Уровень 2: LLM API (NVIDIA build API / `mistralai/mistral-medium-3.5-128b`)

**Проблема 1 — Long-generation Timeout:** API завершал запросы дольше 30 секунд ошибкой long-generation timeouts.

**Решение — SSE Streaming:** Конвертировал блокирующий запрос в инкрементальный сбор токенов с `stream=True` и таймаутом 300 секунд.

**Проблема 2 — Утечка мыслей модели:** Kimi-K2.6 выводил внутренние монологи в тегах `<think>...</think>`.

**Решение — Regex-очистка:** `re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)`

### Уровень 3: Управление контекстом

Класс `SREIncidentPipeline` накапливает результаты этапов в словаре `self.context`.

### Уровень 4: Мультисредовое получение ключа

Поддержка Colab Secrets, `.env` файла и системной переменной окружения через единую функцию.

---

## [RU] Результат

### Количественные результаты

| Метрика | Значение |
|---------|----------|
| **Время выполнения** | 246.72 сек (4.1 мин) |
| **Сгенерировано** | 27,722 символа |
| **Этапов выполнено** | 7/7 (100%) |
| **Повторных попыток API** | 0 |
| **Соответствие стандартам** | 100% (20/20 критериев) |
| **Валидные артефакты** | Alertmanager JSON ✅, Post-mortem ✅ |

### Качественные результаты

1. **Академическая валидация**: Полный отчёт SecureBank Pro, проходящий все структурные критерии статьи СПбГЭТУ-2026
2. **Production-grade артефакты**: Валидный Alertmanager JSON, исполняемые kubectl-команды, трёхаудиторные коммуникации
3. **Воспроизводимость**: Бесконечное множество сценариев через изменение параметров — без изменения кода

### Ключевые инженерные вклады

| Вклад | Влияние |
|-------|---------|
| SSE Streaming | Устранение long-generation timeouts таймаутов |
| Regex очистка `<think>` | Чистый вывод из reasoning-модели |
| Jinja2 chain-of-prompts | Многоэтапная связность без fine-tuning |
| Мультисредовой API-ключ | Colab + локальный запуск из единого кода |
| Контроль схемы через промпты | 100% единообразие namespace |

---

## [RU] Использованные технологии

| Технология | Назначение |
|-----------|-----------|
| Python 3.12+ | Основной движок и интеграция с API |
| Jinja2 3.1 | Рендеринг шаблонов с инъекцией параметров |
| NVIDIA build API (`mistralai/mistral-medium-3.5-128b`) | LLM с поддержкой streaming |
| Server-Sent Events | Инкрементальный сбор токенов |
| Regex (re.DOTALL) | Очистка reasoning-тегов |
| python-dotenv | Мультисредовое управление секретами |
| Kubernetes 1.27 | Контекст команд remediation |
| Alertmanager v4 | Стандарт схемы алертов |
| Google SRE Post-mortem | Шаблон blameless-отчёта |
