FROM python:3.12-slim

WORKDIR /app

# Install governor-service dependencies
COPY governor-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy governor-service application
COPY governor-service/app ./app
COPY governor-service/conftest.py ./conftest.py

# Copy sibling module directories (optional compliance modules)
COPY compliance-modules/ /modules/compliance-modules/
COPY agent-fingerprinting/ /modules/agent-fingerprinting/
COPY surge-v2/ /modules/surge-v2/
COPY integrations/ /modules/integrations/
COPY impact-assessment/ /modules/impact-assessment/

# Add modules to PYTHONPATH so the module registry can import them
ENV PYTHONPATH="/modules/compliance-modules:/modules/agent-fingerprinting:/modules/surge-v2:/modules/impact-assessment:/modules/integrations"

# Run as non-root user
RUN adduser --disabled-password --gecos '' appuser && chown -R appuser /app /modules
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
