"""One bounded HTTP/1 request per connection, for localhost/Unix-socket demos.

Not a general HTTP server. No proxying of bodies, upgrades or persistent streams.
"""

import http.client
import logging
import re
import socket
import socketserver
import threading
import time

from .common import MAX_RESPONSE, Request, Response, error

MAX_HEADERS = 8192


class ProtocolError(ValueError):
    pass


def read_request(connection):
    raw, deadline = b"", time.monotonic() + 2
    while b"\r\n\r\n" not in raw:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ProtocolError("deadline")
        connection.settimeout(min(0.5, remaining))
        chunk = connection.recv(min(1024, MAX_HEADERS + 1 - len(raw)))
        if not chunk:
            raise ProtocolError("incomplete headers")
        raw += chunk
        if len(raw) > MAX_HEADERS:
            raise ProtocolError("header budget")
    head, extra = raw.split(b"\r\n\r\n", 1)
    if extra:
        raise ProtocolError("body or pipelining")
    try:
        lines = head.decode("ascii").split("\r\n")
        if len(lines[0]) > 2048 or len(lines) > 33:
            raise ProtocolError("limits")
        parts = lines[0].split(" ")
        if len(parts) != 3 or parts[2] not in ("HTTP/1.0", "HTTP/1.1"):
            raise ProtocolError("request line")
        headers = []
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            if not separator or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
                raise ProtocolError("header name")
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ProtocolError("header value")
            headers.append((name, value.strip(" ")))
        return Request(parts[0], parts[1], headers)
    except UnicodeError as exc:
        raise ProtocolError("ASCII only") from exc


def wire(result):
    return (f"HTTP/1.1 {result.status} Response\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(result.body)}\r\n"
            "Cache-Control: no-store\r\n"
            "X-Content-Type-Options: nosniff\r\n"
            "Connection: close\r\n\r\n").encode("ascii") + result.body


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            try:
                request = read_request(self.request)
                result = self.server.app(request)
                if len(result.body) > MAX_RESPONSE:
                    result = error(500, "response_budget")
            except (ValueError, OSError):
                result = error(400, "invalid_request")
            except Exception:
                # Do not include exception messages that may contain attacker input.
                logging.getLogger("openmaze").error("service dispatch failed")
                result = error(500, "internal_error")
            self.request.settimeout(0.5)
            self.request.sendall(wire(result))
        except OSError:
            pass


class BoundedThreads(socketserver.ThreadingMixIn):
    daemon_threads = True
    block_on_close = False

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                request.sendall(wire(error(503, "concurrency_budget")))
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class TCPServer(BoundedThreads, socketserver.TCPServer):
    allow_reuse_address = True
    request_queue_size = 32


class UnixServer(BoundedThreads, socketserver.UnixStreamServer):
    request_queue_size = 32


def make_server(address, app, unix=False):
    server = (UnixServer if unix else TCPServer)(address, Handler)
    server.app, server.slots = app, threading.BoundedSemaphore(16)
    return server


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=0.25)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def call(connection, request):
    try:
        connection.request(request.method, request.target, headers=dict(request.headers))
        result = connection.getresponse()
        body = result.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise ValueError("upstream response too large")
        return Response(result.status, body)
    except http.client.HTTPException as exc:
        raise ValueError("upstream protocol error") from exc
    finally:
        connection.close()


def unix_call(path, request):
    return call(UnixConnection(path), request)


def tcp_call(port, request):
    return call(http.client.HTTPConnection("127.0.0.1", port, timeout=0.25), request)
