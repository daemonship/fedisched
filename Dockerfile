# Build frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend .
RUN npm run build

# Build backend
FROM python:3.11-slim AS backend-builder
WORKDIR /app
COPY pyproject.toml ./
# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .
# Copy application code
COPY app ./app

# Runtime stage
FROM python:3.11-slim
WORKDIR /app

# Install runtime dependencies
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /app/app ./app
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist
COPY pyproject.toml .env.example ./

# Create non-root user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser && \
    chown -R appuser:appgroup /app
USER appuser

# Volume for SQLite database (mount at /app/data)
ENV DATABASE_URL=sqlite:///./data/fedisched.db
VOLUME /app/data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
