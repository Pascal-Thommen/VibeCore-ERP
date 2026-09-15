# ADR 0008: Mature-Library Implementation Policy

**Status:** ACCEPTED
**Date:** 2026-09-14

## Context

Financial and fiscal systems must not acquire hidden risk by reimplementing
well-understood infrastructure.

## Decision

The Finance Core uses FastAPI, SQLAlchemy, Pydantic, and Alembic as its approved
application, persistence, validation, and migration foundation. Adapter teams use
maintained protocol and format libraries appropriate to their integration, such
as Zeep for SOAP and established XML and cryptography libraries.

Custom implementations of cryptography, hashing algorithms, XML signatures,
HTTP/TLS transport, JWT primitives, or protocol encoders are forbidden. Choose a
mature maintained library and wrap it only behind a small domain-facing boundary
when needed.

## Consequences

- The team concentrates custom code on accounting and client workflow value.
- Dependency versions, security updates, and license suitability become explicit
  engineering responsibilities.
