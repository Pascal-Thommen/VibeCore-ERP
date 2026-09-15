# Adapter Schema Template

Copy this file into `<adapter>/.ai/adapter_schema.md` and replace every
placeholder before an adapter is integrated.

## Adapter identity

- **Name:** `<adapter-name>`
- **Version:** `<semantic-version>`
- **Owner:** `<team-or-contact>`
- **OpenAPI:** `openapi.json`

## Core contract

- **Inbound endpoints/events:** `<list the Core-to-Adapter operations>`
- **Outbound endpoints/events:** `<list the Adapter-to-Core operations>`
- **Authentication:** `<asymmetric client authentication / signed webhook>`
- **Idempotency key:** `<header or field>`
- **Correlation ID:** `<header or field>`
- **Retry and recovery:** `<policy; polling is recovery only>`

## Payload evolution

All JSON payloads must accept optional `meta` and `custom_data` objects. Document
versioning, required fields, error codes, and backward-compatibility guarantees.

## Security boundary

This adapter has no direct PostgreSQL access. List the secrets it needs, their
injection mechanism, and the key-rotation procedure. Never put secret values in
this document.
