FROM python:3.11-slim

WORKDIR /app

# Install deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY edf_lib/ ./edf_lib/
COPY app/ ./app/
COPY load_data.py .

# Create data dirs
RUN mkdir -p /data/uploads

ENV DATABASE_URL=sqlite:////data/cpap.db
ENV UPLOAD_DIR=/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
