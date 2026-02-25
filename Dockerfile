FROM mcr.microsoft.com/playwright/python:v1.58.0

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

COPY . .

EXPOSE 10000

CMD bash -c "python worker.py & gunicorn main:app --bind 0.0.0.0:10000 --workers 1 --threads 4"