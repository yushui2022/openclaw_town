FROM python:3.11-slim

WORKDIR /app

COPY opentown/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy only runtime code and required Stanford-town assets.
COPY opentown /app/opentown
COPY environment/frontend_server/static_dirs /app/environment/frontend_server/static_dirs

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "opentown.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
