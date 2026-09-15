# ADR 0007: SIFEN Adapter Boundary and Staged Rollout

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

Paraguayan fiscal workflows need SIFEN facts in the Core but should not couple
financial posting to SOAP/XML, certificate management, signing, or transmission.

## Decision

The Core natively stores fiscal facts required for accounting and traceability:
partner RUC, IVA treatment, Timbrado references, document identity, and the
SIFEN lifecycle/result snapshot. The SIFEN adapter is an isolated container that
owns SOAP/XML transformation, validated XML generation, certificate access,
cryptographic signing through established libraries, transmission, and provider
retry behavior.

Implementation proceeds in stages:

1. Mock SIFEN adapter for local contract, event, retry, and idempotency tests.
2. Official SIFEN test-environment integration before any pilot deployment.
3. Production configuration only after compliance review, operational testing,
   certificate procedures, and explicit release approval.

The adapter exposes `openapi.json` and its own `.ai/adapter_schema.md`; it has no
direct PostgreSQL connection.

## Consequences

- The reference workflow can be built and tested without fiscal-network access.
- SIFEN complexity and secrets do not infect the reusable Finance Core.
