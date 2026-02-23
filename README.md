## Epi Clipping API

### Subir Postgres
docker compose up -d

### Criar venv e instalar
poetry install

### Config
cp .env.example .env

### Rodar migrations
alembic revision --autogenerate -m "init"
alembic upgrade head

### Subir API
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

### Testar
GET http://localhost:8080/health
GET http://localhost:8080/epidemiologia/boletins
GET http://localhost:8080/epidemiologia/casos?disease=dengue&geo_code=3304557
GET http://localhost:8080/epidemiologia/indicadores?disease=dengue&geo_code=3304557
GET http://localhost:8080/epidemiologia/alertas
