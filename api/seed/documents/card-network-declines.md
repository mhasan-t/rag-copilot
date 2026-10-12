---
title: Card network declines
doc_type: runbook
service_tags: [payments]
---
# Card network declines

Errors logged as `card network declined request: issuer unavailable` come from the external card network, not from
our code.

- A background rate below 1% is normal.
- If it rises above 1% while latency stays normal, the card network is having an outage. Check the provider's
  status page and inform support.
- Rolling back or restarting the payments service does **not** help and should not be done for this.
