# FlatMates Expense Tracker

A shared expense management app for flatmates — built with Django REST Framework 
and React. Handles split tracking, multi-currency expenses, time-scoped membership, 
and CSV import with anomaly detection.

## Live App
- Frontend: [URL after deployment]
- Backend API: [URL after deployment]

> [!NOTE]
> Render's free web services spin down after 15 minutes of inactivity. The first request after idling takes 30-50 seconds (cold start) while the container restarts. This is normal and expected behavior for the free tier.

## Tech Stack
| Component | Technology |
|---|---|
| Backend | Django 4.2 + Django REST Framework |
| Database | PostgreSQL 15 |
| Authentication | JWT (djangorestframework-simplejwt) |
| Frontend | React 18 + Vite + TailwindCSS |
| State Management | Zustand |
| FX Rates | Frankfurter API (free, historical) |
| Deployment | Render (backend), Supabase (PostgreSQL), Vercel (frontend) |

## AI Tool Used
Claude (Anthropic) — used for code generation, reviewed and corrected 
before every commit. See AI_USAGE.md.

## Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+

### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Fill in your values
createdb flatmates_db
python manage.py migrate
python manage.py seed_flatmates
python manage.py runserver
```

### Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env.development  # Set VITE_API_URL=http://localhost:8000
npm run dev
```

### Environment Variables

Backend (.env):

```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://localhost/flatmates_db
DB_CONN_MAX_AGE=600
DEBUG=True
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

For local development, DATABASE_URL points at a local PostgreSQL 
instance with DB_CONN_MAX_AGE=600. In production, DATABASE_URL points 
at the Supabase pooled connection string and DB_CONN_MAX_AGE=0 
(see DECISIONS.md).

Frontend (.env.development):

```env
VITE_API_URL=http://localhost:8000
```

### Demo Accounts
All flatmates pre-seeded with password: `flatmate123`
- aisha@flat.com (active)
- rohan@flat.com (active)  
- priya@flat.com (active)
- meera@flat.com (left 2026-03-28)
- sam@flat.com (joined 2026-04-08)
- dev@flat.com (guest)

### Importing the CSV
1. Login as any user
2. Go to your group → Import tab
3. Upload Expenses_Export.csv
4. Review the import report
5. Resolve flagged anomalies one by one
6. Download the final import report

## Running Tests
```bash
cd backend
python manage.py test tests/
```
