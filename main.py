import os
import asyncio
import json
import shutil
import subprocess
from contextlib import asynccontextmanager
from typing import Optional

import secrets

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth, OAuthError

from liveapiworker import LiveAPIWorker
from languages import languages_json, name_for_code

load_dotenv(override=True)  # .env wins over inherited env (e.g. GOOGLE_CLOUD_LOCATION=global)

# --- Configuration (all overridable via .env) ---
DEFAULT_SOURCE_LANG_CODE = os.getenv("DEFAULT_SOURCE_LANG_CODE", "cmn-CN")
DEFAULT_TARGET_LANG_CODE = os.getenv("DEFAULT_TARGET_LANG_CODE", "en-US")
DEFAULT_SOURCE_LANG = os.getenv("DEFAULT_SOURCE_LANG") or name_for_code(DEFAULT_SOURCE_LANG_CODE)
DEFAULT_TARGET_LANG = os.getenv("DEFAULT_TARGET_LANG") or name_for_code(DEFAULT_TARGET_LANG_CODE)

# --- OAuth / auth configuration ---
# In-app Google (OpenID Connect) login. When a client id + secret are present,
# every page/API/WebSocket requires a signed-in user whose email domain matches
# ALLOWED_HD (default google.com). If not configured, auth is DISABLED so local
# development without credentials still works.
OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "")
# Explicit callback URL registered on the OAuth client. Deterministic across
# proxies (Cloud Run forwards http internally, so request.url_for would produce
# the wrong scheme). Falls back to request.url_for('auth') when unset.
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "")
ALLOWED_HD = os.getenv("ALLOWED_HD", "google.com")
# Must be stable across restarts/instances so session cookies stay valid.
SESSION_SECRET = os.getenv("SESSION_SECRET") or secrets.token_urlsafe(32)
AUTH_ENABLED = bool(OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET)

oauth = OAuth()
if AUTH_ENABLED:
    oauth.register(
        name="google",
        client_id=OAUTH_CLIENT_ID,
        client_secret=OAUTH_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _current_user(request: Request):
    """Return the signed-in user dict, or None."""
    return request.session.get("user")


def _is_authed(request: Request) -> bool:
    """True when auth is disabled, or a valid user is in the session."""
    return (not AUTH_ENABLED) or bool(request.session.get("user"))

liveapiworker: Optional[LiveAPIWorker] = None
_worker_task: Optional[asyncio.Task] = None
# The single WebSocket the broadcaster forwards events to (the most recently
# connected tab). Using ONE consumer + ONE active target prevents the worker's
# shared event queue from being split across multiple/zombie connections.
_active_ws: Optional[WebSocket] = None
_broadcaster_task: Optional[asyncio.Task] = None


def check_gcloud_auth() -> bool:
    """Check for gcloud application-default credentials (non-blocking).

    Returns True if ADC is present. If not, prints a clear instruction and
    returns False rather than launching an interactive login (which would
    hang the server startup). The UI still boots; the Live API session will
    error until the user authenticates.
    """
    # In containers / Cloud Run there is no gcloud CLI — the app relies on
    # ambient Application Default Credentials (the service account exposed via
    # the metadata server, or GOOGLE_APPLICATION_CREDENTIALS). Skip the check
    # quietly instead of printing a misleading warning.
    if shutil.which("gcloud") is None:
        print("[startup] gcloud CLI not found; relying on ambient ADC "
              "(Cloud Run service account / metadata server).")
        return True
    try:
        subprocess.check_output(
            ["gcloud", "auth", "application-default", "print-access-token"],
            stderr=subprocess.STDOUT,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("=" * 70)
        print("  Google Cloud ADC not found. Translation will fail until you run:")
        print("      gcloud auth application-default login")
        print("=" * 70)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    global liveapiworker, _worker_task, _broadcaster_task
    check_gcloud_auth()

    liveapiworker = LiveAPIWorker(
        DEFAULT_SOURCE_LANG,
        DEFAULT_TARGET_LANG,
        source_language_code=DEFAULT_SOURCE_LANG_CODE,
        target_language_code=DEFAULT_TARGET_LANG_CODE,
    )

    _worker_task = asyncio.create_task(liveapiworker.run(), name="live-api-worker")
    _broadcaster_task = asyncio.create_task(_broadcaster(), name="ws-broadcaster")
    yield
    # Graceful shutdown: cancel the background tasks.
    for _t in (_worker_task, _broadcaster_task):
        if _t and not _t.done():
            _t.cancel()
    await asyncio.gather(_worker_task, _broadcaster_task, return_exceptions=True)


app = FastAPI(lifespan=lifespan)
# SessionMiddleware signs a cookie that holds the logged-in user. same_site
# 'lax' allows the cookie to ride along on the top-level OAuth redirect back
# from Google. https_only stays off so local http testing works; on Cloud Run
# the connection is https anyway.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory="static"), name="static")


# --------------------------- Auth routes ---------------------------
@app.get("/login")
async def login(request: Request):
    """Kick off the Google OpenID Connect flow."""
    if not AUTH_ENABLED:
        return RedirectResponse("/")
    redirect_uri = OAUTH_REDIRECT_URI or str(request.url_for("auth"))
    # `hd` pre-selects the org's accounts on the Google chooser (soft hint;
    # the hard check happens in the callback).
    return await oauth.google.authorize_redirect(request, redirect_uri, hd=ALLOWED_HD)


@app.get("/auth", name="auth")
async def auth(request: Request):
    """OAuth callback: verify the user and start a session."""
    if not AUTH_ENABLED:
        return RedirectResponse("/")
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        return HTMLResponse(f"Sign-in failed: {exc.error}", status_code=401)

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    verified = userinfo.get("email_verified")
    hd = userinfo.get("hd")

    # Hard domain restriction: verified email must be @ALLOWED_HD.
    if not verified or not email.endswith("@" + ALLOWED_HD) or (hd and hd != ALLOWED_HD):
        return HTMLResponse(
            f"<h3>Access denied</h3><p>This app is restricted to "
            f"<b>@{ALLOWED_HD}</b> accounts. You signed in as "
            f"<b>{email or 'unknown'}</b>.</p>"
            f'<p><a href="/logout">Try another account</a></p>',
            status_code=403,
        )

    request.session["user"] = {"email": email, "name": userinfo.get("name")}
    return RedirectResponse("/")


@app.get("/logout")
async def logout(request: Request):
    """Clear the local session and bounce home (re-triggers login)."""
    request.session.pop("user", None)
    return RedirectResponse("/")


@app.get("/me")
async def me(request: Request):
    """Report the signed-in user so the UI can show an auth header."""
    user = _current_user(request)
    return JSONResponse(
        {
            "auth_enabled": AUTH_ENABLED,
            "authenticated": bool(user) or not AUTH_ENABLED,
            "email": (user or {}).get("email"),
            "name": (user or {}).get("name"),
            "allowed_hd": ALLOWED_HD if AUTH_ENABLED else None,
        }
    )


@app.get("/config")
async def get_config(request: Request):
    """Expose language list + defaults to the frontend."""
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return JSONResponse(
        {
            "languages": languages_json(),
            "default_source_code": DEFAULT_SOURCE_LANG_CODE,
            "default_target_code": DEFAULT_TARGET_LANG_CODE,
            "model": LiveAPIWorker.MODEL_ID,
        }
    )


async def _broadcaster() -> None:
    """Single consumer of the worker's event queue.

    Forwards every event to the CURRENT active WebSocket only (`_active_ws`,
    the most recently connected tab). Previously each connection ran its own
    consumer draining the SAME shared queue, so with more than one connection
    (a second tab, a reconnect that left a zombie, an inspector tab, etc.) the
    events were split across connections. Because there is exactly one
    input-transcription (type 1) record per turn but many translation (type 2)
    records, the single input record frequently landed on a stale connection
    and never reached the visible tab. One consumer + one active target fixes
    that.
    """
    while True:
        event = await liveapiworker.event_queue.get()
        ws = _active_ws
        try:
            if ws is None:
                continue

            event_type = event["type"]

            if event_type == "audio":
                await ws.send_bytes(event["data"])

            elif event_type == "data":
                # The uid/seq/type/message/finished data contract.
                await ws.send_text(
                    json.dumps({"kind": "data", "data": event["payload"]})
                )

            elif event_type == "live_api_status":
                await ws.send_text(
                    json.dumps({
                        "kind": "status",
                        "live_api_status": {
                            "connected": event.get("connected", False),
                            "state": event.get("state", "disconnected"),
                        },
                    })
                )

        except Exception as exc:
            print(f"[broadcaster] Error sending to client: {exc}")
        finally:
            liveapiworker.event_queue.task_done()


@app.get("/")
async def get(request: Request):
    if not _is_authed(request):
        return RedirectResponse("/login")
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _active_ws
    # Reject unauthenticated sockets before accepting (reads the same signed
    # session cookie the page was served with).
    if AUTH_ENABLED and not websocket.session.get("user"):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()

    # This connection becomes the sole active target for broadcasted events.
    # A newer tab supersedes an older one (single-user app).
    _active_ws = websocket

    # New browser connection = new client session (fresh uid, seq resets to 1).
    # seq then accumulates across turns and Start/Stop until the next connect.
    liveapiworker.begin_client_session()

    # Send the current Live API connection state immediately so the client
    # can render the status indicator without waiting for the next change.
    try:
        connected = bool(getattr(liveapiworker, "live_api_connected", False))
        await websocket.send_text(
            json.dumps({
                "kind": "status",
                "live_api_status": {
                    "connected": connected,
                    "state": "connected" if connected else "disconnected",
                },
            })
        )
    except Exception as exc:
        print(f"[websocket] Failed to send initial status: {exc}")

    try:
        while True:
            data = await websocket.receive()

            if data.get("type") == "websocket.disconnect":
                print("Client disconnected")
                break

            if "bytes" in data:
                await liveapiworker.send_audio_data(data["bytes"])

            elif "text" in data:
                message = json.loads(data["text"])
                action = message.get("action")

                if action == "start_session":
                    await liveapiworker.start_session()
                elif action == "stop_session":
                    await liveapiworker.stop_session()
                elif action == "set_audio_output":
                    liveapiworker.set_audio_output(bool(message.get("enabled", True)))
                elif "source_language" in message or "target_language" in message:
                    source = message.get("source_language", liveapiworker.source_language)
                    target = message.get("target_language", liveapiworker.target_language)
                    source_code = message.get(
                        "source_language_code", liveapiworker.source_language_code
                    )
                    target_code = message.get(
                        "target_language_code", liveapiworker.target_language_code
                    )
                    await liveapiworker.set_language(
                        source, target,
                        source_code=source_code,
                        target_code=target_code,
                    )

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as exc:
        print(f"[websocket] Unexpected error: {exc}")
    finally:
        # Only clear the active target if this connection is still the active
        # one (a newer tab may have already taken over).
        if _active_ws is websocket:
            _active_ws = None


if __name__ == "__main__":
    # HOST/PORT are env-driven so the same code runs locally and on Cloud Run.
    # Local default: 127.0.0.1:8000. Cloud Run sets PORT (usually 8080) and
    # requires binding 0.0.0.0.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
