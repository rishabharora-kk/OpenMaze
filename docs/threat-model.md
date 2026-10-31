# Threat model

## Assets and attacker

Assets: private synthetic tenant records, read authorization, signing authority,
credentials and service availability. Attacker: a remote HTTP caller that can
probe arbitrary routes, rotate sessions, know the source code, and possess an
unprivileged tenant credential. No human/AI classifier is used.

The gateway, backend, host, credentials, pinned key, parser and deployment
configuration are trusted. The decoy is untrusted. A compromised gateway can use
its credentials against the backend. A compromised signer breaks authenticity.
A stolen alpha credential authorizes alpha reads; the maze cannot recover intent.

## Claimed properties are narrow

- Gateway-denied requests never invoke a protected record operation in the tested
  application flow.
- The backend separately checks tenant authority, including direct calls.
- A client holding the pinned key rejects modified, mismatched, stale, unsigned
  or already consumed responses under the implemented verification profile.
- Decoy interactions have finite response/state/admission budgets.

These properties are tested, not formally proven or independently audited.

## Deployment boundaries

Local TCP mode has process separation only. All services bind loopback by default.
Other processes with the same OS user's permissions can read state or call local
ports. Python-level separation does not contain a compromised process.

The optional Linux Compose design gives the decoy only its seed and its own Unix
socket directory. Protected/decoy services have no IP networking. The gateway sees
both sockets and credentials, but no signing key. Distinct mount namespaces keep
the decoy away from backend sockets and key files. All containers share a host
kernel and run under one non-root UID. This is not a defense against host/kernel
compromise, malicious Docker administrators, or container escape vulnerabilities.

Before claiming container isolation, on a supported Docker host:

1. Run the full suite with Unix-socket tests enabled.
2. Build and run Compose as a non-root UID matching the state owner.
3. Inspect effective CPU, memory, process, capability, mount and network settings.
4. From the decoy, verify that signing key, credentials, backend socket, host
   filesystem, Docker socket and cloud metadata are inaccessible.
5. Verify outbound IPv4/IPv6/DNS connections fail while gateway requests work.
6. Saturate the decoy and inspect resource growth, log rotation and legitimate
   request latency. Stop/start services and verify socket lifecycle/fail-closed errors.

The implementation runner has no Docker and prohibits filesystem AF_UNIX sockets.
Those deployment checks are outstanding; local TCP process tests were executed.

## Failure and availability limits

Upstream failures return 503; they never grant access or route into a real service
as a fallback. Invalid credentials and cross-tenant access remain explicit errors.
There is no disk-backed session growth or unbounded generated content.

Admission buckets and worker caps bound application work, but do not prevent
connection floods, bandwidth exhaustion, worker starvation or host-level DoS.
The two-second header deadline limits slow connections, not total concurrent
attack impact. No availability SLO is demonstrated.

Gateway logs contain route class, status, size and duration, with no supplied
paths, credentials, payloads or nonces. Retained event files total approximately
3 MiB plus record/rotation overhead. Protect state/log permissions and disk space.
Runtime/container stdout also needs rotation. Logs remain untrusted data for any
downstream analyst system.

## Excluded

Production/critical systems, arbitrary agent hosting, hostile code execution,
prompt-injection counterattacks, attacker-infrastructure access, public targeting,
universal autonomous-agent detection, permanent capture, secret-based maze paths,
key compromise recovery, and automatic credential revocation are not implemented.
