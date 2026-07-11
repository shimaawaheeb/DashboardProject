# Enterprise Projects & Workforce Dashboard

An internship project that demonstrates a data-driven enterprise dashboard for
project portfolio tracking, workforce visibility, governance monitoring, and
dashboard-assisted analysis.

The application reads its business data from Excel workbooks instead of
hard-coded KPI values. `sample_data.xlsx` is the editable source workbook, and
`cleaned_data.xlsx` is the cleaned workbook used by the dashboard at runtime.

## Project Overview

This project was built to simulate an internal enterprise reporting tool. It
combines a browser-based dashboard, a lightweight Python HTTP server, local
authentication, admin workbook management, and an optional AI assistant that can
answer questions using dashboard context.

Core capabilities include:

- Portfolio overview for project status, investment, delivery health, and risks.
- Project delivery tracking for tasks, deadlines, blockers, effort, and workload.
- Workforce insights for employees, departments, assignments, and capacity.
- Governance reporting for weekly updates, meetings, outcomes, and activity.
- Employee-specific "My dashboard" views based on the signed-in account email.
- Admin tools for adding, editing, deleting, undoing, and redoing workbook data.
- Google and local authentication with employee email validation.
- Optional Gemini-powered dashboard assistant.

## Technology Stack

- Frontend: HTML, CSS, and JavaScript.
- Backend: Python standard library HTTP server.
- Data source: Excel workbooks.
- Authentication: Local SQLite database with bcrypt password hashing.
- Development reload: `watchfiles`.
- Optional assistant: Gemini API.

## Run Locally

From the `DashboardProject` folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
./start_dev.sh
```

Open:

```text
http://127.0.0.1:8000
```

The development server binds to port `8000`. If that port is already in use,
the server exits with an error so the issue is visible.

The development command uses `watchfiles`; changes to `.py`, `.html`, `.css`,
or `.js` files automatically restart `server.py`.

For a non-reloading run:

```bash
./start_dashboard.sh
```

Do not open `index.html` directly. Browsers block local HTML files from reading
local workbook files, so the dashboard must be served by `server.py`.

## Run With Docker

The published Docker image includes the application code and anonymized demo
workbooks. Runtime data is stored outside the image in `/data` so accounts and
admin workbook changes can persist across container restarts.

Create a named Docker volume:

```bash
docker volume create dashboard-data
```

Run the image:

```bash
docker run -p 8000:8000 \
  --env-file .env \
  -v dashboard-data:/data \
  shimaawaheeb/dashboard-project:latest
```

Open:

```text
http://127.0.0.1:8000
```

On first run, the container copies the bundled demo workbooks into `/data` if
they are missing. After that, `/data` holds:

```text
/data/dashboard_auth.sqlite3
/data/sample_data.xlsx
/data/cleaned_data.xlsx
```

Useful Docker environment variables:

```dotenv
DASHBOARD_DATA_DIR=/data
AUTH_DB_PATH=/data/dashboard_auth.sqlite3
SAMPLE_WORKBOOK_PATH=/data/sample_data.xlsx
CLEANED_WORKBOOK_PATH=/data/cleaned_data.xlsx
DEFAULT_ADMIN_EMAIL=employee1001@example.com
```

`DEFAULT_ADMIN_EMAIL` may contain one email or a comma-separated list. When a
user with one of those emails signs up, the account is granted admin access.

### Demo Signup

The public Docker image uses anonymized employee data. It does not include any
pre-created user accounts or passwords.

To try the demo:

1. Open `http://127.0.0.1:8000`.
2. Select **Sign up**.
3. Use this demo employee email:

   ```text
   employee1001@example.com
   ```

4. Choose any valid username and password.

`employee1001@example.com` is the default admin email for the demo image. After
the account is created, it receives admin access.

If Gmail settings are not configured in `.env`, the signup OTP is printed in the
container logs instead of being sent by email:

```bash
docker logs <container-name>
```

The log line looks like:

```text
Signup OTP for demo.admin: 123456
```

## Deploy To Vercel

The project is Vercel-compatible through `api/index.py`, which exports a
`BaseHTTPRequestHandler`-compatible `handler`. Vercel serves the static frontend
files normally and routes `/api/*` requests to that Python function.

Local development still uses `server.py` and `ThreadingHTTPServer`. Vercel does
not call `server.py` or `serve_forever()`.

To deploy:

1. Open Vercel and select **Add New Project**.
2. Import `shimaawaheeb/DashboardProject`.
3. Use the default static deployment settings.
4. Deploy.

Vercel uses:

```text
index.html, app.js, styles.css, avatars/  -> static frontend
api/index.py                              -> Python API function
vercel.json                               -> routes /api/* to api/index.py
```

The bundled `cleaned_data.xlsx` is included in the function bundle and is read
by the API at runtime.

### Vercel Storage Limits

Vercel serverless functions do not provide durable local file storage. In Vercel,
runtime files are placed under:

```text
/tmp/dashboard-data
```

This means local SQLite auth data, sessions, admin edits, and workbook changes
are temporary and may reset after redeploys or function instance changes. This
Vercel deployment is suitable for a public demo. For production persistence,
replace local SQLite and Excel writes with managed storage such as PostgreSQL
and object storage.

### Vercel Environment Variables

Keep secrets in Vercel project environment variables, not in GitHub:

```dotenv
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=https://your-vercel-domain.vercel.app/api/auth/google/callback
GMAIL_USER=your-email@gmail.com
GMAIL_APP_PASSWORD=your-gmail-app-password
PASSWORD_RESET_BASE_URL=https://your-vercel-domain.vercel.app
DEFAULT_ADMIN_EMAIL=employee1001@example.com
```

If Gmail settings are not configured, signup OTP and password reset links are
printed in the Vercel function logs.

## Optional Docker Backend Deployment

The Docker image remains useful for local demos or container platforms. Docker
supports persistent volumes, so it is a better fit than Vercel if you need local
SQLite and Excel edits to persist without refactoring storage.

## Test

Run the test suite with the project-local Python environment:

```bash
.venv/bin/python -m unittest discover -v
```

## Data Workflow

The dashboard uses `cleaned_data.xlsx` for reporting. To refresh the data:

1. Update the structured tables in `sample_data.xlsx`.
2. Save the workbook in this project folder with the same filename.
3. Run:

   ```bash
   .venv/bin/python clean_workbook.py
   ```

4. Select **Refresh data** in the dashboard.

The server reloads workbook data on each refresh request. A server restart is
not required after workbook changes.

For Docker runs, update the workbook files in the mounted `/data` volume or
mount your own files to the configured workbook paths.

## Admin Page

The admin page allows authorized users to manage workbook data from the browser.
It supports:

- Adding new records.
- Editing existing records.
- Deleting records.
- Calendar selectors for date fields.
- Undo and redo for admin data changes made during the current browser session.
- Admin access management for existing dashboard users.

Admin changes are written back to the Excel source workbook and then cleaned so
the dashboard can immediately use the updated data.

## Authentication

The dashboard supports local account signup/login and Google sign-in. Signup is
restricted to emails that exist in the Employees sheet of the cleaned workbook.

For a fresh Docker volume, no users exist yet. Sign up with an email in the
Employees sheet. By default, `employee1001@example.com` is the initial admin
email for the public demo workbook.

Google sign-in requires these values in the git-ignored `.env` file:

```dotenv
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
```

Restart the server after changing `.env`.

## Dashboard Assistant

The assistant is integrated into the dashboard and uses the same
`cleaned_data.xlsx` source. It receives only:

- calculated dashboard KPIs;
- records from the cleaned workbook relevant to the question;
- the active dashboard page and department filter.

It does not rely on unrelated general knowledge or an old chatbot mock
database. If the available dashboard context cannot support an answer, it is
instructed to say so.

To enable the assistant, add a Gemini API key to `.env`:

```dotenv
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.5-flash
```

The key is read only by the Python server and is never sent to the browser.

## Dashboard Pages

- **Portfolio overview:** portfolio status, investment, health, and exceptions.
- **Project delivery:** task pipeline, deadlines, blockers, effort, and workload.
- **Workforce:** employee status, capacity, locations, and assignments.
- **Governance:** weekly health, meetings, outcomes, and activity.
- **My dashboard:** employee-specific projects, tasks, meetings, and profile data.
- **Admin:** workbook data management and admin access control.

The department filter uses owning department for portfolio, delivery, and
governance views. On the workforce page, it uses the employee or assignee
department.
