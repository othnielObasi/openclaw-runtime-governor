FROM python:3.12-slim

WORKDIR /app

# Install governor-service dependencies
COPY governor-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy governor-service application
COPY governor-service/app ./app
COPY governor-service/conftest.py ./conftest.py

# Run as non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
