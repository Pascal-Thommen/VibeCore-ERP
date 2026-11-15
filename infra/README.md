# Infrastructure

The deployment baseline will provide one Docker Compose stack per customer with:

- PostgreSQL 16 or newer
- automated volume-aware backups using `pg_dump`
- encrypted off-machine backup storage
- structured JSON logging
- health checks and documented restore procedures

Production credentials use Docker Secrets or protected mounted secret files.

## Available Stacks

- **Dolibarr ERP (Oro Ku'i / UPA Extension)**: [`infra/dolibarr/docker-compose.yml`](dolibarr/docker-compose.yml) (see [`infra/dolibarr/README.md`](dolibarr/README.md) for endpoints, credentials, persistent volumes, and enabled modules).

