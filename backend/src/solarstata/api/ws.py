"""WebSocket endpoint for Pro mode — stream chunked result blocks per command.

Wire protocol (JSON, line-delimited):

  Client → Server
    {"type": "run", "command": "regress y x1 x2, vce(robust)"}

  Server → Client
    {"type": "started", "command": "regress y x1 x2, vce(robust)"}
    {"type": "block", "kind": "regress" | "summarize" | ..., "structured": {...}, "text": "..."}
    {"type": "history_appended"}
    {"type": "complete"}

  Errors
    {"type": "error", "detail": "no estimates stored"}

Phase 3 emits one `block` per dispatched command (no streaming subdivision
inside a single block yet); we run the whole compute on the FastAPI worker
thread and ship blocks back as they're produced.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..engine.dofile import dispatch, parse_line
from ..session.store import session_store
from ._jsonsafe import safe

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/pro")
async def pro_ws(ws: WebSocket) -> None:
    # Pull session from the cookie the WebSocket carries.
    cookie = ws.cookies.get("solarstata_session")
    session = None
    if cookie:
        try:
            from itsdangerous import URLSafeSerializer
            from ..config import settings
            sid = URLSafeSerializer(settings.session_secret, salt="solarstata").loads(cookie)
            session = session_store.get(sid)
        except Exception:  # noqa: BLE001 — bad cookie, mint a fresh one
            session = None
    if session is None:
        session = session_store.create()

    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "detail": "invalid JSON"}))
                continue

            if msg.get("type") != "run":
                await ws.send_text(json.dumps({"type": "error", "detail": "unsupported message type"}))
                continue

            command_str = msg.get("command", "")
            await _execute(ws, session, command_str)

    except WebSocketDisconnect:
        return


async def _execute(ws: WebSocket, session, command_str: str) -> None:
    parsed = None
    try:
        parsed = parse_line(command_str)
    except ValueError as exc:
        await ws.send_text(json.dumps({"type": "error", "detail": f"parse error: {exc}"}))
        return

    if parsed is None:
        return

    frame = session.current_frame
    if frame is None and parsed.command not in ("clear", "exit"):
        await ws.send_text(json.dumps({"type": "error", "detail": "no dataset loaded"}))
        return

    await ws.send_text(json.dumps({"type": "started", "command": parsed.raw}))

    try:
        outcome = dispatch(parsed, session, frame)
    except (KeyError, ValueError) as exc:
        await ws.send_text(json.dumps({"type": "error", "detail": str(exc)}))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch failed")
        await ws.send_text(json.dumps({"type": "error", "detail": f"unexpected error: {exc}"}))
        return

    # Stream each block as a discrete frame so the Pro mode results pane can
    # render them progressively. Phase 3 only ever produces one block per
    # command, but the protocol is already block-aware.
    for result in outcome.blocks:
        block = {
            "type": "block",
            "kind": result.structured.get("kind", parsed.command),
            "structured": safe(result.structured),
            "text": result.text,
            "command": result.command,
        }
        await ws.send_text(json.dumps(block))

    if outcome.estimation is not None:
        session.last_estimation = outcome.estimation
        if outcome.blocks:
            session.e_results = dict(outcome.blocks[0].e_update or {})

    for var, col in outcome.dataset_mutations:
        frame.df[var] = col
        frame.storage_types[var] = "double"

    session.append_history(parsed.raw)
    await ws.send_text(json.dumps({"type": "history_appended", "command": parsed.raw}))
    await ws.send_text(json.dumps({"type": "complete"}))
