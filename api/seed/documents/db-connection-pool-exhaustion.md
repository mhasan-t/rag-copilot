---
title: Database connection pool exhaustion
doc_type: runbook
service_tags: [payments, ledger]
---
# Database connection pool exhaustion

Symptoms: requests time out waiting for a database connection; logs contain `connection pool exhausted` or
`query timed out`; latency rises sharply while traffic is unchanged.

## Causes

1. **A new release holds connections longer**, for example by adding a query per request or keeping a transaction
   open across a network call. This is the most common cause and starts right after a deployment.
2. **A slow query** after data growth or a missing index.
3. **The database itself is degraded** (high CPU, failover in progress).

## What to do

- If the problem started after a deployment, roll the deployment back. Don't raise the pool size as a fix: it moves
  the bottleneck to the database.
- If there was no deployment, restart the affected deployment to release stuck connections and ask the database
  team to check for slow queries.
