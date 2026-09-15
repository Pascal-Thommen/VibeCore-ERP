# ADR 0001: Isolated Deployment per Customer

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

VibeShell workflows are deliberately client-specific. Combining unrelated
customers in one database increases the risk of cross-customer access and makes
backup, restore, and custom deployment operations harder to reason about.

## Decision

Each customer receives a dedicated Docker Compose deployment and a dedicated
PostgreSQL database. A database belongs to exactly one customer and contains:

- `core` — protected financial truth
- `shell` — client-specific operational workspace

The deployment may run on the customer's local Ubuntu server. No service may
read data from another customer's database. The database is backed up and
restored as one customer-owned unit.

## Consequences

- Stronger isolation and simpler disaster recovery.
- Client-specific Shell changes have no cross-customer blast radius.
- Central fleet management, if later needed, operates deployments rather than
  joining customer data into a shared transactional database.
