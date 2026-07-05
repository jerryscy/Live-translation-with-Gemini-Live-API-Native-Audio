# Deploying to Cloud Run

This app runs the **same code** locally and on Cloud Run — only the launch
method and configuration differ. It's a single lightweight process; noise
handling is done in the browser (`noiseSuppression`), so there's no torch
dependency and no sidecar.

Local development uses `./run.sh` (see `RUN.md`). The `Dockerfile` is only
used for Cloud Run.

---

## Prerequisites

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com aiplatform.googleapis.com \
                       artifactregistry.googleapis.com cloudbuild.googleapis.com
```

The Live API is accessed via Vertex AI, so the Cloud Run **service account**
needs the Vertex AI User role:

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${PROJECT_NUM}-compute@developer.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

> Or create a dedicated service account and pass it with `--service-account` below.

---

## Deploy (source-based — Cloud Build builds the Dockerfile for you)

```bash
gcloud run deploy live-translation \
  --source . \
  --region=us-central1 \
  --allow-unauthenticated \
  --session-affinity \
  --timeout=3600 \
  --cpu=1 --memory=1Gi \
  --concurrency=1 \
  --min-instances=0 --max-instances=10 \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=us-central1,LIVE_API_MODEL=gemini-live-2.5-flash-native-audio,IDLE_CLOSE_SECONDS=30
```

Cloud Run prints a `https://...run.app` URL. Open it — HTTPS is automatic, so
the microphone (`getUserMedia`/`AudioWorklet`) and `wss://` both work.

### Why these flags

| Flag | Why |
|---|---|
| `--session-affinity` | Keeps each WebSocket client pinned to one instance |
| `--timeout=3600` | Max (60 min) — long translation sessions aren't cut off (default is 300s) |
| `--concurrency=1` | **Important:** the app currently uses one shared worker per instance, so allow only one user per instance. Autoscaling gives each user their own instance. Raise this only after the per-connection-worker refactor |
| `--cpu=1 --memory=1Gi` | Plenty for the lightweight single process |
| `--set-env-vars=...` | Replaces the local `.env` (which isn't in the image) |

> No API key is needed — the genai client uses `vertexai=True` and picks up the
> service account's Application Default Credentials from the metadata server.

---

## Optional: build/push manually via Artifact Registry

```bash
gcloud artifacts repositories create apps --repository-format=docker --location=us-central1
gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/apps/live-translation
gcloud run deploy live-translation \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/apps/live-translation \
  --region=us-central1 --allow-unauthenticated --session-affinity \
  --timeout=3600 --cpu=1 --memory=1Gi --concurrency=1 \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID,GOOGLE_CLOUD_LOCATION=us-central1
```

---

## Test the container locally (optional)

```bash
docker build -t live-translation .
docker run --rm -p 8080:8080 \
  -e GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID -e GOOGLE_CLOUD_LOCATION=us-central1 \
  -v $HOME/.config/gcloud:/root/.config/gcloud:ro \
  live-translation
# open http://127.0.0.1:8080
```

(The `-v .../gcloud` mount lets the container reuse your local ADC for testing.)

---

## Access control — in-app Google OAuth

The app can gate every page, the `/config` API, and the `/ws` WebSocket behind
a Google (OpenID Connect) login, restricted to a single Workspace domain
(`ALLOWED_HD`, default `google.com`). Cloud Run itself stays
`--allow-unauthenticated`; the **app** does the gating so browser users get a
normal Google sign-in page.

Auth turns on automatically when `OAUTH_CLIENT_ID` + `OAUTH_CLIENT_SECRET` are
present; if they're blank the app is open (useful for local dev).

### 1. Create an OAuth client

Google Cloud Console → **APIs & Services → Credentials → Create credentials →
OAuth client ID → Web application**. Under **Authorized redirect URIs** add:

```
http://127.0.0.1:8000/auth                          # local testing
https://<your-service-url>/auth                      # Cloud Run
```

The callback path is `/auth` and must match exactly (scheme, host, no trailing
slash). Copy the **Client ID** and **Client secret**.

### 2. Store the secrets in Secret Manager

The client secret and the session-signing secret should **not** be passed as
plain env vars. Store them in Secret Manager and reference them at deploy time.

```bash
gcloud services enable secretmanager.googleapis.com

# Client secret from the OAuth client
printf '%s' 'YOUR_CLIENT_SECRET' | \
  gcloud secrets create oauth-client-secret --data-file=- --replication-policy=automatic

# Stable random session secret (signs the login cookie)
python -c "import secrets; print(secrets.token_urlsafe(32))" | tr -d '\n' | \
  gcloud secrets create session-secret --data-file=- --replication-policy=automatic

# Let the Cloud Run runtime service account read them
PROJECT_NUM=$(gcloud projects describe "$(gcloud config get-value project)" --format='value(projectNumber)')
SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"
for s in oauth-client-secret session-secret; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:${SA}" \
    --role="roles/secretmanager.secretAccessor" --condition=None
done
```

> To rotate later: `gcloud secrets versions add <name> --data-file=-` then
> redeploy (or the next cold start) picks up `:latest`. Keep `session-secret`
> stable, though — changing it invalidates all existing login cookies.

### 3. Deploy

Non-secret config goes in `--set-env-vars`; the two secrets come from Secret
Manager via `--set-secrets`:

```bash
gcloud run deploy live-translation \
  --source . --region=us-central1 --allow-unauthenticated \
  --session-affinity --timeout=3600 --cpu=1 --memory=1Gi --concurrency=1 \
  --set-env-vars="^@^GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID@GOOGLE_CLOUD_LOCATION=us-central1@LIVE_API_MODEL=gemini-live-2.5-flash-native-audio@IDLE_CLOSE_SECONDS=30@OAUTH_CLIENT_ID=YOUR_CLIENT_ID@OAUTH_REDIRECT_URI=https://<your-service-url>/auth@ALLOWED_HD=google.com" \
  --set-secrets="OAUTH_CLIENT_SECRET=oauth-client-secret:latest,SESSION_SECRET=session-secret:latest"
```

Notes:
- `OAUTH_REDIRECT_URI` must be the **https** Cloud Run URL — Cloud Run forwards
  http internally, so setting it explicitly avoids a scheme mismatch.
- `--set-env-vars` and `--set-secrets` are independent; list every non-secret
  var in the former since it replaces the whole env-var set.

### 4. Verify

```bash
BASE=https://<your-service-url>
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/"        # 307 -> /login
curl -s -o /dev/null -w "%{http_code}\n" "$BASE/config"  # 401 when anonymous
curl -sD - -o /dev/null "$BASE/login" | grep -i location # -> accounts.google.com
```

Open `$BASE` in a browser → you're sent to Google → after signing in with an
`@google.com` account you land on the app. Non-matching domains get a 403.
`/logout` clears the session.

---

## Known limitation — multi-user scaling

The backend keeps a **single shared `LiveAPIWorker` per instance**, so one
instance serves one active session. `--concurrency=1` works around this by
giving each user a separate instance. For higher density, refactor to a
**per-connection worker**, then raise `--concurrency`.
