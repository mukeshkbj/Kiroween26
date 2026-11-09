"""A minimal TN3270 server that presents the Seance Insurance stand-in.

Speaks just enough telnet + TN3270 for s3270 (the bridge's client) to connect,
receive Erase/Write screens and send back inbound AID + modified fields. One
``InsuranceApp`` per connection; the business logic runs on the live TK4- via
``CobolClient``.

Telnet negotiation (basic TN3270, RFC 1576-style): we negotiate BINARY both
ways, END-OF-RECORD (EOR) both ways, and TERMINAL-TYPE (we accept whatever
s3270 offers). After that, 3270 streams are framed by IAC EOR.
"""
from __future__ import annotations

import socket
import socketserver
import threading

from . import datastream as ds
from .app import InsuranceApp
from .cobol_client import CobolClient
from .screens import COLS

# Telnet
IAC = 0xFF
DO, DONT, WILL, WONT, SB, SE = 0xFD, 0xFE, 0xFB, 0xFC, 0xFA, 0xF0
EOR = 0xEF                      # end-of-record (follows IAC)
OPT_BINARY = 0x00
OPT_EOR = 0x19
OPT_TTYPE = 0x18
OPT_SGA = 0x03


class _Conn:
    """Per-connection telnet framing over a socket."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = bytearray()

    def negotiate(self) -> None:
        # Offer the basic TN3270 option set and request it of the client.
        for cmd, opt in [(WILL, OPT_BINARY), (DO, OPT_BINARY),
                         (WILL, OPT_EOR), (DO, OPT_EOR),
                         (DO, OPT_TTYPE), (WILL, OPT_SGA)]:
            self._send_iac(cmd, opt)

    def _send_iac(self, cmd: int, opt: int) -> None:
        self.sock.sendall(bytes([IAC, cmd, opt]))

    def send_record(self, payload: bytes) -> None:
        """Send a 3270 record: escape IAC in data, terminate with IAC EOR."""
        escaped = payload.replace(bytes([IAC]), bytes([IAC, IAC]))
        self.sock.sendall(escaped + bytes([IAC, EOR]))

    def read_record(self) -> bytes | None:
        """Read one inbound 3270 record (up to IAC EOR), handling negotiation.

        Returns the 3270 payload bytes, or None if the peer closed.
        """
        record = bytearray()
        while True:
            b = self._next_byte()
            if b is None:
                return None
            if b != IAC:
                record.append(b)
                continue
            c = self._next_byte()
            if c is None:
                return None
            if c == IAC:                      # escaped 0xFF data byte
                record.append(IAC)
            elif c == EOR:
                return bytes(record)
            elif c in (DO, DONT, WILL, WONT):
                opt = self._next_byte()
                self._reply_negotiation(c, opt)
            elif c == SB:
                self._consume_subneg()
            else:
                pass  # ignore other telnet commands

    def _reply_negotiation(self, cmd: int, opt: int | None) -> None:
        if opt is None:
            return
        # Accept BINARY/EOR; acknowledge TTYPE/SGA; refuse anything else.
        if cmd == WILL:
            self._send_iac(DO if opt in (OPT_BINARY, OPT_EOR, OPT_TTYPE, OPT_SGA) else DONT, opt)
        elif cmd == DO:
            self._send_iac(WILL if opt in (OPT_BINARY, OPT_EOR, OPT_SGA) else WONT, opt)

    def _consume_subneg(self) -> None:
        # Read through IAC SE. If the client sends its terminal type, ignore it
        # (we always paint a 24x80 3278-2 compatible stream).
        while True:
            b = self._next_byte()
            if b is None:
                return
            if b == IAC:
                c = self._next_byte()
                if c == SE:
                    return

    def _next_byte(self) -> int | None:
        if not self.buf:
            try:
                chunk = self.sock.recv(4096)
            except OSError:
                return None
            if not chunk:
                return None
            self.buf.extend(chunk)
        return self.buf.pop(0)


def _typed_from_inbound(app_screen, inbound: ds.Inbound) -> dict[str, str]:
    """Map inbound modified-field addresses to the screen's named inputs.

    An inbound field's buffer address is the first data cell of the field (one
    past its attribute byte), which equals rc(spec.row, spec.col).
    """
    by_addr = {ds.rc(s.row, s.col): s for s in app_screen.inputs}
    typed: dict[str, str] = {}
    for f in inbound.fields:
        spec = by_addr.get(f.addr)
        if spec is not None:
            typed[spec.name] = f.text.rstrip("\x00 ").strip()
    return typed


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        cobol: CobolClient = self.server.cobol  # type: ignore[attr-defined]
        conn = _Conn(self.request)
        conn.negotiate()
        app = InsuranceApp(cobol)
        self._send_screen(conn, app)
        while True:
            record = conn.read_record()
            if record is None:
                return
            if not record:
                continue
            inbound = ds.parse_inbound(record)
            typed = _typed_from_inbound(app.screen(), inbound)
            try:
                app.handle(inbound.aid, typed)
            except Exception:  # noqa: BLE001 - always answer the terminal
                # A bug must not leave the 3270 keyboard locked forever; the
                # client would see an ambiguous ack. Answer with a message.
                app.values["msg"] = "STAND-IN ERROR - SEE SERVER LOG"
                import traceback

                traceback.print_exc()
            self._send_screen(conn, app)

    def _send_screen(self, conn: _Conn, app: InsuranceApp) -> None:
        screen = app.screen()
        fields = screen.out_fields(app.render_values())
        stream = ds.build_erase_write(fields, cursor=screen.cursor_offset(), texts=screen.texts())
        conn.send_record(stream)


class StandinServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, host: str, port: int, cobol: CobolClient):
        super().__init__((host, port), _Handler)
        self.cobol = cobol


def serve(host: str = "0.0.0.0", port: int = 3271, cobol: CobolClient | None = None) -> StandinServer:
    server = StandinServer(host, port, cobol or CobolClient())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
