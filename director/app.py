import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

import redis
from bson import ObjectId
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, get_jwt, jwt_required
from pymongo import MongoClient
from solcx import compile_source
from web3 import Web3

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "change-this-secret")
jwt = JWTManager(app)
mongo_client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
mongo_database = mongo_client[os.environ.get("MONGO_DB", "investment_management")]
assets = mongo_database["assets"]
redis_client = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=int(os.environ.get("REDIS_PORT", "6379")), decode_responses=True)
web3 = Web3(Web3.HTTPProvider(os.environ.get("WEB3_PROVIDER_URL", "http://ganache:8545")))
voting_contracts = {}

def role_check(required_role):
    def decorator(function):
        @wraps(function)
        @jwt_required()
        def wrapped(*args, **kwargs):
            if get_jwt().get("role") != required_role:
                return jsonify(message="Unauthorized."), 401
            return function(*args, **kwargs)
        return wrapped
    return decorator

def voting_contract():
    path = os.environ.get("VOTING_CONTRACT_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "blockchain", "Voting.sol"))
    with open(path) as source_file:
        compiled = compile_source(source_file.read(), output_values=["abi", "bin"])
    data = next(iter(compiled.values()))
    return web3.eth.contract(abi=data["abi"], bytecode=data["bin"])

@app.route("/pending_orders", methods=["GET"])
@role_check("director")
def pending_orders():
    orders = []
    for key in redis_client.scan_iter(match="order:*"):
        value = redis_client.get(key)
        if value is not None:
            orders.append(json.loads(value))
    return jsonify(orders=orders), 200

@app.route("/decision", methods=["POST"])
@role_check("director")
def decision():
    data = request.get_json() or {}
    if "uuid" not in data or data["uuid"] == "":
        return jsonify(message="Field uuid is missing."), 400
    try:
        uuid.UUID(data["uuid"])
    except (ValueError, AttributeError, TypeError):
        return jsonify(message="Invalid uuid."), 400
    order_key = "order:" + data["uuid"]
    order_value = redis_client.get(order_key)
    if order_value is None:
        return jsonify(message="Invalid uuid."), 400
    if "voters" not in data or not isinstance(data["voters"], list) or len(data["voters"]) == 0:
        return jsonify(message="Field voters is missing."), 400
    if any(not Web3.is_address(voter) for voter in data["voters"]):
        return jsonify(message="Invalid voter address."), 400
    if len(data["voters"]) % 2 == 0:
        return jsonify(message="Even number of voters."), 400
    owner = os.environ.get("CONTRACT_OWNER_ACCOUNT")
    private_key = os.environ.get("CONTRACT_OWNER_PRIVATE_KEY")
    if not owner or not private_key:
        return jsonify(message="Blockchain configuration is missing."), 500
    order = json.loads(order_value)
    contract = voting_contract()
    nonce = web3.eth.get_transaction_count(owner)
    transaction = contract.constructor(data["voters"]).build_transaction({"from": owner, "nonce": nonce, "gas": 2000000, "gasPrice": web3.eth.gas_price})
    signed = web3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    deployed = web3.eth.contract(address=receipt.contractAddress, abi=contract.abi)
    voting_contracts[receipt.contractAddress] = {"contract": deployed, "order_key": order_key, "order": order}
    return jsonify(approve_transaction={"to": receipt.contractAddress, "data": deployed.functions.vote(True)._encode_transaction_data(), "value": 0}, reject_transaction={"to": receipt.contractAddress, "data": deployed.functions.vote(False)._encode_transaction_data(), "value": 0}), 200

def process_finished_votes():
    while True:
        for address, item in list(voting_contracts.items()):
            try:
                contract = item["contract"]
                if contract.functions.ended().call():
                    if contract.functions.approved().call():
                        order = item["order"]
                        now = datetime.now(timezone.utc)
                        if order.get("order_type") == "BUY":
                            assets.insert_one({"name": order["name"], "categories": order["categories"], "buying_price": order["buying_price"], "info": order["info"], "buying_date": now})
                        elif order.get("order_type") == "SELL":
                            assets.update_one({"_id": ObjectId(order["id"])}, {"$set": {"selling_price": order["selling_price"], "selling_date": now}})
                    redis_client.delete(item["order_key"])
                    del voting_contracts[address]
            except Exception:
                pass
        time.sleep(2)

threading.Thread(target=process_finished_votes, daemon=True).start()

@app.route("/report", methods=["GET"])
@role_check("director")
def report():
    pipeline = [{"$unwind": "$categories"}, {"$group": {"_id": "$categories", "spent": {"$sum": "$buying_price"}, "earned": {"$sum": {"$cond": [{"$ifNull": ["$selling_price", False]}, "$selling_price", 0]}}}}, {"$sort": {"earned": -1, "spent": 1, "_id": 1}}]
    statistics = []
    for item in assets.aggregate(pipeline):
        statistics.append({"category": item["_id"], "spent": item["spent"], "earned": item["earned"]})
    return jsonify(statistics=statistics), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5002"))
    app.run(host="0.0.0.0", port=port)
