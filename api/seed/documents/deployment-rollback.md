---
title: Rolling back a deployment
doc_type: runbook
service_tags: []
---
# Rolling back a deployment

Applies to every service.

## When to roll back

Roll back when a service got worse (latency, errors) shortly after a deployment and nothing else changed.
Rolling back is faster and safer than debugging a fix forward during an incident.

## How

1. Get approval: rollbacks are high-risk actions and must be approved by a superuser.
2. Roll back to the previous revision. The rollback is recorded as a new revision in the deployment history.
3. Keep watching the service's main metrics for 5 minutes.

## Verify

The rollback worked when the metrics that degraded are back to their normal range from the service's runbook. If
they are not back to normal within 5 minutes, the deployment was probably not the cause: escalate.
