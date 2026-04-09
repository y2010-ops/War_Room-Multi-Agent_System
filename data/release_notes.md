# Release Notes — Feature: "Smart Dashboard 2.0"

**Version:** 4.7.0
**Launch Date:** Day 8 of observation window
**Owner:** Product — Smart Dashboard squad

## What changed
- Rebuilt the home dashboard with a new component library (PurpleUI v2).
- Introduced an in-line analytics panel powered by a new aggregation service (`agg-svc`).
- Added a redesigned checkout flow integrated with the new payments client SDK (v3.2.0).
- Migrated session storage from local cache to a centralized Redis cluster.

## Known risks at launch
1. **`agg-svc` is new** — first time serving production traffic at full DAU.
2. **Payments SDK v3.2.0** — released two weeks before launch, no full load test against peak traffic.
3. **Redis session cluster** — newly provisioned, capacity headroom not fully validated.
4. **Older Android (<= 12) devices** — limited QA coverage; UI library v2 has known rendering quirks.

## Rollback plan
- Feature flag `smart_dashboard_v2` can be disabled per-region within ~5 minutes.
- Payments SDK can be pinned back to v3.1.4 via remote config.
- Redis session migration can fall back to local cache via `session_store=local`.
