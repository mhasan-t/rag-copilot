---
title: Payments latency spike
doc_type: runbook
service_tags: [payments]
---
# Payments latency spike

Use this when p99 latency of the payments service is above its normal range, or when users report slow or
failing checkouts.

## Normal behaviour

- p99 latency of `POST /payments` is below **300 ms** (usually ~100 ms).
- 5xx error ratio is below **1%**. A small number of "card network declined request" errors is normal.
- Traffic is steady; a latency spike with unchanged request rate points at the service itself, not at load.

## Diagnose

### 1. Confirm the spike

Check p99 latency and error ratio for the last 30 minutes. Note when the spike started.

### 2. Check recent deployments

Compare the start of the spike with the deployment history. A deployment within **15 minutes before** the spike
is the most likely cause; most payments latency incidents have been bad releases.

### 3. Read error logs

Look for these messages:

- `connection pool exhausted` or `ledger-db query timed out`: the service is waiting on database connections.
  See the "Database connection pool exhaustion" runbook.
- `card network declined request: issuer unavailable`: an upstream card network problem. See the
  "Card network declines" runbook; rolling back will not help.

### 4. Look at slow traces

Slow traces on `POST /payments` with normal traces on `GET /payments/{id}` mean the write path is affected,
which is where ledger queries happen.

## Remediate

- **Spike started after a deployment:** roll back to the previous version. This is a high-risk action and needs
  approval from a superuser. Rolling back is safe for payments: releases are backwards compatible with the
  database schema.
- **No recent deployment, pool exhausted:** restart the deployment to clear stuck connections, then escalate to the
  payments on-call engineer.
- **Card network errors only:** do not roll back or restart. Monitor and inform support.

## Verify

The fix worked when, within **5 minutes**, p99 latency is back below **300 ms** and the error ratio is below **1%**.
If not, escalate to the payments on-call engineer.
