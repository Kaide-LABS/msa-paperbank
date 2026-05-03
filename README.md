# MSA Paperbank

A simple WhatsApp past-paper retrieval bot for PAU students.

## Running Locally
1. Copy `.env.example` to `.env` and fill in your values.
2. Run `pip install -r requirements.txt`.
3. Set up the DB by running `psql -f migrations/001_init.sql`.
4. Run the app: `uvicorn app.main:app --reload`.

## Deploying
Use the provided Dockerfile or deploy to Cloud Run using `env.yaml`.