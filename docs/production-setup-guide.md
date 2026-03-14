# Goon Production Setup Guide

> From zero accounts to a working canary/production deployment.
> Domain placeholder: **holdplz.ai** (replace throughout when final)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Account Setup Checklist](#2-account-setup-checklist)
3. [Twilio Setup](#3-twilio-setup)
4. [Vapi Setup](#4-vapi-setup)
5. [Anthropic (Claude) Setup](#5-anthropic-claude-setup)
6. [Google Places Setup](#6-google-places-setup)
7. [Tavily Setup](#7-tavily-setup)
8. [Stripe Setup](#8-stripe-setup)
9. [Domain & DNS Setup](#9-domain--dns-setup)
10. [Railway Deployment](#10-railway-deployment)
11. [Canary / Staging / Production Pattern](#11-canary--staging--production-pattern)
12. [Seed Your Test User](#12-seed-your-test-user)
13. [Wire Up Webhooks](#13-wire-up-webhooks)
14. [First Test](#14-first-test)
15. [Litestream Backup](#15-litestream-backup)
16. [Voice Platform Decision: Vapi vs Alternatives](#16-voice-platform-decision)
17. [Hosting Decision: Railway vs Alternatives](#17-hosting-decision)
18. [Scaling Roadmap](#18-scaling-roadmap)

---

## 1. Architecture Overview

```
User's Phone
    │
    ├── SMS ──► Twilio ──► POST https://api.holdplz.ai/sms/webhook
    │                              │
    └── Call ──► Twilio ──► POST https://api.holdplz.ai/voice/webhook
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  FastAPI Server  │  (Railway)
                          │  Python 3.12    │
                          │                  │
                          │  Orchestrator    │──► Anthropic Claude API
                          │  Resolution      │──► Google Places API
                          │  Ladder          │──► Tavily Web Search
                          │                  │──► Vapi Outbound Calls
                          │  SQLite + Files  │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │  Vapi.ai         │
                          │  Voice Agent     │──► 11Labs TTS
                          │  (outbound)      │──► Deepgram STT
                          │                  │──► Claude LLM
                          └──────────────────┘
                                   │
                          POST https://api.holdplz.ai/vapi/events
                          (call results webhook)
```

**Two environments:**
- **Production**: `api.holdplz.ai` — all registered users
- **Canary/Staging**: `canary.holdplz.ai` — your account + specified test accounts only

---

## 2. Account Setup Checklist

Create these accounts in order. Each step lists what you need from it.

| # | Service | URL | What You Need | Est. Cost |
|---|---------|-----|---------------|-----------|
| 1 | Twilio | twilio.com | Account SID, Auth Token, Phone Number | ~$1/mo + usage |
| 2 | Vapi | vapi.ai | API Key, Phone Number ID | ~$0.15-0.25/min |
| 3 | Anthropic | console.anthropic.com | API Key | ~$0.003-0.01/msg |
| 4 | Google Cloud | console.cloud.google.com | Places API Key | $0-200/mo |
| 5 | Tavily | tavily.com | API Key | Free tier: 1000 req/mo |
| 6 | Stripe | stripe.com | Secret Key, Webhook Secret, Price ID | 2.9% + $0.30/txn |
| 7 | Railway | railway.app | Account + Project | ~$5-15/mo |
| 8 | Domain Registrar | (Cloudflare, Namecheap, etc.) | Domain + DNS | ~$10-15/yr |
| 9 | ElevenLabs | elevenlabs.io | Voice ID (used through Vapi) | Billed through Vapi |
| 10 | Backblaze B2 | backblaze.com | Bucket for SQLite backups | ~$0.005/GB/mo |

---

## 3. Twilio Setup

### 3a. Create Account
1. Go to https://www.twilio.com/try-twilio
2. Sign up with email. Verify your phone number.
3. Complete identity verification (required for production).

### 3b. Buy a Phone Number
```bash
# Via CLI (install: brew install twilio)
twilio login
twilio phone-numbers:buy:local --area-code 415
# Or buy via Console: Phone Numbers → Buy a Number
```

Pick an area code that makes sense for your user base. This is the number
users will text and call.

### 3c. Collect Credentials
From the Twilio Console dashboard:
- **Account SID**: starts with `AC...`
- **Auth Token**: click to reveal
- **Phone Number**: the number you just bought (E.164 format: `+1415XXXXXXX`)

### 3d. Upgrade from Trial
Trial accounts have limitations (verified numbers only, "Sent from Twilio"
prefix on SMS). Upgrade to a paid account before real testing.

### 3e. A2P 10DLC Registration (Required for US SMS)
US carriers now require A2P 10DLC registration for business SMS.
Without it, your messages may be filtered or blocked.

1. Console → Messaging → Trust Hub → A2P 10DLC
2. Register your brand (business name, EIN or sole proprietor info)
3. Create a Campaign (use case: "Customer service / notifications")
4. Assign your phone number to the campaign
5. Approval takes 1-5 business days

**Do this early — it's the longest lead-time item.**

### 3f. ENV vars from Twilio
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GOON_NUMBER=+1415XXXXXXX
```

---

## 4. Vapi Setup

### 4a. Create Account
1. Go to https://vapi.ai and sign up
2. Add a payment method (usage-based billing)

### 4b. Import Your Twilio Number
Vapi needs to control your Twilio number for outbound calls.

1. Vapi Dashboard → Phone Numbers → Import from Twilio
2. Enter your Twilio Account SID and Auth Token
3. Select your Goon phone number
4. Vapi will configure the number for outbound calling

**Note the Phone Number ID** Vapi assigns — you'll need it.

### 4c. Create an Inbound Assistant (for voice calls TO your number)
1. Dashboard → Assistants → Create
2. Model: Anthropic Claude (claude-sonnet-4-5)
3. Voice: ElevenLabs, pick a natural-sounding voice
4. Configure the system prompt (the soul document handles this in code)
5. Save — note the **Assistant ID**

### 4d. Configure Server URL
1. Go to your Assistant settings
2. Set Server URL to: `https://api.holdplz.ai/vapi/events`
   (or your canary URL for testing)

### 4e. Choose a Voice (ElevenLabs)

Vapi uses 11Labs as one of its TTS providers. You're choosing a voice
**within** Vapi, not setting up a separate 11Labs account.

Recommended voices for a natural-sounding caller:
- `jBzLvP03992lMFEkj2kJ` — "Adam" (currently in the codebase)
- Browse Vapi's voice library for alternatives
- You can also create a custom voice on elevenlabs.io and use it via Vapi

### 4f. ENV vars from Vapi
```env
VAPI_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
VAPI_PHONE_NUMBER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
VAPI_ASSISTANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## 5. Anthropic (Claude) Setup

### 5a. Create Account + API Key
1. Go to https://console.anthropic.com
2. Sign up, add payment method
3. Settings → API Keys → Create Key
4. Set a usage limit (start with $50/month, adjust as needed)

### 5b. ENV var
```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

---

## 6. Google Places Setup

### 6a. Create Google Cloud Project
1. Go to https://console.cloud.google.com
2. Create a new project (e.g., "goon-production")
3. Enable billing

### 6b. Enable Places API (New)
1. APIs & Services → Library → search "Places API (New)"
2. Enable it
3. **Important:** Enable the NEW Places API, not the legacy one.
   The code uses v2 endpoints (`places.googleapis.com/v1`).

### 6c. Create API Key
1. APIs & Services → Credentials → Create Credentials → API Key
2. Restrict the key:
   - Application restriction: HTTP referrers or IP (for production)
   - API restriction: Places API (New) only

### 6d. ENV var
```env
GOOGLE_PLACES_API_KEY=AIzaXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### 6e. Cost Control
- Places Text Search: $0.032 per request
- Place Details: $0.017 per request
- Set a budget alert at $50/month in Cloud Console → Billing → Budgets

---

## 7. Tavily Setup

### 7a. Create Account + API Key
1. Go to https://tavily.com
2. Sign up — free tier gives 1,000 requests/month
3. Dashboard → API Key

### 7b. ENV var
```env
TAVILY_API_KEY=tvly-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

---

## 8. Stripe Setup

### 8a. Create Account
1. Go to https://stripe.com and sign up
2. Complete business verification (can start with individual/sole proprietor)

### 8b. Create a Product + Price
1. Dashboard → Products → Add Product
2. Name: "Goon Monthly"
3. Pricing: $19.99/month, recurring
4. Save — note the **Price ID** (starts with `price_`)

### 8c. Create Webhook Endpoint
1. Developers → Webhooks → Add Endpoint
2. URL: `https://api.holdplz.ai/stripe/webhook`
3. Events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
4. Note the **Webhook Signing Secret** (starts with `whsec_`)

### 8d. ENV vars
```env
STRIPE_SECRET_KEY=sk_live_YOUR_KEY_HERE
STRIPE_WEBHOOK_SECRET=whsec_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
STRIPE_PRICE_ID=price_XXXXXXXXXXXXXXXXXXXXXXXX
```

**For testing, use test mode keys** (`sk_test_...`, `whsec_test_...`)
until you're ready for real payments.

---

## 9. Domain & DNS Setup

### 9a. Register Domain
Buy `holdplz.ai` (or your chosen domain) from Cloudflare, Namecheap,
or your preferred registrar.

### 9b. DNS Records (configure after Railway deployment)

| Type | Name | Value | Purpose |
|------|------|-------|---------|
| CNAME | `api` | `<railway-provided-domain>` | Production API |
| CNAME | `canary` | `<railway-staging-domain>` | Canary/staging API |
| CNAME | `www` | `<vercel-or-railway-domain>` | Landing page (future) |
| A/CNAME | `@` | (landing page host) | Root domain |

Railway provides the CNAME target when you add a custom domain.

---

## 10. Railway Deployment

### 10a. Install Railway CLI
```bash
brew install railway
railway login
```

### 10b. Create Project
```bash
cd ~/gt/goon/mayor/rig
railway init
# Name: goon-production
```

### 10c. Create a Persistent Volume
```bash
railway volume create --mount /data
# This is where SQLite + user markdown files live
```

### 10d. Configure Environment Variables
```bash
# Set all env vars (Railway encrypts these at rest)
railway variables set TWILIO_ACCOUNT_SID=ACxxxxxxxx
railway variables set TWILIO_AUTH_TOKEN=xxxxxxxx
railway variables set GOON_NUMBER=+1415XXXXXXX
railway variables set VAPI_API_KEY=xxxxxxxx
railway variables set VAPI_PHONE_NUMBER_ID=xxxxxxxx
railway variables set VAPI_ASSISTANT_ID=xxxxxxxx
railway variables set ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
railway variables set ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
railway variables set GOOGLE_PLACES_API_KEY=AIzaxxxxxxxx
railway variables set TAVILY_API_KEY=tvly-xxxxxxxx
railway variables set STRIPE_SECRET_KEY=sk_live_xxxxxxxx
railway variables set STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxx
railway variables set STRIPE_PRICE_ID=price_xxxxxxxx
railway variables set ADMIN_PASSWORD=<generate-a-strong-password>
railway variables set BASE_URL=https://api.holdplz.ai
railway variables set DATABASE_URL=sqlite:///data/goon.db
railway variables set USER_DATA_DIR=/data/users
railway variables set ENABLE_TEST_BUSINESSES=false
```

### 10e. Add Dockerfile (if not present)
Create `Dockerfile` in the repo root:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ app/

# Data directory will be mounted as a Railway volume at /data
RUN mkdir -p /data/users

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 10f. Add Custom Domain
```bash
railway domain add api.holdplz.ai
# Railway will give you a CNAME target — add it to your DNS
```

### 10g. Deploy
```bash
railway up
# Or connect to GitHub for auto-deploy on push to main:
railway service connect
```

### 10h. Verify
```bash
curl https://api.holdplz.ai/health
# → {"status": "ok"}
```

---

## 11. Canary / Staging / Production Pattern

This is the deployment workflow for safe, testable releases.

### Architecture

```
                  ┌─────────────────┐
  Your phone ───► │  CANARY         │  canary.holdplz.ai
  Test accounts   │  (staging env)  │  Separate Railway service
                  │  Own SQLite DB  │  Own volume, own env vars
                  └─────────────────┘

                  ┌─────────────────┐
  All users ────► │  PRODUCTION     │  api.holdplz.ai
                  │  (prod env)     │  Main Railway service
                  │  Prod SQLite DB │  Prod volume
                  └─────────────────┘
```

### Setup: Create Staging Environment

Railway has first-class Environment support:

```bash
# In your Railway project:
railway environment create staging
```

This clones the production service config. Then customize:

```bash
railway environment use staging

# Override env vars for staging
railway variables set BASE_URL=https://canary.holdplz.ai
railway variables set ENABLE_TEST_BUSINESSES=true
railway variables set DATABASE_URL=sqlite:///data/goon-staging.db

# Add staging custom domain
railway domain add canary.holdplz.ai
```

### Workflow: Canary Deploy

```
1. Push code to a feature branch
2. Deploy to canary:
   git push origin feature-branch
   railway environment use staging
   railway up

3. Update Twilio webhooks for YOUR number only:
   - Go to Twilio Console
   - Your personal number → point webhooks at canary.holdplz.ai
   - (All other users still hit api.holdplz.ai)

4. Test:
   - Text the Goon number from your phone
   - Traffic routes through canary
   - Other users are unaffected on production

5. Promote to production:
   - Merge feature branch to main
   - railway environment use production
   - railway up (or auto-deploys from GitHub)
   - Point your Twilio webhooks back to api.holdplz.ai
```

### Advanced: Per-Account Canary Routing

For testing with multiple accounts without touching Twilio:

Add a canary check in the SMS webhook that routes specific phone numbers
to a different orchestrator config or feature flags. This is a code change
(not an infra change) and gives you fine-grained control:

```python
# In app/routes/sms.py — example canary routing
CANARY_PHONES = {"+1XXXXXXXXXX", "+1YYYYYYYYYY"}  # from env var

if sender in CANARY_PHONES:
    # Use canary-specific config, feature flags, etc.
    ...
```

### Promoting a Build

```
Feature Branch ──► Canary (staging env) ──► Test ──► Merge to main ──► Production
     │                    │                              │
     │                    ▼                              ▼
     │              canary.holdplz.ai              api.holdplz.ai
     │              Your phone only                All users
     │
     └── If broken: revert branch, redeploy staging. Zero prod impact.
```

---

## 12. Seed Your Test User

After the production database is created on first deploy:

```bash
# SSH into Railway (or run via railway run)
railway run python -c "
import sqlite3, sys
conn = sqlite3.connect('/data/goon.db')
conn.execute('''
  INSERT OR IGNORE INTO users (id, phone, name, email,
    subscription_status, allowlisted)
  VALUES ('+1XXXXXXXXXX', '+1XXXXXXXXXX', 'Riley',
    'rileycrane@gmail.com', 'active', 1)
''')
conn.commit()
print('User seeded')
"
```

Replace `+1XXXXXXXXXX` with your actual phone number in E.164 format.

---

## 13. Wire Up Webhooks

Now that the server is deployed, point all services at it.

### Twilio
Console → Phone Numbers → Your Goon Number:
- **SMS webhook**: `POST https://api.holdplz.ai/sms/webhook`
- **Voice webhook**: `POST https://api.holdplz.ai/voice/webhook`

### Vapi
Dashboard → Your Assistant → Server URL:
- `https://api.holdplz.ai/vapi/events`

Also set in env:
```env
VAPI_SERVER_URL=https://api.holdplz.ai/vapi/events
```

### Stripe
Developers → Webhooks → Your Endpoint:
- `https://api.holdplz.ai/stripe/webhook`
- (Already configured in Step 8c, but verify the URL matches)

---

## 14. First Test

### Smoke Test (no external services)
```bash
curl https://api.holdplz.ai/health
# → {"status": "ok"}
```

### SMS Test
Text the Goon number from your phone:
```
What time does Whole Foods close?
```
Expected: A response with real hours from Google Places, no phone call.

### Full Circuit Test (with test businesses)
1. Set `ENABLE_TEST_BUSINESSES=true` on canary
2. Text: `Book me a table at Riley's Pizza for 2 tonight at 7`
3. Goon should reply it's calling
4. Your Google Voice phone rings — answer as the restaurant
5. You get an SMS with the reservation result

### Full Integration Test
```bash
cd ~/gt/goon/mayor/rig
uv run python scripts/integration_test.py
```
Walks through all 7 scenarios with two phones.

---

## 15. Litestream Backup

SQLite on a single volume = single point of failure. Add Litestream
to continuously replicate your database to cloud storage.

### 15a. Create Backblaze B2 Bucket
1. Sign up at https://www.backblaze.com/b2
2. Create a bucket: `goon-db-backups`
3. Create an Application Key with read/write access to that bucket
4. Note: Key ID, Application Key, Bucket Name, Endpoint

### 15b. Add Litestream to Dockerfile
```dockerfile
# Add to Dockerfile
RUN apt-get update && apt-get install -y wget && \
    wget https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.deb && \
    dpkg -i litestream-v0.3.13-linux-amd64.deb && \
    rm litestream-v0.3.13-linux-amd64.deb

COPY litestream.yml /etc/litestream.yml
```

### 15c. Create litestream.yml
```yaml
dbs:
  - path: /data/goon.db
    replicas:
      - type: s3
        bucket: goon-db-backups
        path: replica
        endpoint: https://s3.us-west-000.backblazeb2.com
        access-key-id: ${LITESTREAM_ACCESS_KEY_ID}
        secret-access-key: ${LITESTREAM_SECRET_ACCESS_KEY}
```

### 15d. Update CMD to run Litestream as supervisor
```dockerfile
CMD ["litestream", "replicate", "-exec", "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

Litestream runs as the parent process, starts uvicorn as a child,
and continuously streams SQLite WAL changes to B2.

### 15e. Add env vars to Railway
```bash
railway variables set LITESTREAM_ACCESS_KEY_ID=xxxxxxxx
railway variables set LITESTREAM_SECRET_ACCESS_KEY=xxxxxxxx
```

---

## 16. Voice Platform Decision

### Vapi vs 11Labs: They're Different Layers

**11Labs** = text-to-speech engine. Converts text to natural-sounding audio.

**Vapi** = voice call orchestration platform. Wires together:
- STT (Deepgram) — transcribes what the business says
- LLM (Claude) — decides what to say next
- TTS (11Labs) — speaks the response
- Telephony (Twilio SIP) — manages the actual phone call
- Turn-taking — detects when someone stops talking
- Interruption handling — stops speaking if interrupted

**You're already using both correctly.** Vapi orchestrates the call; 11Labs
provides the voice inside Vapi. They're not alternatives to each other.

### Should You Stay on Vapi?

**Yes, for now.** Here's the comparison:

| | Vapi | Retell.ai | Bland.ai | DIY (Twilio+Deepgram+11Labs+Claude) |
|---|---|---|---|---|
| Cost/min (all-in) | $0.16-0.26 | $0.14-0.20 | $0.15-0.25 | $0.08-0.14 |
| Latency | 550-800ms | 400-600ms | 600-900ms | 700-1400ms |
| Claude support | Native | Native | Limited | Native |
| 11Labs voices | Native | Limited | Limited | Native |
| Turn-taking | Handled | Handled | Handled | You build it |
| Setup time | Hours | Hours | Hours | Weeks |

**Recommendation:**
- Stay on Vapi through v0 and early users
- Benchmark Retell.ai as a backup — lower latency, reportedly more stable
- Do NOT build DIY unless Vapi fees exceed $5K/month
- The turn-taking problem alone is a multi-week engineering effort

### Risk: Vapi Breaking Changes
Vapi has a pattern of pushing updates that break production agents.
Mitigate by pinning your Vapi API version and testing on canary first.

---

## 17. Hosting Decision

### Why Railway (For Now)

| Requirement | Railway | Fly.io | Hetzner VPS | AWS Fargate |
|---|---|---|---|---|
| Persistent disk (SQLite) | Volume ($0.25/GB) | Volume ($0.15/GB) | Local disk (free) | EFS (SQLite issues) |
| Always-on webhooks | Yes | Yes | Yes | Yes |
| Background cron (APScheduler) | Yes | Yes | Yes | Yes |
| Custom domain + SSL | Auto | Auto | Manual (nginx+certbot) | ALB ($18/mo base) |
| Staging environments | First-class | Separate app | Separate VPS | CodeDeploy canary |
| Setup time | 30 min | 45 min | 2-3 hours | 1-2 days |
| Monthly cost (small) | $10-15 | $5-10 | $5 | $40-60 |
| Horizontal scaling | Limited (SQLite) | LiteFS multi-region | Manual | Auto-scaling |

**Railway wins on developer experience.** Environments, auto-deploy from
GitHub, zero nginx config, logs in the dashboard. For 1-1000 users with
SQLite, it's the right call.

### When to Migrate

| User Count | Platform | Why |
|---|---|---|
| 1-1,000 | **Railway** | Simple, cheap, fast iteration |
| 1,000-10,000 | **Fly.io + LiteFS** | Multi-region SQLite, better pricing |
| 10,000+ | **AWS or Fly.io + Postgres** | Migrate to Postgres, horizontal scaling |

### Cost-Optimized Alternative: Hetzner VPS

If Railway's $10-15/month feels unnecessary when a $5/month Hetzner CX22
(2 vCPU, 4GB RAM) can run the entire stack:

- Pro: 3x cheaper, full control, SQLite just works on local disk
- Con: You manage nginx, SSL (certbot), systemd, deploys, monitoring
- Good for: experienced ops person who wants to minimize spend
- Bad for: moving fast and iterating on product, not infra

---

## 18. Scaling Roadmap

```
NOW (1-10 users)
├── Railway (single instance)
├── SQLite on volume
├── Litestream backups to B2
└── Canary via Railway Environments

SOON (10-500 users)
├── Same setup, works fine
├── Monitor SQLite write contention
├── Add error alerting (PagerDuty/SMS)
└── Unit economics dashboard

LATER (500-5,000 users)
├── Consider Fly.io + LiteFS for multi-region
├── SQLite still works for reads
├── Watch for write bottlenecks
└── Start evaluating Postgres migration

EVENTUALLY (5,000+ users)
├── Migrate to Postgres (Supabase, Neon, or managed)
├── Horizontal scaling unlocked
├── Any platform works (Railway, Fly, AWS)
└── Consider self-hosted voice stack if Vapi costs > $5K/mo
```

---

## Complete .env Template

```env
# === Twilio ===
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
GOON_NUMBER=

# === Vapi ===
VAPI_API_KEY=
VAPI_PHONE_NUMBER_ID=
VAPI_ASSISTANT_ID=
VAPI_SERVER_URL=  # e.g., https://api.holdplz.ai/vapi/events

# === Anthropic ===
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929

# === Google Places ===
GOOGLE_PLACES_API_KEY=

# === Tavily (Web Search) ===
TAVILY_API_KEY=

# === Stripe ===
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID=

# === Database & Storage ===
DATABASE_URL=sqlite:///data/goon.db
USER_DATA_DIR=/data/users

# === Server ===
BASE_URL=https://api.holdplz.ai
ADMIN_PASSWORD=

# === Test Mode ===
ENABLE_TEST_BUSINESSES=false
TEST_BUSINESS_PHONE=
TEST_MODE_LOG_VERBOSE=false

# === Litestream (SQLite backup) ===
LITESTREAM_ACCESS_KEY_ID=
LITESTREAM_SECRET_ACCESS_KEY=
```

---

## Quick Start Summary

If you just want to get to "I can text the number and it works":

```
1. Create accounts: Twilio, Vapi, Anthropic, Google Cloud, Tavily
2. Buy Twilio number, import into Vapi
3. railway init && railway volume create --mount /data
4. Set all env vars in Railway
5. railway up
6. Point Twilio webhooks at your Railway URL
7. Seed yourself as a user (allowlisted=1)
8. Text the number: "What time does Whole Foods close?"
9. If that works → test a voice call with test businesses enabled
```

Total time: ~2-3 hours if accounts approve quickly.
Total monthly cost to start: ~$15-25/month (Railway + Twilio + API usage).

---

*Last updated: 2026-03-01*
