import argparse
import http.client
import logging
import signal
import select
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import sys
import time

from .common import Policy, decode
from .transport import make_server, tcp_call, unix_call


def application(role, state, mode, transport="tcp", backend_port=8081, decoy_port=8082):
    if role == "decoy":
        from .decoy import Decoy
        return Decoy((state / "decoy.seed").read_bytes())
    policy = Policy(decode((state / "auth.json").read_bytes()))
    if role == "protected":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from .protected import Protected
        return Protected(policy, Ed25519PrivateKey.from_private_bytes((state / "signing.key").read_bytes()))
    from .gateway import Gateway
    logger = logging.getLogger("openmaze.events")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(state / "logs/events.log", maxBytes=1024 * 1024, backupCount=2)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    backend = (lambda r: unix_call(state / "backend/api.sock", r)) if transport == "unix" else (lambda r: tcp_call(backend_port, r))
    decoy = (lambda r: unix_call(state / "decoy/api.sock", r)) if transport == "unix" else (lambda r: tcp_call(decoy_port, r))
    return Gateway(policy, backend, decoy, mode, logger)


def serve(args):
    state = args.state.resolve()
    app = application(args.role, state, args.mode, args.transport, args.backend_port, args.decoy_port)
    if args.role == "gateway":
        address, unix = (args.host, args.port), False
    elif args.transport == "unix":
        address = str(state / ("backend" if args.role == "protected" else "decoy") / "api.sock")
        unix = True
        # Never replace a live or stale socket silently. Operator must investigate.
        if Path(address).exists():
            raise RuntimeError(f"socket already exists: {address}")
    else:
        address = ("127.0.0.1", args.backend_port if args.role == "protected" else args.decoy_port)
        unix = False
    server = make_server(address, app, unix)
    if unix:
        Path(address).chmod(0o600)
    try:
        with server:
            print(f"{args.role} listening on {address}", flush=True)
            server.serve_forever(poll_interval=0.1)
    finally:
        if unix:
            Path(address).unlink(missing_ok=True)


def demo(args):
    processes = []
    try:
        for role, directory in (("protected", "backend"), ("decoy", "decoy")):
            path = args.state / directory / "api.sock"
            if args.transport == "unix" and path.exists():
                raise RuntimeError(f"socket already exists: {path}")
            process = subprocess.Popen([sys.executable, "-m", "openmaze", "serve", role,
                                        "--state", str(args.state), "--transport", args.transport,
                                        "--backend-port", str(args.backend_port),
                                        "--decoy-port", str(args.decoy_port)],
                                       stdout=subprocess.PIPE, text=True)
            processes.append(process)
            # Readiness comes from our own child after bind, not another process
            # that happens to own the expected TCP port or stale socket path.
            if not select.select([process.stdout], [], [], 5)[0]:
                raise RuntimeError(f"{role} did not start")
            ready = process.stdout.readline()
            if not ready.startswith(f"{role} listening on "):
                raise RuntimeError(f"{role} did not start")
            print(ready.rstrip(), flush=True)
        args.role = "gateway"
        serve(args)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
        # Only sockets belonging to children launched by this command.
        if args.transport == "unix":
            for directory in ("backend", "decoy")[:len(processes)]:
                (args.state / directory / "api.sock").unlink(missing_ok=True)


def client(args):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from .receipts import Verifier
    policy = decode((args.state / "auth.json").read_bytes())
    verifier = Verifier(Ed25519PublicKey.from_public_bytes((args.state / "verify.key").read_bytes()))
    target = f"/v1/tenants/{args.tenant}/records"
    nonce = verifier.begin("GET", target)
    connection = http.client.HTTPConnection("127.0.0.1", args.port, timeout=3)
    try:
        connection.request("GET", target, headers={"Authorization": f"Bearer {policy[args.tenant]}",
                                                  "X-OpenMaze-Nonce": nonce})
        result = connection.getresponse()
        payload = verifier.verify(result.read(8193), result.status, nonce)
        print("Verified protected response:", payload)
    finally:
        connection.close()


def main():
    def stop(_signal, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    parser = argparse.ArgumentParser(description="OpenMaze local research prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "serve", "demo", "client"):
        command = commands.add_parser(name)
        command.add_argument("--state", type=Path, default=Path(".openmaze"))
        if name == "serve":
            command.add_argument("role", choices=("gateway", "protected", "decoy"))
        if name in ("serve", "demo"):
            command.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
            command.add_argument("--mode", choices=("deny", "maze"), default="deny")
            command.add_argument("--transport", choices=("tcp", "unix"), default="tcp")
            command.add_argument("--backend-port", type=int, default=8081)
            command.add_argument("--decoy-port", type=int, default=8082)
        if name in ("serve", "demo", "client"):
            command.add_argument("--port", type=int, default=8080)
        if name == "client":
            command.add_argument("--tenant", choices=("alpha", "beta"), default="alpha")
    args = parser.parse_args()
    try:
        if args.command == "init":
            from .setup import initialize
            initialize(args.state)
            print("Created local demo state; credentials remain in auth.json.")
        else:
            {"serve": serve, "demo": demo, "client": client}[args.command](args)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"OpenMaze: {exc}\n")


if __name__ == "__main__":
    main()
