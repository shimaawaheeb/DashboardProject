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
