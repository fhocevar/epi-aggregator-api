# Epi Clipping API

API para **coletar**, **normalizar**, **persistir** e **expor** dados epidemiológicos, com suporte a múltiplas fontes (ex: WHO DON, InfoDengue, e-SUS OpenSearch, SIVEP-SRG, e **DEMAS – MS Dados Abertos**).

---

## Sumário

* [Visão geral](#visão-geral)
* [Stack](#stack)
* [Arquitetura](#arquitetura)
* [Subir local](#subir-local)

  * [Docker Postgres](#docker-postgres)
  * [Instalar dependências](#instalar-dependências)
  * [Configurar .env](#configurar-env)
  * [Migrations](#migrations)
  * [Subir API](#subir-api)
* [Endpoints principais](#endpoints-principais)
* [DEMAS (MS Dados Abertos)](#demas-ms-dados-abertos)

  * [Datasets configurados](#datasets-configurados)
  * [Client: timeouts, retries e deadline hard](#client-timeouts-retries-e-deadline-hard)
  * [Collector](#collector)
  * [Normalizer](#normalizer)
  * [Sync Service (RAW, EVENTS, DIM)](#sync-service-raw-events-dim)
  * [Import Service (CSV/ZIP/URL/S3)](#import-service-csvzipurls3)
  * [db_bulk: bulk insert + debug row ruim](#db_bulk-bulk-insert--debug-row-ruim)
  * [Routers /demas](#routers-demas)
  * [Fluxos recomendados](#fluxos-recomendados)
* [Postman (copiar/colar)](#postman-copiarcolar)
* [Troubleshooting](#troubleshooting)

---

## Visão geral

A API mantém um pipeline típico:

```
[Upstream] -> [Collector/Client] -> [RAW no Postgres] -> [Normalizer] -> [EVENTS/DIM] -> [Routers]
```

Motivo: upstreams públicos podem ser instáveis/lentos. O módulo **DEMAS** foi implementado com **fail-fast** e **circuit breaker** para evitar “travar 49 minutos”.

---

## Stack

* Python + FastAPI
* PostgreSQL
* SQLAlchemy Async + asyncpg
* Alembic
* Poetry
* httpx (AsyncClient)
* Docker Compose (Postgres local)

---

## Arquitetura

```
app/
  collectors/
    demas/
      client.py
      collector.py
  normalizers/
    demas/
      normalizer.py
  routers/
    demas.py
  services/
    demas_service.py
    demas_import_service.py
    demas_sources.py
  db_bulk.py
  demas_models.py   # DemasRaw, DemasEvent, DemasMunicipioDim
  settings.py
```

---

# Subir local

## Docker Postgres

`docker-compose.yml`:

```yaml
version: "3.9"

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: epi_clipping
      POSTGRES_USER: epi
      POSTGRES_PASSWORD: epi
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Subir:

```bash
docker compose up -d
```

---

## Instalar dependências

```bash
poetry install
```

---

## Configurar .env

Criar:

```bash
cp .env.example .env
```

Exemplo consolidado (com todas variáveis que você enviou):

```env
APP_ENV=dev
DATABASE_URL=postgresql+asyncpg://epi:epi@localhost:5432/epi_clipping

# Scheduler
SYNC_INTERVAL_MINUTES=15

# WHO
WHO_DON_URL=https://www.who.int/api/news/diseaseoutbreaknews

# InfoDengue
INFODENGUE_ALERTCITY_URL=https://info.dengue.mat.br/api/alertcity
INFODENGUE_DEFAULT_GEOCODES=3304557,3550308
INFODENGUE_DEFAULT_DISEASES=dengue,chikungunya,zika
INFODENGUE_DEFAULT_EW_START=1
INFODENGUE_DEFAULT_EW_END=53
INFODENGUE_DEFAULT_EY_START=2025
INFODENGUE_DEFAULT_EY_END=2026

# SIVEP SRG (exemplo)
OPENDATASUS_SIVEP_SRG_CSV_URL=https://s3.sa-east-1.amazonaws.com/ckan-saude/SRAG/2024/INFLUD2024.zip

# DEMAS
DEMAS_BASE_URL=https://apidadosabertos.saude.gov.br
DEMAS_TIMEOUT_SECONDS=180
DEMAS_LIMIT=20
DEMAS_SLEEP_SECONDS=0.20
DEMAS_ARBOVIROSES_YEARS=2024,2025,2026

# e-SUS OpenSearch
ESUS_OPENSEARCH_BASE_URL=https://notifica-prd-es.saude.gov.br
ESUS_OPENSEARCH_USER=user-public-notificacoes
ESUS_OPENSEARCH_PASSWORD=***
ESUS_OPENSEARCH_TIMEOUT_SECONDS=60
ESUS_OPENSEARCH_PAGE_SIZE=200
ESUS_OPENSEARCH_MAX_PAGES=20

# Alert Engine
ALERT_COOLDOWN_MINUTES=720
```

---

## Migrations

```bash
alembic revision --autogenerate -m "init"
alembic upgrade head
```

---

## Subir API

```bash
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

---

# Endpoints principais

Testar:

* `GET http://localhost:8080/health`
* `GET http://localhost:8080/epidemiologia/boletins`
* `GET http://localhost:8080/epidemiologia/casos?disease=dengue&geo_code=3304557`
* `GET http://localhost:8080/epidemiologia/indicadores?disease=dengue&geo_code=3304557`
* `GET http://localhost:8080/epidemiologia/alertas`

---

# DEMAS (MS Dados Abertos)

Módulo para consumir `apidadosabertos.saude.gov.br`, persistir RAW, normalizar EVENTS e manter dimensão de municípios.

## Datasets configurados

Em `app/services/demas_service.py`:

* `arboviroses_dengue` → `/arboviroses/dengue` (`uses_year=True`, `kind=events`)
* `arboviroses_chikungunya` → `/arboviroses/chikungunya` (`uses_year=True`, `kind=events`)
* `arboviroses_zikavirus` → `/arboviroses/zikavirus` (`uses_year=True`, `kind=events`)
* `arboviroses_febre_amarela` → `/arboviroses/febre-amarela-humanos-primatas-nao-humanos` (`uses_year=True`, `kind=events`)
* `sg_2020..sg_2024` → `/vigilancia-e-meio-ambiente/notificacoes-de-sindrome-gripal-leve-YYYY` (`kind=events`)
* `srag_2019_2026` → `/vigilancia-e-meio-ambiente/srag-2019-2026` (`kind=events`)
* `macrorregiao_municipio` → `/macrorregiao-e-regiao-de-saude/municipio` (`kind=dim`)
* `cnes_estabelecimentos` → `/v1/cnes/estabelecimentos` (`kind=raw_only`, tenta fallback sem `/v1/`)

---

## Client: timeouts, retries e deadline hard

Arquivo: `app/collectors/demas/client.py`

**Características:**

* Timeout “cirúrgico” para evitar ficar preso
* `trust_env=False` (ignora HTTP(S)_PROXY do Windows/corp)
* Retries leves (3 tentativas)
* Fail-fast em `502/503/504`
* Paginação `limit + offset`
* `hard_deadline_seconds` por endpoint/dataset

**Funções relevantes:**

* `ping()` chama endpoint leve `/macrorregiao-e-regiao-de-saude/municipio?limit=1&offset=0`
* `iter_items()` itera páginas e extrai lista via chaves:
  `("parametros", "items", "data", "results", "macrorregiao_regiao_saude_municipios")`

---

## Collector

Arquivo: `app/collectors/demas/collector.py`

Wrapper que chama o client e retorna lista:

* `collect_all(path, params)` → `list[dict]`

---

## Normalizer

Arquivo: `app/normalizers/demas/normalizer.py`

Normaliza `RAW` para evento genérico:

* `event_date` tenta: `dt_notific`, `dt_sin_pri`, `dt_invest`, `dt_digita`, `data`, `dt_obito` (fallback `date.today()`)
* `epiweek` suporta `AAAASS` (ex: `202605`) ou semana simples
* `year` prioriza `nu_ano/ano/year`, senão deriva de epiweek, senão de `event_date`
* `uf` normaliza upper/trim
* `municipio_ibge` mantém só dígitos
* `municipio_nome` tenta chaves comuns
* `fingerprint = hash(dataset + payload)`

Retorno padrão:

```json
{
  "dataset": "...",
  "event_date": "...",
  "year": 2026,
  "epiweek": 5,
  "uf": "RJ",
  "municipio_ibge": "3304557",
  "municipio_nome": "RIO DE JANEIRO",
  "fingerprint": "...",
  "payload": { ... }
}
```

---

## Sync Service (RAW, EVENTS, DIM)

Arquivo: `app/services/demas_service.py`

### Objetivos

* Coletar e salvar RAW em lotes (rápido)
* Normalizar em chunks e salvar EVENTS (tolerante a falhas item-a-item)
* Upsert da dimensão de municípios (semanal)
* Consultas paginadas de RAW e EVENTS

### RAW

* `sync_dataset_raw(ds)` salva em `DemasRaw` com:

  * `ON CONFLICT DO NOTHING` na constraint `uq_demas_raw_endpoint_hash`
  * Contagem precisa via `RETURNING`

### EVENTS

* `normalize_dataset_events(ds)`:

  * lê RAW por chunks (por id crescente)
  * normaliza item-a-item (conta `failed`)
  * insere com `ON CONFLICT DO NOTHING` na constraint `uq_demas_events_dataset_fp`

### DIM (municípios)

* `sync_municipios_dim()` faz upsert em `DemasMunicipioDim` usando:

  * `ON CONFLICT DO UPDATE` (index: `municipio_ibge`)

### Circuit breaker

* `sync_all_daily()`:

  * chama `client.ping()` antes
  * se ping falhar: retorna rápido com “DEMAS_DOWN”
  * por dataset, aplica `asyncio.wait_for(..., dataset_deadline_seconds)`

### Consultas

* `query_raw(dataset, year, page, size)`
* `query_events(dataset, date_from, date_to, uf, municipio_ibge, page, size)`

---

## Import Service (CSV/ZIP/URL/S3)

Arquivo: `app/services/demas_import_service.py`

Suporta 3 modos:

1. **Local/Upload**: `import_csv_or_zip()`
2. **URL**: `import_from_url()`
3. **Bulk de fontes**: `import_bulk_from_sources(sources: list[DemasSource])`

### Detalhes importantes

* Detecta encoding: `utf-8-sig`, `utf-8`, `latin-1`
* Detecta delimitador com `csv.Sniffer` (`; , | \t`)
* Importa RAW em chunks
* Normaliza EVENTS opcionalmente (`normalize_events=True`)
* Se bulk insert quebrar: cai em modo debug para achar linha ruim usando `save_raw_debug_find_bad_row_on_conflict`

---

## db_bulk: bulk insert + debug row ruim

Arquivo: `app/db_bulk.py`

* `bulk_insert_on_conflict_do_nothing_chunked(...)`
* `bulk_insert_on_conflict_do_nothing_chunked_returning_count(...)`
* `save_raw_debug_find_bad_row_on_conflict(...)`

Destaque:

* No asyncpg, após erro a transação fica “abortada”, então o helper faz `await session.rollback()` antes de seguir para 1-a-1.

---

## Routers /demas

Arquivo: `app/routers/demas.py`
Prefix: `/demas`

### `GET /demas/health?external=false|true`

* `external=false`: status local
* `external=true`: ping real no DEMAS (pode falhar rápido)

### `GET /demas/datasets`

Lista datasets (key/path/uses_year/kind)

### `GET /demas/stats`

Totais do banco (raw/events/dim)

### `POST /demas/sync/daily`

Sync diário (circuit breaker + deadline por dataset)

### `POST /demas/sync/weekly-municipios`

Sync semanal da dimensão de municípios

### `POST /demas/sync/dataset/{dataset_key}`

Sync de um dataset específico

### Consulta Postgres

#### `GET /demas/raw/{dataset_key}`

Query params:

* `year` (opcional para arboviroses)
* `page` (default 0)
* `size` (default 50, max 200)

#### `GET /demas/events/{dataset_key}`

Query params:

* `date_from` (YYYY-MM-DD)
* `date_to` (YYYY-MM-DD)
* `uf` (ex: RJ)
* `municipio_ibge` (ex: 3304557)
* `page`, `size`

---

## Fluxos recomendados

### 1) Verificar saúde do DEMAS (rápido)

```http
GET http://localhost:8080/demas/health?external=true
```

### 2) Rodar sync diário

```http
POST http://localhost:8080/demas/sync/daily
```

### 3) Rodar sync semanal de municípios

```http
POST http://localhost:8080/demas/sync/weekly-municipios
```

### 4) Sync de um dataset específico

```http
POST http://localhost:8080/demas/sync/dataset/arboviroses_dengue
```

### 5) Consultar RAW persistido

```http
GET http://localhost:8080/demas/raw/arboviroses_dengue?year=2026&page=0&size=50
```

### 6) Consultar EVENTS normalizados

```http
GET http://localhost:8080/demas/events/arboviroses_dengue?uf=RJ&municipio_ibge=3304557&date_from=2026-01-01&date_to=2026-02-28&page=0&size=50
```

### 7) Import por URL (quando DEMAS estiver ruim)

> Se houver rota exposta para isso (você já usou um exemplo antes), use:

```http
POST http://localhost:8080/demas/import/from-url/arboviroses_dengue?url=https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR26.csv.zip&request_year=2026&normalize_events=true
```

---

# Postman (copiar/colar)

## Requests básicos

### Health

* GET `http://localhost:8080/health`

### Epidemiologia

* GET `http://localhost:8080/epidemiologia/boletins`
* GET `http://localhost:8080/epidemiologia/casos?disease=dengue&geo_code=3304557`
* GET `http://localhost:8080/epidemiologia/indicadores?disease=dengue&geo_code=3304557`
* GET `http://localhost:8080/epidemiologia/alertas`

## DEMAS

### Health (sem upstream)

* GET `http://localhost:8080/demas/health`

### Health (com upstream)

* GET `http://localhost:8080/demas/health?external=true`

### Datasets

* GET `http://localhost:8080/demas/datasets`

### Stats

* GET `http://localhost:8080/demas/stats`

### Sync daily

* POST `http://localhost:8080/demas/sync/daily`

### Sync weekly municipios

* POST `http://localhost:8080/demas/sync/weekly-municipios`

### Sync dataset

* POST `http://localhost:8080/demas/sync/dataset/arboviroses_dengue`

### Query RAW

* GET `http://localhost:8080/demas/raw/arboviroses_dengue?year=2026&page=0&size=50`

### Query EVENTS

* GET `http://localhost:8080/demas/events/arboviroses_dengue?uf=RJ&municipio_ibge=3304557&page=0&size=50`

---

# Troubleshooting

## DEMAS lento / instável (502/503/504)

* Isso é esperado em janelas de instabilidade do gateway.
* O client é **fail-fast**: não vai ficar “pendurado” por muito tempo.
* Use fallback por CSV/ZIP via URL (S3) quando necessário.

## Sync não gera events

* Você pode ter importado apenas RAW.
* Rode `POST /demas/sync/dataset/{dataset}` para normalizar (kind=events), ou use `normalize_events=true` no import.

## Bulk insert falha “do nada”

* `DemasImportService` tem fallback para identificar a row ruim (`save_raw_debug_find_bad_row_on_conflict`).
* O erro levantado inclui a row problemática para correção.

---

## Anexo: setup original (o que você mandou no começo)

### Subir Postgres

`docker compose up -d`

### Criar venv e instalar

`poetry install`

### Config

`cp .env.example .env`

### Rodar migrations

`alembic revision --autogenerate -m "init"`
`alembic upgrade head`

### Subir API

`poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload`

### Testar

* `GET http://localhost:8080/health`
* `GET http://localhost:8080/epidemiologia/boletins`
* `GET http://localhost:8080/epidemiologia/casos?disease=dengue&geo_code=3304557`
* `GET http://localhost:8080/epidemiologia/indicadores?disease=dengue&geo_code=3304557`
* `GET http://localhost:8080/epidemiologia/alertas`

---