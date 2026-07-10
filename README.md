# MoMo SMS Data Analytics

An enterprise-level fullstack application that processes Mobile Money (MoMo) SMS
data delivered as XML, cleans and categorizes it, stores it in a relational
(SQLite) database, and exposes a frontend dashboard to analyze and visualize the
transactions.

> **Note on team setup:** This project is being completed **individually**. Due
> to a registration timing issue, I was added to this class after it began and
> granted an extension by the instructor to complete the assignments solo. All
> "team" requirements (collaborators, member list) are therefore fulfilled by a
> single contributor.

## Team / Author

| Role | Name |
|------|------|
| Sole contributor | `<Evan Ndahiro` |

## Project Description

The system ingests raw MoMo SMS records (XML), runs them through an ETL pipeline
(parse → clean/normalize → categorize → load), persists structured records in
SQLite, exports aggregated data to JSON, and renders an interactive dashboard.
An optional FastAPI layer can serve the same data over HTTP.

## High-Level Architecture



A shareable/editable version of the diagram: `<https://mermaid.ai/app/projects/3d2a65bb-3a95-4601-a125-f033d55a8f46/diagrams/abd94c12-1398-41bb-96f9-07426ab78ef4/version/v0.1/edit>`

## Project Structure

```
.
├── README.md              # Setup, run, overview
├── .env.example           # DATABASE_URL / paths
├── requirements.txt       # lxml, dateutil, (FastAPI optional)
├── index.html             # Dashboard entry (static)
├── web/                   # Frontend styling + chart rendering
├── data/                  # raw (git-ignored), processed JSON, SQLite DB, logs
├── etl/                   # parse → clean → categorize → load → export
├── api/                   # Optional FastAPI (bonus)
├── scripts/               # Shell helpers to run ETL / export / serve
└── tests/                 # Unit tests
```

## Scrum Board

Task tracking is managed on a Scrum board (To Do / In Progress / Done):

`<SCRUM BOARD LINK>`

## Getting Started

> The application logic is scaffolded and will be implemented in the coming
> weeks. Setup steps below describe the intended workflow.

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/momo-data-analytics.git
cd momo-data-analytics

# 2. Create a virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# 4. Run the ETL pipeline (once implemented)
bash scripts/run_etl.sh

# 5. Serve the dashboard
bash scripts/serve_frontend.sh   # http://localhost:8000
```

## Tech Stack

- **Backend / ETL:** Python (ElementTree / lxml, python-dateutil)
- **Database:** SQLite
- **Frontend:** HTML, CSS, vanilla JavaScript
- **API (optional):** FastAPI + Uvicorn

---

# MoMo SMS Data Analytics — Database (Week 2)

> **Note on team setup:** This project is being completed **individually** due
> to a registration timing issue; extension granted by the instructor.

This directory contains the database design and implementation for the MoMo
Analytics system. Week 1 produced the project scaffolding; Week 2 turns
that scaffolding into a working, queryable relational database.

## What lives where

```
database/
  database_setup.sql        MySQL 8.0 script — creates schema + sample data
docs/
  erd_diagram.png           Entity Relationship Diagram (PNG)
  Database_Design_Document.pdf   Full design writeup with query screenshots
examples/
  json_schemas.json         API-facing JSON representation of each entity
screenshots/
  *.png                     Query and constraint-test screenshots
AI_USAGE_LOG.md             Transparent record of how AI was used
```

## Running the SQL script

You'll need MySQL 8.0+ or MariaDB 10.5+. From the repo root:

```bash
mysql -u root -p < database/database_setup.sql
```

The script is idempotent — it drops and recreates the `momo_analytics`
database each run, so you can iterate freely. After it completes:

```bash
mysql -u root -p momo_analytics -e "SHOW TABLES;"
```

You should see six tables: `users`, `transaction_categories`,
`transactions`, `tags`, `transaction_tags`, and `system_logs`.

## Schema at a glance

| Table                    | Purpose                                                                 |
|--------------------------|-------------------------------------------------------------------------|
| `users`                  | People appearing as senders or receivers in SMS                         |
| `transaction_categories` | The 8 transaction types identified in the XML (Incoming Money, etc.)    |
| `transactions`           | Main fact table — one row per parsed SMS                                |
| `tags`                   | Analyst-defined labels (`high_value`, `merchant`, `needs_review`, …)    |
| `transaction_tags`       | **M:N junction** between transactions and tags                          |
| `system_logs`            | ETL activity log with optional link back to a transaction               |

The full ERD is at `docs/erd_diagram.png` and the design rationale is in
`docs/Database_Design_Document.pdf`.

## Design choices worth calling out

1. **Users are normalized.** The same person shows up in dozens of SMS. Storing
   a name once and referencing it by `user_id` keeps updates cheap and prevents
   drift (e.g. `Jane Smith` vs `Jane  Smith`).
2. **`transaction_tags` resolves the M:N cardinality.** A transaction can carry
   many tags, and a tag applies to many transactions. The junction table stores
   `(transaction_id, tag_id)` as a composite primary key, plus `applied_at` and
   `applied_by` for audit.
3. **CHECK constraints reject bad data at the DB layer.** Negative amounts,
   invalid phone formats, malformed hex colors — all rejected before they touch
   the analytics layer. See the constraint tests in the PDF.
4. **Nullable sender/receiver.** Bank deposits have no sender; airtime and
   withdrawals have no receiver. The FKs are `ON DELETE SET NULL` so the
   history survives if a user record is later removed.
5. **Portable enforcement via triggers.** MySQL 8 allows column-vs-column
   comparisons inside CHECK constraints; some MariaDB versions don't. The
   "sender ≠ receiver" rule is enforced by BEFORE INSERT/UPDATE triggers so the
   script runs on both.

## JSON serialization

`examples/json_schemas.json` shows how each entity would be serialized for an
API response. The `complete_transaction` example demonstrates nested
serialization — foreign keys are expanded into full objects and the M:N tags
relation collapses into an inline array. This is the shape Assignment 3's REST
API will produce.

## Sample queries (all runnable)

The setup script ends with five sample queries that exercise the schema:

1. All transactions with human-readable category and party names
2. Volume per category (drives the dashboard's pie chart)
3. High-value transactions joined through the M:N tag relation
4. Recent ETL warnings and errors from `system_logs`
5. A demonstration UPDATE and DELETE showing safe CRUD

Screenshots of these queries running against real data live under `screenshots/`
and are embedded in the design document PDF.
