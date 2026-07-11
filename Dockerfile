FROM python:3.12-slim

WORKDIR /app

COPY requirements-dev.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HOST=0.0.0.0
ENV PORT=8000
ENV DASHBOARD_DATA_DIR=/data
ENV AUTH_DB_PATH=/data/dashboard_auth.sqlite3
ENV SAMPLE_WORKBOOK_PATH=/data/sample_data.xlsx
ENV CLEANED_WORKBOOK_PATH=/data/cleaned_data.xlsx
ENV DEFAULT_ADMIN_EMAIL=employee1001@example.com

EXPOSE 8000
VOLUME ["/data"]

CMD ["sh", "-c", "python3 server.py --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]
