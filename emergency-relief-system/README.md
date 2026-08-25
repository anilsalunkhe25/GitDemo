# AI-Based Emergency Relief Resource Allocation and Demand Forecasting System

A production-style MCA Minor Project II demonstration for humanitarian operations. The platform connects emergency requests, transparent prioritization, inventory, AI demand forecasts, allocation, delivery tracking, and analytics through a Flask REST API and Streamlit console.

## Features

- JWT authentication, hashed passwords, and role-based access for administrators, relief-center operators, and logistics volunteers.
- Emergency and affected-area management, request approval, explainable 0-100 priority scoring, and status workflows.
- Multi-center inventory with capacity checks, expiry protection, reservation, transfers, and a transaction ledger.
- Priority-aware partial allocation and delivery events.
- Real Scikit-learn training pipeline comparing Linear Regression, Random Forest, and Gradient Boosting using MAE, RMSE, and R2.
- Forecast shortage calculation and recommendations explicitly marked `AI Recommendation - Human Review Required`.
- Streamlit operational dashboard backed only by Flask APIs.

## Stack and architecture

Python, Flask, SQLAlchemy, MySQL, Flask-JWT-Extended, Streamlit, Pandas, NumPy, Scikit-learn, Joblib, Pytest, and Docker Compose. See [docs/architecture.md](docs/architecture.md), [docs/api.md](docs/api.md), and [docs/ai_model.md](docs/ai_model.md).

## Local setup

```bash
cd emergency-relief-system
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m backend.ml.generate_dataset
python -m backend.ml.train_model
python -m backend.seed
```

The default development configuration uses `data/emergency_relief_dev.db` for a zero-setup demo. To use MySQL, set `DATABASE_URL=mysql+pymysql://user:password@localhost:3306/emergency_relief_db` in `.env`, create the database with `database/schema.sql`, then run the seed command.

Start the API and UI in separate terminals:

```bash
python run.py
streamlit run frontend/app.py
```

Open `http://localhost:8501`; the API health endpoint is `http://localhost:5000/health`.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Compose exposes MySQL on `3306`, Flask on `5000`, and Streamlit on `8501`. After the first startup, seed the backend container with `docker compose exec backend python -m backend.seed`; train with `docker compose exec backend python -m backend.ml.train_model`.

## Tests and demo credentials

```bash
pytest -q
```

The idempotent seed creates:

- `admin@relief.local` (ADMIN)
- `operator1@relief.local` and `operator2@relief.local` (RELIEF_CENTER_OPERATOR)
- `volunteer1@relief.local`, `volunteer2@relief.local`, and `volunteer3@relief.local` (VOLUNTEER_LOGISTICS)

All seeded accounts use `Admin@123`. Change credentials before any real deployment.

## Workflow

Login -> create or review an emergency -> register an affected area -> create a relief request -> calculate explainable priority -> inspect non-expired inventory -> generate and review the AI forecast -> allocate available stock (possibly partially) -> create delivery -> update delivery events -> inspect dashboard and analytics.

## Responsible AI and limitations

The checked-in dataset is synthetic demonstration data, not real disaster-response data. Model metrics describe only that dataset and are not a guarantee of field accuracy. Forecasts are recommendations; critical allocation decisions require human approval and the application records forecast review. Future work includes calibrated uncertainty intervals, real validated consumption feeds, geospatial routing, database migrations, audit exports, and production observability.
