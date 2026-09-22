# MBA Reading Stand & Book Tracking System

A Flask + SQLAlchemy + Jinja2 + Bootstrap application for tracking the MBA department's physical reading stands, book views, student activity, and loans.

## Features

- Seeded inventory for 14 stands across floors 3 and 4 (one stand contains 7 books; the others contain 6).
- Unique book IDs and dynamically generated QR codes for every title.
- Student-aware QR view logging with scan counts.
- Borrow and return workflow with timestamps and loan duration.
- Dashboard metrics for availability, checkouts, scans, popular books, floor activity, and recent events.
- Searchable book inventory, stand inventory, student-wise activity, book-level audit trails, and complete activity history.
- MySQL support through `DATABASE_URL`, with SQLite as the default for local development.
- Flask-Login authentication for the resource desk, with public QR scan pages.
- Flask-Migrate integration for future schema migrations.
- Chart.js floor and stand interaction statistics.

## Run locally

1. Install Python 3.11+ and create a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set `SECRET_KEY`, `ADMIN_PASSWORD`, and `DATABASE_URL`.

   MySQL example:

   ```text
   mysql+pymysql://mba_user:password@localhost/mba_reading_stand
   ```

   SQLite example:

   ```text
   sqlite:///mba_reading_stand.db
   ```

3. Start the application directly on Windows:

   ```powershell
   python app.py
   ```

The first start creates the tables, creates the local `admin` user, and seeds the 14 reading stands and their books. Open `http://127.0.0.1:5000` and sign in with `admin` and the value of `ADMIN_PASSWORD`.

## GitHub and Render deployment

The repository includes `render.yaml` and a production `Procfile`. Create a GitHub repository, push this project, then create a Render Web Service from the repository. Set these environment variables in Render:

- `SECRET_KEY`: a long random value
- `ADMIN_PASSWORD`: a strong administrator password
- `DATABASE_URL`: a MySQL SQLAlchemy URL such as `mysql+pymysql://user:password@host/database`

Render uses `waitress-serve` as the production WSGI server. Do not commit `.env`, local SQLite databases, or the `instance/` directory.

## Production notes

- Set a strong `SECRET_KEY` and use MySQL in production.
- Put the app behind a production WSGI server such as Waitress or Gunicorn.
- Add department authentication before exposing administration routes publicly.
- QR codes encode absolute URLs based on the request host, so the deployed domain should be used when downloading final labels.