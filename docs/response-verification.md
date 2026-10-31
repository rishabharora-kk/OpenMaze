# Experimental response envelope v1

This is an application-specific local demonstration, **not RFC 9421 compliance**.
Algorithm is fixed to Ed25519; there is no algorithm negotiation. The pinned key
comes from trusted local initialization, never from the response being verified.

The protected response is JSON with exactly two fields: `receipt`, `signature`.
The receipt contains exactly:

| Field | Value / interpretation |
|---|---|
| profile | `openmaze-envelope-v1` |
| audience | `openmaze-local-demo` (fixed local audience) |
| kid | `demo-ed25519-v1` (only one pinned development key) |
| method | Exact `GET` request method |
| target | Exact path; query strings are unsupported |
| nonce | Client-generated 16 random bytes encoded as 32 lowercase hex characters |
| status | HTTP response status integer |
| issued | Unix seconds integer |
| expires | Unix seconds integer; issuance + 60 seconds |
| payload | Standard padded base64 of exact application JSON bytes |

The signed bytes are the domain separator `OpenMaze response envelope v1` plus a
NUL byte followed by the encoded receipt. Encoding uses Python JSON with sorted
keys, compact separators, ASCII escaping, and non-finite values disabled. Receipt
metadata uses only strings and integers; no floating-point values are allowed in
timestamps/status. Payload is signed as base64 bytes, not reserialized during
verification. The signature is padded base64 of the 64-byte Ed25519 result.
Duplicate JSON field names are rejected. Additional/missing envelope or receipt
fields fail verification. The algorithm and domain separator are code-defined,
not attacker-supplied fields.

The verifier checks:

1. Response size at most 8 KiB and exact envelope/receipt schema.
2. Pinned profile, audience and key ID.
3. Exact outstanding method/path/nonce and actual HTTP status.
4. Integer time metadata; positive lifetime at most 60 seconds; issuance not over
   30 seconds ahead, expiry not over 30 seconds behind local clock.
5. Ed25519 signature over the complete receipt.
6. Payload decoding and minimum object schema, then atomic nonce consumption.

At most 128 requests remain pending. Entries expire after 90 local seconds.
Concurrent replay accepts at most one response. Verification failure does not
consume the nonce; local expiry still bounds it. The consumer must apply its own
domain/schema correctness checks to the verified object.

Freshness is per pending client request, not a global server replay ledger.
Reissuing the same GET nonce to the service is not prohibited. This profile must
not be extended to side-effecting operations without authenticated request replay
prevention and idempotency design. Client restarts lose pending state; they create
new unpredictable nonces and cannot validate old outstanding responses.

The prototype does not bind dynamic authority/Host, proxy transformations,
compression, content negotiation or arbitrary headers. It has one fixed audience
and per-initialization pinned key. Those restrictions are intentional. It cannot
be presented as a general HTTP signature scheme or transparently placed in front
of an existing API.

TLS is absent from this local demo; do not expose it remotely. A production design
needs TLS, authenticated key provisioning, rotation/revocation, clock policy,
upstream validation and a reviewed protocol implementation. A compromised signer
can authenticate false data. A public verification key permits distinguishing
genuine receipts from decoy responses; that is acceptable.

References: [RFC 9421 (February 2024)](https://www.rfc-editor.org/rfc/rfc9421.html),
[RFC 9530 (February 2024)](https://www.rfc-editor.org/rfc/rfc9530.html).
