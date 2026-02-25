FROM mcr.microsoft.com/playwright/python:v1.58.0

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

COPY . .

EXPOSE 10000

CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:10000", "--workers", "2", "--threads", "4"]