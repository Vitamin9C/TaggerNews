FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir . 2>/dev/null || true   # install deps only
COPY src/ src/
RUN pip install --no-cache-dir .                        # now install the actual package

# Copy application code
COPY src/ src/
COPY templates/ templates/
COPY static/ static/
COPY migrations/ migrations/
COPY alembic.ini .

# Create non-root user
RUN adduser --disabled-password --no-create-home appuser
USER appuser

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "taggernews.main:app", "--host", "0.0.0.0", "--port", "8000"]
