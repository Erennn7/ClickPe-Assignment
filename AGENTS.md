# AGENTS.md - Developer & Agent Guide: The Loan Eligibility Engine

Welcome to **The Loan Eligibility Engine** repository. This document serves as the single source of truth for AI agents, contributors, and evaluators detailing the architecture, design principles, code standards, and workflows.

---

## 1. System Vision & Architecture

The Loan Eligibility Engine is an automated, event-driven fintech platform designed to:
1. **Ingest Large-Scale Customer Data:** Reliably ingest 10,000+ customer records without hitting serverless API timeouts or memory ceilings by utilizing **S3 Presigned URLs** and **asynchronous streaming Lambda batch ingestion**.
2. **Autonomously Discover Loan Products:** Periodically crawl financial websites via an **n8n crawler workflow (Workflow A)**, using LLMs to extract unstructured web text into validated relational schemas.
3. **Execute High-Throughput Matching (The Optimization Treasure Hunt):** Solve the $N \times M$ combinatorial explosion using a **3-Stage Filtering Funnel**:
   - **Stage 1 (SQL Push-down):** PostgreSQL composite-indexed queries filter out 95% of invalid user-product combinations in $<100\text{ ms}$.
   - **Stage 2 (Heuristic Scoring & Top-K):** Memory-efficient JS/Python algorithmic scoring ranks products based on interest rates and credit margins, isolating the Top 3 options.
   - **Stage 3 (Targeted LLM Evaluation):** Batched LLM inference (20 pairs/prompt) generates personalized qualitative reasoning with minimal token spend.
4. **Notify Qualified Borrowers:** Format and dispatch personalized loan offers via **Amazon SES (Workflow C)** routed safely to verified test inboxes and email aliases (`user+one@gmail.com`).

---

## 2. Directory Layout & Key Modules

```
.
├── AGENTS.md                    # Core architecture and agent guidelines (this file)
├── README.md                    # Public documentation, setup instructions & diagrams
├── docker-compose.yml           # Self-hosted n8n + PostgreSQL 16 local stack
├── serverless.yml               # AWS Serverless Framework configuration
├── .env.example                 # Template for environment variables
├── requirements.txt             # Python backend dependencies
│
├── backend/
│   ├── db/
│   │   ├── schema.sql           # PostgreSQL schema, constraints, and composite indexes
│   │   └── seed_products.sql    # Baseline Indian banking personal loan products
│   ├── lambdas/
│   │   ├── presigned_url.py     # Lambda: Generates S3 presigned PUT URLs
│   │   ├── ingest_csv.py        # Lambda: Streams S3 CSV -> PostgreSQL batch insert
│   │   └── db_client.py         # Resilient DB connection pool & helpers
│   └── crawler/
│       └── scraper.py           # Web scraping engine for personal loan discovery
│
├── n8n_workflows/
│   ├── workflow_a_discovery.json    # n8n Workflow A: Web Crawler & LLM Parser
│   ├── workflow_b_matching.json     # n8n Workflow B: 3-Stage Matching Engine
│   └── workflow_c_notification.json # n8n Workflow C: SES Notification Dispatcher
│
├── frontend/
│   ├── index.html               # Minimal, responsive single-page portal
│   ├── app.js                   # Client-side S3 presigned uploader & status tracker
│   └── style.css                # Polished modern stylesheet
│
└── sample_data/
    └── users.csv                # 10,000-row sample user dataset
```

---

## 3. Database Schema Overview

The database uses PostgreSQL 16 with the following core entities:

- **`ingestion_batches`**: Tracks CSV upload transactions, total row count, status (`PENDING`, `COMPLETED`, `FAILED`), and processing duration.
- **`users`**: Ingested customer records (`user_id`, `name`, `email`, `monthly_income`, `credit_score`, `employment_status`, `age`, `batch_id`).
  - *Composite Index:* `idx_users_eligibility ON users(credit_score, monthly_income, age, employment_status)`.
- **`loan_products`**: Bank offerings (`product_id`, `product_name`, `provider_name`, `interest_rate`, `min_income`, `min_credit_score`, `min_age`, `max_age`, `eligible_employment_status`, `features`, `source_url`, `is_active`).
- **`matches`**: Approved user-product pairings (`match_id`, `user_id`, `product_id`, `batch_id`, `match_score`, `reasoning`, `notification_status`).

---

## 4. Coding & Architecture Standards

1. **Event-Driven Over Monolithic:** Never accept large file payloads directly in Lambda/API Gateway. Always upload directly to S3 via presigned URLs.
2. **Database Push-Down:** Push mathematical and set-filtering operations down to PostgreSQL using indexed queries rather than loading thousands of unindexed records into Node.js / Python memory.
3. **Idempotency & Upserts:** All ingestion and crawling pipelines must be idempotent. Use `ON CONFLICT` clauses to handle retries gracefully without creating duplicate records.
4. **Environment Isolation:** Never hardcode credentials, endpoints, or keys. Always load configuration via environment variables.
5. **Safety in Notifications:** In development and test phases, never send emails to arbitrary domains found in test CSVs. Route all outgoing emails to verified test aliases (`username+one@gmail.com`).

---

## 5. Development & Testing Commands

- **Start Local Services:**
  ```bash
  docker compose up -d
  ```
- **Access n8n Editor:**
  `http://localhost:5678`
- **Execute Local Migration:**
  ```bash
  psql postgresql://postgres:postgres@localhost:5432/loan_engine -f backend/db/schema.sql
  psql postgresql://postgres:postgres@localhost:5432/loan_engine -f backend/db/seed_products.sql
  ```
- **Run Ingestion Locally / Lambda Test:**
  ```bash
  python3 backend/lambdas/ingest_csv.py --local-file sample_data/users.csv
  ```

---

## 6. Optimization Treasure Hunt Rationale

When discussing or demonstrating the matching pipeline:
- Highlight that comparing 10,000 users against 20 products creates 200,000 pairs.
- Demonstrate that **Stage 1 (SQL Push-down)** uses composite B-tree indexing to discard >90% of invalid pairs in $<100\text{ ms}$ at **$0.00** cost.
- Explain that **Stage 2 (Heuristic Scoring)** narrows candidate loans down to the Top 3 best rates for each user.
- Show that **Stage 3 (LLM Reasoning)** is executed on a compact, batched payload (20 items/prompt) to output personalized natural language explanations without triggering rate limits or excessive cost.
