FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY mock_vietful ./mock_vietful

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "mock_vietful.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
