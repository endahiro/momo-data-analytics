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
