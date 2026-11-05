FROM python:3.8-slim

WORKDIR /app
COPY director/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY director/app.py .
COPY blockchain/Voting.sol /blockchain/Voting.sol
RUN python -c "from solcx import install_solc; install_solc('0.8.20')"

CMD ["python", "app.py"]
