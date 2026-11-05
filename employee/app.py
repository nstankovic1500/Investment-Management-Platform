import json
import os
import re
import uuid
from datetime import datetime
from functools import wraps

import redis
from bson import ObjectId
from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, get_jwt, get_jwt_identity, jwt_required
from pymongo import MongoClient


app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "change-this-secret")
jwt = JWTManager(app)

mongo_client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
mongo_database = mongo_client[os.environ.get("MONGO_DB", "investment_management")]
assets = mongo_database["assets"]

redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=True,
)


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


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def date_as_string(value):
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return value


def asset_response(asset):
    result = {
        "id": str(asset["_id"]),
        "name": asset.get("name"),
        "categories": asset.get("categories", []),
        "buying_date": date_as_string(asset.get("buying_date")),
        "buying_price": asset.get("buying_price"),
        "info": asset.get("info", {}),
    }
    if asset.get("selling_date") is not None:
        result["selling_date"] = date_as_string(asset["selling_date"])
        result["selling_price"] = asset.get("selling_price")
    return result


@app.route("/search", methods=["POST"])
@role_check("employee")
def search():
    data = request.get_json() or {}
    query = {}

    if data.get("name") is not None:
        query["name"] = {"$regex": re.escape(str(data["name"]))}
    if data.get("category") is not None:
        query["categories"] = data["category"]
    if data.get("buying_date") is not None:
        buying_date = parse_date(data["buying_date"])
        if buying_date is not None:
            query["buying_date"] = {"$gt": buying_date}
    if data.get("selling_date") is not None:
        selling_date = parse_date(data["selling_date"])
        if selling_date is not None:
            query["selling_date"] = {"$lt": selling_date}

    operator_map = {
        "eq": "$eq",
        "ne": "$ne",
        "gt": "$gt",
        "gte": "$gte",
        "lt": "$lt",
        "lte": "$lte",
    }
    for item in data.get("info_filters", []):
        field = item.get("field")
        operator = item.get("operator")
        if field and operator in operator_map:
            query["info." + field] = {operator_map[operator]: item.get("value")}

    found_assets = assets.find(query)
    return jsonify(assets=[asset_response(asset) for asset in found_assets]), 200


@app.route("/create_buy_order", methods=["POST"])
@role_check("employee")
def create_buy_order():
    data = request.get_json() or {}
    for field in ["name", "categories", "buying_price", "info"]:
        if field not in data or (isinstance(data[field], str) and data[field] == ""):
            return jsonify(message=f"Field {field} is missing."), 400

    if isinstance(data["categories"], list) and len(data["categories"]) == 0:
        return jsonify(message="Categories list is empty."), 400

    if not isinstance(data["buying_price"], (int, float)) or isinstance(data["buying_price"], bool) or data["buying_price"] <= 0:
        return jsonify(message="Invalid buying price."), 400

    order_id = str(uuid.uuid4())
    order = {
        "uuid": order_id,
        "order_type": "BUY",
        "name": data["name"],
        "categories": data["categories"],
        "buying_price": data["buying_price"],
        "info": data["info"],
    }
    redis_client.set("order:" + order_id, json.dumps(order))
    return "", 200


@app.route("/create_sell_order", methods=["POST"])
@role_check("employee")
def create_sell_order():
    data = request.get_json() or {}
    for field in ["id", "selling_price"]:
        if field not in data:
            return jsonify(message=f"Field {field} is missing."), 400

    try:
        asset_id = ObjectId(data["id"])
    except Exception:
        asset_id = None
    if asset_id is None or assets.find_one({"_id": asset_id}) is None:
        return jsonify(message="Invalid id."), 400

    if not isinstance(data["selling_price"], (int, float)) or isinstance(data["selling_price"], bool) or data["selling_price"] <= 0:
        return jsonify(message="Invalid selling price."), 400

    order_id = str(uuid.uuid4())
    order = {
        "uuid": order_id,
        "order_type": "SELL",
        "id": data["id"],
        "selling_price": data["selling_price"],
    }
    redis_client.set("order:" + order_id, json.dumps(order))
    return "", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port)
