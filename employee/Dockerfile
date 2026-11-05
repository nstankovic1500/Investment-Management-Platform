FROM python:3.8-slim

WORKDIR /app
COPY employee/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY employee/app.py .

CMD ["python", "app.py"]
