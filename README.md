# OptiScale: High-Throughput A/B Testing & Experimentation Engine

A production-grade, distributed A/B testing and experimentation platform engineered for sub-millisecond variant routing, consistent hashing, resilient multi-tier caching, and mathematically rigorous statistical inference.

---

## Architecture Overview

```
                          ┌──────────────────────────┐
                          │   Client / Browser / App │
                          └────────────┬─────────────┘
                                       │ HTTP
                                       ▼
                          ┌──────────────────────────┐
                          │  FastAPI Routing Engine  │
                          └──────┬────────────┬──────┘
                                 │            │
            1. Cache Probe (<2ms)│            │ 2. DB Fallback & Write-back
                                 ▼            ▼
                   ┌─────────────────┐    ┌─────────────────┐
                   │   Redis 7 L1    │    │  PostgreSQL 16  │
                   │ (24hr TTL Cache)│    │  (ACID Storage) │
                   └─────────────────┘    └─────────────────┘
```

- **Consistent Hashing**: Deterministic user routing using MD5 hex partition mapping across 10,000 buckets. A user always maps to the same variant without requiring pre-computed assignment tables.
- **Multi-Tier Assignment Caching**:
  1. **L1 (Redis)**: Sub-millisecond lookup (`assignment:{exp_id}:{user_id}`).
  2. **L2 (PostgreSQL)**: Fallback on cache miss with write-back to Redis.
  3. **Idempotent Computation**: On first visit, consistent hash computes the variant, inserts with `ON CONFLICT DO NOTHING`, and sets the Redis key with a 24-hour TTL.
- **Statistics Engine**: Two-sample pooled z-test for difference in proportions, two-sided p-values, 95% unpooled confidence intervals, and a sample size guard to prevent false positives from early peeking.

---

## Tech Stack & Dependencies

| Layer | Technology | Key Dependencies & Purpose |
|---|---|---|
| **Backend** | Python 3.13, FastAPI | `fastapi`, `uvicorn` (ASGI), `pydantic-settings` (Config validation) |
| **Storage & ORM** | PostgreSQL 16, SQLAlchemy | `sqlalchemy` (Connection pooling), `psycopg2-binary`, `alembic` (Migrations) |
| **Caching** | Redis 7 | `redis` (Connection pool with graceful offline fallback) |
| **Analytics** | SciPy, NumPy | `scipy.stats.norm` (Z-test, p-values, confidence intervals) |
| **Frontend** | React 18, Vite | Vanilla CSS design tokens, `lucide-react` (Crisp iconography) |
| **Infra** | Docker Compose | Multi-container orchestration with dependency healthchecks |

---

## Quickstart Guide

### Option 1: Docker Compose (One-Command Startup)

Prerequisites: [Docker Desktop](https://www.docker.com/) running.

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/AB-Testing-Platform.git
cd AB-Testing-Platform

# 2. Boot all services (PostgreSQL, Redis, FastAPI Backend, React Frontend)
docker-compose up --build
```

- **React Dashboard**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Healthcheck**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Option 2: Local Development (Virtual Environment)

#### 1. Start Database and Cache
```bash
docker run -d --name test_pg -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ab_testing postgres:16-alpine
docker run -d --name test_redis -p 6379:6379 redis:7-alpine
```

#### 2. Setup Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

#### 3. Run Database Migrations
```bash
python scripts/run_migrations.py
```

#### 4. Start Backend Server
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

#### 5. Start React Frontend
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```

---

## API Endpoints & cURL Examples

### 1. Create an Experiment
```bash
curl -X POST http://localhost:8000/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Checkout CTA Color Test",
    "variants": [
      {"name": "control", "weight": 50},
      {"name": "treatment", "weight": 50}
    ]
  }'
```

**Response (201 Created):**
```json
{
  "id": 1,
  "name": "Checkout CTA Color Test",
  "variants": [
    {"name": "control", "weight": 50.0},
    {"name": "treatment", "weight": 50.0}
  ],
  "status": "active",
  "created_at": "2026-09-20T11:20:00Z"
}
```

### 2. Assign User to a Variant
```bash
curl "http://localhost:8000/assign?experiment_id=1&user_id=user_alpha_42"
```

**Response (200 OK):**
```json
{
  "experiment_id": 1,
  "user_id": "user_alpha_42",
  "variant": "treatment",
  "from_cache": false
}
```
*Calling the same endpoint again with the same `user_id` returns `"from_cache": true` in under 1 millisecond.*

### 3. Track a Conversion Event
```bash
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": 1,
    "user_id": "user_alpha_42",
    "event_type": "conversion"
  }'
```

**Response (201 Created):**
```json
{
  "id": 1,
  "experiment_id": 1,
  "user_id": "user_alpha_42",
  "variant": "treatment",
  "event_type": "conversion",
  "timestamp": "2026-09-20T11:20:15Z"
}
```

### 4. Fetch Statistical Results
```bash
curl http://localhost:8000/experiments/1/results
```

---

## Seed & Load Test Benchmark Script

The repository includes a load testing and latency benchmarking script (`scripts/seed_load_test.py`) that:
1. Measures the latency difference between Redis cache hits vs cold PostgreSQL queries.
2. Simulates concurrent user traffic across variants with real conversion gaps.
3. Automatically evaluates two-sample proportion z-scores, p-values, and peeking guards.

### Running the Load Test
```bash
# Activate virtual environment
source venv/bin/activate

# Run simulation with 5,000 users (10% control CVR vs 14% treatment CVR)
python scripts/seed_load_test.py --users 5000 --control-cvr 0.10 --treatment-cvr 0.14
```

### Example Benchmark Output
```
============================================================
LATENCY BENCHMARK: Cold (DB Fallback) vs Warm (Redis Cache)
============================================================
Sample Size: 200 requests per condition
Metric     | Cold / DB (ms)   | Warm / Redis (ms) | Speedup   
------------------------------------------------------------
Mean       |           4.82 ms |           0.91 ms |     5.30x
p50        |           4.15 ms |           0.82 ms |     5.06x
p95        |           7.63 ms |           1.34 ms |     5.69x
p99        |          11.20 ms |           1.88 ms |     5.96x
============================================================

Simulating 5,000 users with 20 worker threads...
Target True CVR: Control = 10.0%, Treatment = 14.0%
Progress: 5,000/5,000 users (100%) - 412.3 req/s
Simulation completed in 12.12s (412.5 users/sec).

======================================================================
FINAL EXPERIMENT RESULTS: Checkout Flow Redesign (ID: 1)
======================================================================
Variant      | Weight   | Sample Size  | Conversions  | Conversion Rate 
----------------------------------------------------------------------
control      | 50       | 2,514        | 258          |          10.26%
treatment    | 50       | 2,486        | 351          |          14.12%
----------------------------------------------------------------------
STATISTICAL INFERENCE (Two-sample proportion Z-test):
Comparison: treatment vs control
  - Absolute Difference:   +3.86%
  - Relative Lift:         +37.60%
  - Z-Statistic:           4.1284
  - P-Value:               0.00004
  - 95% Conf. Interval:    [+2.03%, +5.69%]
  - Peeking Guard Active:  False
  - Statistically Signif:  True
  - Conclusion:            Statistically significant result detected at 95% confidence level (p = 0.00004 < 0.05).
======================================================================
```

---

## Verifying Redis Caching Directly

To verify that Redis is actively intercepting and caching assignments:

```bash
# Connect to Redis CLI in container
docker exec -it ab_redis redis-cli

# 1. Check cached assignment keys
KEYS "assignment:*"

# 2. Inspect a specific user's cached assignment
GET "assignment:1:user_alpha_42"
# Output: "treatment"

# 3. Check remaining Time-To-Live (in seconds)
TTL "assignment:1:user_alpha_42"
# Output: e.g. 86380
```

---

## Statistical Verification (Manual Math Sanity Check)

To verify the mathematical accuracy of the statistics engine by hand or via standalone Python:

### Sample Dataset
- **Control**: $n_1 = 1,000$ visitors, $x_1 = 100$ conversions $\implies \hat{p}_1 = 0.10$
- **Treatment**: $n_2 = 1,000$ visitors, $x_2 = 140$ conversions $\implies \hat{p}_2 = 0.14$

### Mathematical Steps
1. **Pooled Proportion**:
   $$p_{pool} = \frac{x_1 + x_2}{n_1 + n_2} = \frac{100 + 140}{2000} = 0.12$$

2. **Standard Error (Pooled)**:
   $$SE_{pool} = \sqrt{0.12 \times 0.88 \times \left(\frac{1}{1000} + \frac{1}{1000}\right)} = \sqrt{0.1056 \times 0.002} \approx 0.0145327$$

3. **Z-Statistic**:
   $$Z = \frac{0.14 - 0.10}{0.0145327} \approx 2.7524$$

4. **Two-Tailed P-Value**:
   $$p = 2 \times (1 - \Phi(2.7524)) \approx 0.00592$$
   *Since $p = 0.00592 < 0.05$ and $n_1, n_2 \ge 100$, the test correctly concludes statistical significance.*

5. **95% Confidence Interval**:
   $$SE_{unpooled} = \sqrt{\frac{0.10 \times 0.90}{1000} + \frac{0.14 \times 0.86}{1000}} \approx 0.014505$$
   $$MOE = 1.95996 \times 0.014505 \approx 0.02843$$
   $$CI = [0.04 - 0.02843, 0.04 + 0.02843] = [+1.16\%, +6.84\%]$$

Run this one-line command to verify:
```bash
python3 -c "
from app.stats import calculate_two_sample_z_test
res = calculate_two_sample_z_test(1000, 100, 1000, 140)
print(res)
"
```

---

## Troubleshooting Common Issues

1. **Port Conflicts (`5432` or `6379` already in use)**:
   - If PostgreSQL or Redis is already running on your host machine, stop them (`brew services stop postgresql`, `brew services stop redis`) or modify the host port mappings in `docker-compose.yml` (e.g. `"5433:5432"`).
2. **Database Migration Not Run**:
   - If starting outside Docker, run `python scripts/run_migrations.py` to ensure tables and indexes exist.
3. **CORS Errors in React**:
   - The FastAPI backend includes `CORSMiddleware` configured with `allow_origins=["*"]`. Ensure your backend is reachable on port 8000.
