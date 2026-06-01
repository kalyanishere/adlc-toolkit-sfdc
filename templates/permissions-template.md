---
id: PERMS-<REQ-id>
title: "Permissions for <feature name>"
req: REQ-<id>
status: draft                       # draft | approved | deployed
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
app_prefix: <AppPrefix>              # from .adlc/config.yml salesforce.app_prefix
---

# Permissions — REQ-<id> <feature title>

Required by `salesforce-rules.md`: every feature that touches metadata generates one or more permission sets, with explicit dependency mapping and an assignment matrix.

## Permission sets generated

One row per new permission set. Naming format: `[AppPrefix]_[Component]_[AccessLevel]` where `AccessLevel` ∈ {Read, Write, Full, Execute, Admin}. Per the rules: **no permission set grants more than 10 different object permissions**, and read+delete combinations must be split into separate sets.

| Name | Object/Apex/Flow | Access level | Why this set exists |
|---|---|---|---|
| `<AppPrefix>_<Component>_Read`    | <object/Apex class/flow> | Read    | <one-line purpose> |
| `<AppPrefix>_<Component>_Execute` | <Apex class>             | Execute | <one-line purpose> |

## Permission set group(s)

Create a group when the feature has 3+ related permission sets, users need a combined bundle of permissions, OR a clear user persona exists.

| Group name | Includes | Persona |
|---|---|---|
| `<AppPrefix>_<Component>_PSG` | `<AppPrefix>_<Component>_Read`, `<AppPrefix>_<Component>_Execute` | <persona> |

If no group is needed (fewer than 3 sets and no persona-shaped bundle), state that explicitly: `No permission set group needed for this feature — N permission sets, no persona bundle.`

## Dependency mapping

Which permission set unlocks which Apex class / object / field / flow / Agent / Data Cloud surface. List every cross-reference so a deploy that strips one knows what else breaks.

| Permission set | Grants access to | Notes |
|---|---|---|
| `<AppPrefix>_<Component>_Read` | <SObject>: Read on fields A/B/C; SObject Y: Read | FLS configured per-field, never object-blanket |
| `<AppPrefix>_<Component>_Execute` | Apex `<ClassName>` (apexClassAccesses); flow `<FlowName>` | Class is `with sharing`, AccessLevel = USER_MODE |

## Assignment matrix

Which user roles / personas / scratch-org users get which sets/groups in each environment.

| Persona | Sandbox | Staging | Production |
|---|---|---|---|
| <Persona A> | `<AppPrefix>_<Component>_PSG` | `<AppPrefix>_<Component>_PSG` | `<AppPrefix>_<Component>_PSG` |
| <Persona B> | (manual)                       | (manual)                       | (manual) |

Document who is responsible for assignment in production (admin runbook, automated post-deploy script, sf CLI `sf org assign permset` invocation, etc.).

## Anti-patterns this avoids

Verify each before sign-off:

- [ ] No `View All Data` or `Modify All Data` granted in any permission set
- [ ] Object-level access is split per field where possible (FLS-first)
- [ ] No permission set grants Read AND Delete on the same object
- [ ] No permission set lists more than 10 object permissions
- [ ] Sensitive data (PII, payment, audit-log) sits in a dedicated set, not bundled with general feature access

## Notes

Free-form notes from the implementer / reviewer: rationale for splits, deferred work, follow-up REQs.
