FROM python:3.13-slim

# Set working directory inside the container
WORKDIR /app

# Copy whole project (assuming you're in the root of your project)
COPY ./app /app/app

# Set PYTHONPATH so FastAPI knows where to find the 'app' module
ENV PYTHONPATH=/app

# Install dependencies
RUN pip install --no-cache-dir -r /app/app/requirements.txt

# Run the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]