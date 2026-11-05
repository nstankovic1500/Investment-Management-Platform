FROM python:3.8-slim

WORKDIR /app
COPY authentication/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY authentication/app.py .

CMD ["python", "app.py"]
