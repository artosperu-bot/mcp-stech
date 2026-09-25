# HERMES ↔ STECH MCP — Marketing Contract V1

This integration keeps responsibilities separated:

- **HERMES** plans and delegates.
- **STECH MCP** supplies product truth and approved media references.
- **Creative agents** generate image/video assets.
- **STECH_META** owns Meta API reads/writes under its existing safeguards.

## Read-only tools

### `marketing_product_context(partnumber)`

Returns identity, technical facts, image readiness, evidence conflicts and the
latest operational product snapshot. Distributor/source prices remain labeled as
source evidence and are **not** treated as the approved STECH selling price.

### `marketing_readiness(partnumber)`

Returns `READY`, `REVIEW` or `BLOCKED` for creative generation. Publication
is always false in V1 because publishing belongs to the Meta/commerce control
plane.

### `marketing_media_manifest(partnumber)`

Returns exact/approved image references plus the `PRESERVE_PRODUCT_IDENTITY`
PRODUCT_LOCK policy.

## Safety boundary

V1 cannot:

- publish to Facebook or Instagram;
- create/activate Meta campaigns;
- change stock;
- change selling price;
- modify VTEX/channel publication state.

A paid-media workflow must obtain the approved STECH selling price from the
future pricing/commerce authority before creating a production advertisement.

## Recommended HERMES sequence

1. `marketing_product_context`
2. `marketing_readiness`
3. If allowed, `marketing_media_manifest`
4. Creative generation / review
5. Human approval
6. STECH_META preview
7. Explicitly authorized Meta execution
