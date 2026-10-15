FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN pip install --no-deps . && useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "northstar.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
