# ADR 0004: Authentication, Secrets, and Service Trust

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

The Shell, Core, and external adapters need clear trust boundaries without
introducing enterprise infrastructure that a local customer deployment cannot
operate reliably.

## Decision

The local VibeCore service is the JWT issuer and the VibeShell is the JWT
audience. Access tokens expire after one hour; refresh tokens expire after seven
days. The initial Core roles are `ADMIN`, `ACCOUNTANT`, and `SYSTEM_AGENT`.

The authentication model must allow a future Shell-managed PIN login flow for
factory workers without relaxing Core authorization or approval checks.

Adapters authenticate as services using static asymmetric keys. Webhooks are
signed with HMAC and verified before processing. Payload signatures do not replace
idempotency checks.

Development may load non-production values from an ignored local environment
file. Production private keys, database passwords, API tokens, and encryption
material use Docker Secrets or protected, root-readable mounted secret files.
An external secret manager is deferred until operational scale justifies it.

## Consequences

- Production secret material is not exposed through ordinary container
  environment inspection.
- The Core can distinguish user actions from trusted adapter and system actions.
- Key rotation must be documented by each adapter before production use.
