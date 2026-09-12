# Post-verification external archive receipt verification

After `build_extraction_postverification_external_handoff.py` produces the repository-side replay package, the
next evidence event must happen outside the repository: an independently controlled custodian preserves the exact
handoff/object set and supplies a receipt or equivalent record.

The repository does **not** provide a command that generates that external receipt. It only provides
`verify_extraction_postverification_external_archive_receipt.py` to test whether a receipt supplied from the
external channel is structurally and cryptographically/identity-wise bound to the repository handoff identities
that software can check.

## Receipt contract

The external receipt JSON has a strict schema containing:

- the exact SHA-256 of the post-verification handoff file;
- the stable `archive_object_set_sha256` committed by that handoff;
- the frozen source commit SHA;
- the exact SHA-256 of `verification/bound-cold-verification.json` inside the object set;
- custodian identity, archive channel identity, and archive record id;
- an external UTC timestamp and/or external sequence position;
- `production_authorized=false`.

The receipt is an input from the external custodian. Repository operators must not synthesize it merely to make a
verification command pass.

## Independently selected verification context

Verify the receipt using expectations selected independently from the receipt itself:

```bash
python scripts/verify_extraction_postverification_external_archive_receipt.py \
  --receipt external/postverification-archive-receipt.json \
  --handoff external/postverification-bound-release-handoff.json \
  --expected-handoff-sha256 '<independently-recorded-handoff-sha256>' \
  --expected-source-commit-sha d6ffdf7debd63281e0db5934e3d4b7ebafb98311 \
  --expected-custodian-identity '<independently-expected-custodian>' \
  --expected-archive-channel-identity '<independently-expected-channel>' \
  --expected-archive-record-id '<independently-expected-record-id>' \
  --output external/verified-postverification-archive-receipt-binding.json
```

Do not copy expected custodian/channel/record values from the receipt just before invoking the verifier. A match
against values copied from the same untrusted receipt would only prove self-consistency.

## What the verifier reconstructs

The verifier checks the exact handoff bytes against the independently expected SHA-256 and requires the handoff to
remain in the repository-side `awaiting_independent_archive` state. It then independently reconstructs the stable
archive object-set digest from every `archive_name`, exact object SHA-256, and object size in `archive_objects`.
It does not trust the handoff's stored `archive_object_set_sha256` without reconstruction.

The verifier also requires the object set to contain `verification/bound-cold-verification.json` and requires that
object's exact SHA-256 to equal the handoff's `bound_verification.file_sha256` witness. Only then does it compare
the externally supplied receipt with the independently selected handoff/source/custodian/channel/record context.

This verifies a binding. It does not download or interrogate the custodian's archive service, and therefore does
not by itself prove that every claimed archived object is actually retrievable from that external service.

## Authority boundary

A successful verified binding intentionally keeps:

- `independent_control_established=false`;
- `historical_channel_semantics_established=false`;
- `production_authorized=false`.

Those fields stay false because identity strings, timestamps, record ids, and a structurally matching receipt do
not prove who truly controlled the archive channel or what its institutional retention semantics were. Those are
external governance facts requiring independently reviewable evidence.

The receipt also does not retroactively expand the original external Ed25519 provenance signature. The release
sidecars remain part of the later post-verification archive event, not part of the historical scope of that earlier
signature.

Issue #26 remains open until genuine external evidence supports the required reviewer/adjudicator independence,
historical custody and untouched TEST claims, independently controlled expected run context, any claimed
institutional ownership, and the complete cold-verifiable evidence package.
