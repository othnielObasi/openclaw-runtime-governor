FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy governor service
COPY . .

# External module packages are vendored into _modules/ by the deploy script.
# Add them to PYTHONPATH so the module registry can import them.
ENV PYTHONPATH="/app/_modules/compliance-modules:/app/_modules/agent-fingerprinting:/app/_modules/surge-v2:/app/_modules/impact-assessment:/app/_modules/integrations"

# Run as non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
