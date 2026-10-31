# Architecture decisions

## Scope of v0.1

One local synthetic inventory API, two tenants, three records per tenant. GET is
the only method. Exact resources:

```text
/v1/tenants/alpha/records
/v1/tenants/alpha/records/item-1
/v1/tenants/alpha/records/item-2
/v1/tenants/alpha/records/item-3
```

Equivalent beta resources require beta credentials. Query parameters and path
aliases are rejected; unknown authorized paths return 404. Valid but insufficient
credentials return explicit 403. An absent Authorization header is eligible for
the opt-in decoy; an invalid or empty Authorization header returns 401.

## Processes and trust

`Gateway` checks policy before forwarding an allowlisted request. It rebuilds
headers, forwards the original bearer token and nonce, and never forwards
caller-controlled tenant, forwarding, routing, or internal-identity headers.
`Protected` validates the credential and exact tenant again, checks nonce shape,
then reads and signs its synthetic records. `Decoy` receives only method/path.

The protected service can be called directly by a local credential holder in TCP
mode. It is not an authorization bypass: it independently checks policy. The
gateway's rate limit can be bypassed by such local peers, hence TCP mode is for
local experiments only. Container mode uses separate filesystem mounts and Unix
sockets; independent backend authorization remains necessary there.

There is no route from a decoy continuation into the protected API. The graph
contains no hidden real-data path. Source disclosure and decoy fingerprinting do
not change policy decisions. A valid signature intentionally distinguishes a
protected response from a decoy.

## Bounded world

An entry allocates a random session ID and absolute expiry. Each continuation
contains session ID, node, expiry, and HMAC-SHA256 authentication under a
deployment-specific decoy seed. Synthetic records are derived consistently from
the seed/session/node. Three child nodes are derived without a database. The
finite node space can cycle; infinite traversal is neither implemented nor claimed.

The session table is necessary: stateless continuation tokens alone cannot
enforce a total request budget against replay. A lock atomically increments each
session's response count. Reusing a continuation consumes another response; child
branches share the same 20-response budget. At most 1,000 live sessions exist;
new sessions are denied at capacity until expiry. Identity rotation does not
bypass the process-wide token bucket. Restart discards all session accounting;
old tokens become unusable because their session is absent.

## Implemented application limits

| Boundary | Limit |
|---|---|
| HTTP headers | 8 KiB total, 32 fields, 2 KiB request line |
| Header read | 2-second absolute deadline, 0.5-second inactivity timeout |
| Request target | 1,024 characters, restricted ASCII syntax |
| Bodies / methods | No bodies; GET only; close after one request |
| Each listener | 16 active workers, listen backlog 32 |
| Each response | 8 KiB |
| Internal transport | 250 ms socket operation timeout |
| Uncredentialed gateway admission | 50/sec, burst 100 |
| Credentialed gateway admission | 100/sec, burst 200 |
| Decoy admission | Independent 50/sec, burst 100 |
| Decoy session | 20 responses, 120-second absolute expiry |
| Decoy session table | 1,000 entries |
| Verification pending requests | 128 entries, 90-second local expiry |
| Gateway logs | 1 MiB active file, two rotated backups |

Socket operation timeouts are not a total upstream transaction deadline. Separate
global admission does not reserve network bandwidth or gateway worker slots for
legitimate callers. Connection floods can still deny service. These are explicit
limitations, not production DDoS guarantees.

## Why this implementation differs from the research sketch

- Standard-library HTTP and `unittest` keep dependencies small and the protocol
  deliberately narrow. This server is not production infrastructure. A mature
  parser/front proxy and differential tests are required before expansion.
- Ed25519 uses the documented
  [cryptography API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
  The versioned application envelope avoids claiming unimplemented RFC compliance.
  Migration to a reviewed RFC 9421 implementation is a separate milestone.
- Docker uses Unix sockets with `network_mode: none` for the private services,
  rather than relying on a shared bridge to prevent egress.
- There is no live LLM generation, hostile code execution, arbitrary shell,
  attacker-side command, or adaptive production routing.

The security-critical code remains unaudited. Passing the provided tests is not
a proof of isolation under every deployment or input.
