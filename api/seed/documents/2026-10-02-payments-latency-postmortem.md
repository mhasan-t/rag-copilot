---
title: "Postmortem: payments latency after release"
doc_type: postmortem
service_tags: [payments]
---
# Postmortem: payments latency after release

## Summary

For 35 minutes, p99 latency of the payments service rose from ~100 ms to over 2 s and 5xx errors reached 6%.

## Cause

The release added a ledger lookup on every payment. Each lookup held a database connection for the length of a
slow query, exhausting the 10-connection pool under normal load. Logs showed
`ledger-db query timed out: connection pool exhausted (size=10)`.

## Resolution

Rolled back to the previous version. Latency was normal within 3 minutes.

## Lessons

- Check deployment history first when payments latency spikes; it found the cause in minutes.
- Load-test releases that add queries to the payment path.
