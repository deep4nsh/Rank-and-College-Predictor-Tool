# Physics Wallah (PW) In-House GATE Rank, College & PSU Predictor

> **Production-Grade, 100% Free Open-Source Architecture**  
> Zero paid software licenses, zero paid third-party APIs, and zero ongoing cloud subscriptions.

---

## 1. Executive Overview

The **Physics Wallah (PW) GATE Rank, College & PSU Predictor** is an in-house institutional platform designed to empower students and counselling operations immediately following the GATE examination.

### Core Architecture Highlights
* **Deterministic Mathematical Core:** Zero floating-point rounding errors via exact rational fractions. Strict MSQ zero partial marking, NAT numerical tolerance evaluation ($NAT_{min} \le V \le NAT_{max}$), and automated Marks-to-All (MTA) credit.
* **Official GATE Multi-Session Normalization:** Employs the official GATE formula with Interquartile Range (IQR) outlier scrubbing ($Q_1 - 2.5 \cdot \text{IQR}$ to $Q_3 + 2.5 \cdot \text{IQR}$) to immunize shift scoring against spam/troll submissions.
* **Monotonic PCHIP Spline AIR Prediction:** Guaranteed monotonicity ($\frac{d(AIR)}{d(Score)} < 0$) using Piecewise Cubic Hermite Interpolating Polynomials. A higher score will **never** receive a worse rank.
* **3-Tier Institutional College & PSU Matcher:** Multi-year weighted moving average ($50\% \cdot 2024 + 30\% \cdot 2023 + 20\% \cdot 2022$) matching candidates to IITs (COAP), NITs/IIITs (CCMT), and Maharatna/Navratna PSUs with PwD horizontal reservation, PSU age relaxations, and B.Tech % filtering.
* **3 Ingestion Channels:**
  1. *Mode A (Exam Day CBT Form):* 65-question interactive palette mimicking the real GATE CBT interface with virtual numeric keypad.
  2. *Mode B (TCS iON Digialm Scraper):* Automated HTML and live URL response sheet parser.
  3. *Mode C (Bulk CSV / TSV Import):* Batch ingestion for offline counselling drive leads.
* **Counsellor Operations CRM & Lead Priority Triage:**
  - Automated lead classification: `SUPER_TOPPER`, `PSU_AND_TOP_IIT`, `NIT_PROSPECT`, `NURTURE_REPEATER`.
  - Call disposition logging, follow-up scheduling, and chronological audit history.
  - **Laptop Workstation Contact Card:** Clicking candidate mobile numbers pops up an interactive contact card with 1-click clipboard copy and direct WhatsApp Web messaging (preventing OS dialer errors on laptops without telephony hardware).
  - 1-page PW-branded PDF diagnostic scorecards (ReportLab) and filtered CSV lead exports.
* **Exam-Day Key Revision & O(1) Batch Re-Evaluation:** Faculty keys (v1) published on exam day can be revised with Official IIT Keys (v2) to re-grade tens of thousands of student records in sub-second time using bulk pre-fetched queries.

---

## 2. Technology Stack

* **Backend:** Python 3.11+ / 3.12 / 3.14, FastAPI, Uvicorn, Pydantic v2
* **Mathematics & Science:** NumPy, SciPy (PCHIP Spline Interpolation), Fractions, Decimal
* **Database & Persistence:** SQLite with Write-Ahead Logging (WAL mode), QueuePool connection pooling, PRAGMA busy_timeout, foreign keys
* **Report Generation:** ReportLab (vector PDF generation with XML escaping)
* **HTML Scraping:** BeautifulSoup4, lxml
* **Frontend:** Responsive vanilla HTML5, Tailwind CSS, FontAwesome 6 (zero build step, zero npm dependency)
* **Testing:** Pytest (56 comprehensive unit, integration, and concurrency stress tests)
* **Cloud Ready:** Native Python cloud configuration (`Procfile`, `render.yaml`, `railway.json`)

---

## 3. Quickstart & Local Installation

### Prerequisites
* Python 3.11, 3.12, or 3.14
* Git

### Step 1: Clone and Set Up Virtual Environment
```bash
git clone https://github.com/physicswallah/Rank-and-College-Predictor-Tool.git
cd Rank-and-College-Predictor-Tool

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Run Automated Test Suite
```bash
pytest tests/ -v
```
All 56 tests will run in under 2 seconds.

### Step 3: Start Development Server
```bash
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```
Open your browser at `http://localhost:8000`.

---

## 4. Production Deployment

### Option A: 1-Click Cloud Platform (Render / Railway - 100% Cloud, Zero Local Load)
Deploy with zero container overhead directly from GitHub:
1. Push this repository to your GitHub account.
2. Sign in to **[Render.com](https://render.com)** or **[Railway.app](https://railway.app)**.
3. Select **New Web Service** $\to$ connect this repository.
4. It automatically detects native Python via `requirements.txt`, `Procfile`, and `render.yaml`.
5. Click **Deploy** to receive a live public HTTPS URL (e.g. `https://pw-gate-predictor.onrender.com`).

### Option B: Bare-Metal / Cloud VM Multi-Worker Startup (AWS EC2 / DigitalOcean)
```bash
chmod +x scripts/*.sh
./scripts/run_production.sh
```
This automatically detects CPU core count and launches Uvicorn with `(2 * CPU) + 1` worker processes, proxy headers enabled, and access logging.

### Option C: Online Zero-Downtime Database Backups
```bash
./scripts/backup_db.sh ./gate_predictor.db ./backups
```
Performs a live SQLite `.backup` checkpoint safe for use while concurrent write traffic is active, verifying file integrity (`PRAGMA integrity_check`) upon completion.

---

## 5. Concurrency & Stress Testing

Run the included standalone load benchmark tool:
```bash
# Simulates 200 concurrent student submissions across 10 parallel worker threads
python scripts/benchmark_stress_test.py --total 200 --workers 10
```
Outputs a real-time latency and throughput breakdown (min, mean, p50, p95, p99, req/sec).

---

## 6. Key API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Web Application UI (CBT Form, Digialm Parser, Counsellor Ops, Key Admin) |
| `GET` | `/api/health` | Service health status check |
| `POST` | `/api/v1/submissions` | Submit exam responses, auto-grade, and predict rank/score |
| `GET` | `/api/v1/submissions/{id}` | Retrieve submission scorecard and choice recommendations |
| `POST` | `/api/v1/keys` | Publish Answer Key (PW Faculty v1 or Official IIT v2) |
| `POST` | `/api/v1/keys/{key_id}/re-evaluate` | Re-evaluate all candidate records against revised answer key |
| `POST` | `/api/v1/ingest/parse-response-sheet-html` | Parse raw TCS iON Digialm HTML string |
| `POST` | `/api/v1/ingest/parse-response-sheet-url` | Scrape public Digialm response sheet URL |
| `POST` | `/api/v1/ingest/bulk-csv` | Bulk import offline drive leads (CSV/TSV direct score or Q1..Q65) |
| `GET` | `/api/v1/counsellor/students` | Search and filter leads (by negative marks, AIR, priority, disposition) |
| `POST` | `/api/v1/counsellor/students/{phone}/call-log` | Log counsellor call disposition, notes, and reminder dates |
| `GET` | `/api/v1/counsellor/students/{phone}/call-history` | Chronological audit trail of past call records |
| `GET` | `/api/v1/counsellor/students/{phone}/pdf` | Generate and download branded 1-page ReportLab PDF scorecard |
| `GET` | `/api/v1/counsellor/students/{phone}/whatsapp-summary` | Pre-formatted WhatsApp diagnostic text summary |
| `GET` | `/api/v1/counsellor/export/csv` | Export filtered candidate list to downloadable CSV |
| `GET` | `/api/v1/counsellor/analytics/lead-summary` | Real-time operational KPI metrics and funnel distribution |

---

## 7. License & Compliance
Proprietary institutional software developed for **Physics Wallah (PW)**. Built exclusively on permissive open-source libraries (MIT, BSD, Apache 2.0). Requires zero proprietary or paid third-party dependencies.
