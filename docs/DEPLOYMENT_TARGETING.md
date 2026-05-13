# Deployment Targeting

Contract-Governor v1.3.0 introduces deployment targeting - the ability to control which contracts mount on which pods.

## The Problem

You have the same codebase deployed to multiple pods with different roles:
- `control-plane-api` - serves external API requests
- `control-plane-controller` - runs background jobs, internal operations

Some contracts should only be available on specific pods. For example, admin/controller endpoints shouldn't be exposed on the public API pod.

## The Solution

Two new fields in stipulation config: `mount_on` and `exclude_from`.

## Environment Variable

Set `DEPLOYMENT_ROLE` on each pod to identify its role:

```yaml
# Kubernetes deployment example
env:
  - name: DEPLOYMENT_ROLE
    value: "control-plane-api"
```

## Stipulation Configuration

### Option 1: `mount_on` (whitelist)

Only mount this contract on specific roles:

```yaml
# stipulations/admin/v1.yaml
exposure_policy: global-control-plane
mount_on:
  - control-plane-controller
```

Result: Admin API only mounts on `control-plane-controller` pods.

### Option 2: `exclude_from` (blacklist)

Mount everywhere EXCEPT specific roles:

```yaml
# stipulations/user-catalog/v1.yaml
exposure_policy: tenant-scoped
exclude_from:
  - control-plane-api
```

Result: User catalog mounts on all pods except `control-plane-api`.

### Default Behavior

If neither `mount_on` nor `exclude_from` is set, the contract mounts on all pods (backward compatible).

## Logic

```
if DEPLOYMENT_ROLE is not set:
    mount everything (backward compatible)

if mount_on is set:
    mount only if DEPLOYMENT_ROLE in mount_on

if exclude_from is set:
    mount unless DEPLOYMENT_ROLE in exclude_from

if neither is set:
    mount everywhere
```

## Startup Logs

When deployment targeting is active, you'll see logs like:

```
📋 Step 3.5: Deployment role filtering active
   DEPLOYMENT_ROLE=control-plane-api
   ⏭️ Skipping admin v1 (not for role 'control-plane-api')
   ✓ Exposed hello v1
   ✓ Exposed user-catalog v1
   📋 Skipped 1 contracts for role 'control-plane-api': ['admin:v1']
```

## Performance

Zero runtime cost. Filtering happens once at startup during contract loading.

## Example: Split Control Plane

```yaml
# Pod 1: control-plane-api (external traffic)
DEPLOYMENT_ROLE=control-plane-api

# Pod 2: control-plane-controller (internal jobs)
DEPLOYMENT_ROLE=control-plane-controller
```

Stipulations:

```yaml
# hello/v1.yaml - mounts everywhere (no targeting)
exposure_policy: tenant-scoped

# admin/v1.yaml - controller only
exposure_policy: global-control-plane
mount_on:
  - control-plane-controller

# user-catalog/v1.yaml - not on public API
exposure_policy: tenant-scoped
exclude_from:
  - control-plane-api
```

Result:
- `control-plane-api`: hello
- `control-plane-controller`: hello, admin, user-catalog
