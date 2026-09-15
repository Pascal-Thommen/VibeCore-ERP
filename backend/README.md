# VibeCore ERP Backend

The backend is the Python/FastAPI application boundary for the protected Finance
Core and the client-specific Shell. Read [`../.ai/ARCHITECTURE.md`](../.ai/ARCHITECTURE.md)
and the applicable ADRs before changing it.

## What this scaffold provides

- FastAPI application with `/api/v1/health` and database-backed `/api/v1/ready`
- SQLAlchemy 2.x synchronous session boundary using PostgreSQL and `psycopg`
- Pydantic Settings configuration, including file-based Docker Secrets
- Alembic migration environment
- Deterministic PostgreSQL migrations for the `core` and `shell` schemas
- Docker Compose services for PostgreSQL 16, migration execution, and the API

The first Core business migration provides partners, chart of accounts, IVA
definitions, products, document headers, and document items.

## Local startup

Docker Secrets are required by the Compose setup and are deliberately ignored by
Git. Create a local development secret before starting the stack:

```bash
mkdir -p .secrets
openssl rand -base64 32 > .secrets/postgres_password
chmod 600 .secrets/postgres_password
docker compose up --build
```

The migration container creates `core` and `shell` before the API starts. Then:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
```

For a local Python environment, copy `.env.example` to `.env`, provide either
`DATABASE_URL` or `DATABASE_PASSWORD`, and run `alembic upgrade head`.

## Layout

```text
backend/
├── app/
│   ├── api/                 # HTTP boundary
│   ├── core/                # Configuration and shared financial primitives
│   └── db/                  # SQLAlchemy base and session boundary
├── core/                    # Future protected financial-domain modules
├── shell/                   # Future client-specific Shell-domain modules
├── migrations/              # Alembic environment and revisions
├── tests/                   # Backend tests
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```
