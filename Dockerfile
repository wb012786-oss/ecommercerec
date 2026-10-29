FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY samples/ ./samples/
RUN mkdir -p /tmp/ecom_reconcile_uploads && chmod 777 /tmp/ecom_reconcile_uploads
ENV PYTHONUNBUFFERED=1
ENV UPLOAD_DIR=/tmp/ecom_reconcile_uploads
EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "-w", "2", "--timeout", "120"]