FROM mcr.microsoft.com/playwright/python:chromium-v1.49.1-noble

WORKDIR /app

# System deps for the bundled Chromium are already present in the base image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the Chromium revision Playwright expects is installed.
RUN playwright install chromium

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 10000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
