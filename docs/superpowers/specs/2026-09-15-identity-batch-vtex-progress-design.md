# Identity Batch Research + Safe VTEX EAN Sync Design

## Goal

Process selected products in persistent Product Work jobs so identity research stays fast and parallel, while EAN/UPC writes to VTEX are serialized, safe, observable, and resumable.

## User Flow

1. SCR sends the selected Part Numbers as one or more `RESEARCH_IDENTITY` jobs with `VTEX_EAN_SYNC` requested.
2. Existing internal MCP workers research different products in parallel.
3. Each product reaches one identity decision: verified/promoted, candidate only, conflict/review, or no verified identity.
4. Only verified/promoted identity reaches the VTEX post-action.
5. VTEX EAN sync is globally serialized inside the MCP process: only one identity item may execute the VTEX EAN read/write/readback section at a time.
6. Every item persists a structured final `result_json`. `product_work_job_get` returns that result with the normal status/progress fields so SCR can render a live modal and resume it after reload.

## Zero-Cost Discovery Constraint

EAN/UPC research must not require Brave, SerpAPI, paid Bing API, Google paid search, or any other per-query paid service. The existing free Bing HTML provider remains URL discovery only. Search-result snippets are never barcode evidence.

## Identity Trust Rule B

A barcode is eligible for automatic promotion only when all universal checks pass:

- exact Part Number evidence;
- valid GTIN checksum;
- no conflict with an existing protected/manual identity;
- no conflicting strong evidence for another barcode.

Then one of these trust paths must be satisfied:

### Path 1 — Primary source

At least one exact-PN candidate from `MANUFACTURER` or `OFFICIAL_DOCUMENT` with confidence `A1` or `A2`.

### Path 2 — Strong consensus

At least two independent strong sources agree on the same canonical GTIN, with:

- at least one `AUTHORIZED_DISTRIBUTOR` candidate (`Deltron`, `Ingram`, `Intcomex` domain policy);
- all participating promotion evidence exact-PN;
- confidence in `A1`, `A2`, or `B`;
- independent source hosts.

Two retailers, two marketplaces, or retailer + marketplace never satisfy automatic promotion by themselves. Such evidence may be retained as candidate/review evidence but does not trigger VTEX.

Examples of intended behavior:

- Lenovo PSREF exact PN + valid code -> promote.
- Deltron + Ingram exact PN, same code -> promote.
- Deltron + strong official manufacturer result, same code -> promote.
- Ripley only -> candidate, no VTEX.
- Ripley + Falabella only -> candidate, no VTEX.
- strong sources disagree -> review/conflict, no VTEX.
- no trusted code -> partial/research required, no VTEX.

## Canonical GTIN Comparison

EAN/UPC/GTIN representations are compared through canonical GTIN normalization so equivalent UPC/EAN representations do not create a false conflict. The stored field representation remains compatible with the existing verifier; canonicalization is for decision comparison and VTEX equivalence checks.

## VTEX Safety and Serialization

The existing `VtexEanSyncService` remains create-only:

- resolve SKU by `<PN>-S`;
- verify Product RefId matches the exact PN;
- read current VTEX EAN values;
- equivalent code already present -> `VTEX_EAN_ALREADY_PRESENT`, no POST;
- different non-empty remote EAN -> `VTEX_EAN_CONFLICT`, no write;
- remote empty -> one POST, then GET/readback verification;
- only successful readback -> `VTEX_EAN_SYNCED`.

A process-wide serializer protects the whole VTEX EAN sync operation, not research. Multiple workers may research simultaneously, but only one worker at a time enters the VTEX sync critical section.

## Persistent Result Contract

Add a nullable `result_json NVARCHAR(MAX)` to `dbo.product_work_item` through an additive idempotent migration. Existing rows remain valid.

For identity items the persisted result contains only non-secret operational data, for example:

```json
{
  "partnumber": "83GW005FLD",
  "identity_state": "COMPLETED",
  "identity_result_code": "VERIFICADO",
  "verified_fields": {"upc": "199271965603"},
  "promoted_fields": ["upc"],
  "decision": "PROMOTED",
  "evidence_summary": {"strong_source_count": 2, "has_primary": false, "has_authorized_distributor": true},
  "vtex_state": "VTEX_EAN_SYNCED"
}
```

No credentials, auth headers, page bodies, or tokens are stored in `result_json`.

## Product Work Changes

- Worker transitions remain unchanged.
- Handler returns a `result` payload in addition to status/current step.
- Repository terminal transition persists `result_json` atomically with the final state.
- `get_job()` decodes `result_json` and includes `result` per item.
- Retry/cancel semantics continue to work; a retry replaces the final result only when the next terminal execution finishes.

## Error Handling

- Search/network transient failures remain retryable under existing Product Work retry rules.
- Candidate/no strong evidence is a normal terminal `PARTIAL`, not a crash.
- Trust conflicts are `REVIEW_REQUIRED`.
- VTEX retryable HTTP/network conditions keep the item retryable.
- VTEX permanent conflict/mismatch/forbidden outcomes are reported in the persisted result and never cause a destructive replacement.

## Testing

MCP tests must cover:

1. manufacturer-only exact strong identity promotes;
2. two strong sources with at least one authorized distributor promote;
3. two retailers do not promote;
4. one retailer does not promote;
5. conflicting strong codes do not promote;
6. exact-PN and checksum gates remain mandatory;
7. VTEX sync critical section is serialized across concurrent handler calls;
8. final `result_json` persists and round-trips through `product_work_job_get`;
9. existing VTEX create-only/idempotence tests remain green;
10. full MCP `pytest -q` passes before merge.

## Non-Goals

- No price, stock, category, image, activation, or commercial-field writes.
- No automatic replacement of an existing different VTEX EAN.
- No paid search provider.
- No hard-coded Lenovo barcode catalog; Lenovo examples are test semantics, not production seed data.
