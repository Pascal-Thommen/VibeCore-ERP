# Infrastructure

The deployment baseline will provide one Docker Compose stack per customer with:

- PostgreSQL 16 or newer
- automated volume-aware backups using `pg_dump`
- encrypted off-machine backup storage
- structured JSON logging
- health checks and documented restore procedures

Production credentials use Docker Secrets or protected mounted secret files.
