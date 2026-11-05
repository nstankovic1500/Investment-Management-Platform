# Investment Management Platform

The first implemented component is the Authentication service.

The Employee service searches assets in MongoDB and stores pending buy and sell orders in Redis.

## Install

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r authentication/requirements.txt
```

Set the configuration variables from `authentication/.env.example` in the shell (or in a local `.env` file loaded by your environment):

```bash
export DATABASE_URL=mysql+pymysql://user:password@mysql:3306/authentication
export JWT_SECRET_KEY=replace-with-a-long-random-secret
```

`DATABASE_URL` should point to the MySQL database used by Authentication.

## Run

```bash
python authentication/app.py
```

The service listens on `http://127.0.0.1:5000`. The MySQL tables are created automatically on startup.

## Test with curl

Register a user:

```bash
curl -X POST http://127.0.0.1:5000/register \
  -H "Content-Type: application/json" \
  -d '{"forename":"Ana","surname":"Anic","email":"ana@example.com","password":"password123"}'
```

Log in and copy the `accessToken` from the response:

```bash
curl -X POST http://127.0.0.1:5000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ana@example.com","password":"password123"}'
```

Delete the logged-in user:

```bash
curl -X POST http://127.0.0.1:5000/delete \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

## Employee service

Install its dependencies with:

```bash
pip install -r employee/requirements.txt
```

Set the variables shown in `employee/.env.example`. Start MongoDB locally on port 27017 and Redis locally on port 6379, then run:

```bash
python employee/app.py
```

Use an employee JWT from the Authentication service:

```bash
curl -X POST http://127.0.0.1:5000/search -H "Authorization: Bearer ACCESS_TOKEN" -H "Content-Type: application/json" -d '{"name":"Bond","category":"fixed-income","info_filters":[{"field":"rating","operator":"eq","value":"AAA"}]}'
curl -X POST http://127.0.0.1:5000/create_buy_order -H "Authorization: Bearer ACCESS_TOKEN" -H "Content-Type: application/json" -d '{"name":"Example asset","categories":["category0","category1"],"buying_price":10000,"info":{}}'
curl -X POST http://127.0.0.1:5000/create_sell_order -H "Authorization: Bearer ACCESS_TOKEN" -H "Content-Type: application/json" -d '{"id":"MONGODB_OBJECT_ID","selling_price":20000}'

## Director service

Install dependencies with `pip install -r director/requirements.txt`. Set the variables in `director/.env.example`, using the same JWT secret as Authentication. With MongoDB on port 27017 and Redis on port 6379, run `python director/app.py`.

```bash
curl http://127.0.0.1:5000/pending_orders -H "Authorization: Bearer DIRECTOR_TOKEN"
curl -X POST http://127.0.0.1:5000/decision -H "Authorization: Bearer DIRECTOR_TOKEN" -H "Content-Type: application/json" -d '{"uuid":"ORDER_UUID","voters":["0x1111111111111111111111111111111111111111","0x2222222222222222222222222222222222222222","0x3333333333333333333333333333333333333333"]}'
curl http://127.0.0.1:5000/report -H "Authorization: Bearer DIRECTOR_TOKEN"
```

## Kubernetes

Build the three local images:

```bash
docker build -t investment-authentication:latest -f authentication/Dockerfile .
docker build -t investment-employee:latest -f employee/Dockerfile .
docker build -t investment-director:latest -f director/Dockerfile .
```

Apply the Kubernetes resources:

```bash
kubectl apply -f kubernetes/
kubectl get pods
kubectl get services
kubectl logs deployment/authentication
kubectl delete -f kubernetes/
```

The manifests use `mysql`, `mongodb`, and `redis` as internal hostnames. MySQL and MongoDB data are stored in persistent volume claims. Employee is configured with exactly three replicas. Authentication creates the initial director (`onlymoney@gmail.com`) once, after the database tables are available.

## Blockchain voting

Install the Director blockchain dependencies with `pip install -r director/requirements.txt`. Compile support uses Solidity 0.8.20; install it locally once with `python -c "from solcx import install_solc; install_solc('0.8.20')"` when running Director outside Docker. Set `WEB3_PROVIDER_URL`, `CONTRACT_OWNER_ACCOUNT`, and `CONTRACT_OWNER_PRIVATE_KEY` in the Director environment.

Ganache is included in Docker Compose at `http://ganache:8545`. Director's `/decision` endpoint accepts a UUID and an odd list of Ethereum voter addresses, deploys `Voting.sol`, and returns `approve_transaction` and `reject_transaction` objects. Voters submit one of those transactions from their own allowed account. A small background polling loop observes the contract's `ended` and `approved` values, then updates Redis and MongoDB.
