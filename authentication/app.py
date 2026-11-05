import os
import re
import time
from datetime import timedelta

from flask import Flask, jsonify, request
from flask_jwt_extended import JWTManager, create_access_token, get_jwt_identity, jwt_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "mysql+pymysql://user:password@mysql:3306/authentication"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "change-this-secret")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)

db = SQLAlchemy(app)
jwt = JWTManager(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    forename = db.Column(db.String(100), nullable=False)
    surname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="employee")


def valid_email(email):
    return isinstance(email, str) and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None


with app.app_context():
    for attempt in range(10):
        try:
            db.create_all()
            break
        except SQLAlchemyError:
            if attempt == 9:
                raise
            time.sleep(3)

    director = User.query.filter(User.email == "onlymoney@gmail.com").first()
    if director is None:
        director = User(
            forename="Scrooge",
            surname="McDuck",
            email="onlymoney@gmail.com",
            password=generate_password_hash("evenmoremoney"),
            role="director",
        )
        db.session.add(director)
        db.session.commit()


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}

    required_fields = ["forename", "surname", "email", "password"]
    for field in required_fields:
        if field not in data or data[field] == "":
            return jsonify(message=f"Field {field} is missing."), 400

    if not valid_email(data["email"]):
        return jsonify(message="Invalid email."), 400

    if not isinstance(data["password"], str) or len(data["password"]) < 8:
        return jsonify(message="Invalid password."), 400

    if User.query.filter(User.email == data["email"]).first() is not None:
        return jsonify(message="Email already exists."), 400

    user = User(
        forename=data["forename"],
        surname=data["surname"],
        email=data["email"],
        password=generate_password_hash(data["password"]),
        role="employee",
    )
    db.session.add(user)
    db.session.commit()
    return "", 200


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}

    if "email" not in data or data["email"] == "":
        return jsonify(message="Field email is missing."), 400

    if "password" not in data or data["password"] == "":
        return jsonify(message="Field password is missing."), 400

    if not valid_email(data["email"]):
        return jsonify(message="Invalid email."), 400

    user = User.query.filter(User.email == data["email"]).first()
    if user is None or not check_password_hash(user.password, data["password"]):
        return jsonify(message="Invalid credentials."), 400

    claims = {
        "forename": user.forename,
        "surname": user.surname,
        "email": user.email,
        "role": user.role,
    }
    token = create_access_token(
        identity=user.email, additional_claims=claims, expires_delta=timedelta(hours=1)
    )
    return jsonify(accessToken=token), 200


@app.route("/delete", methods=["POST"])
@jwt_required()
def delete():
    email = get_jwt_identity()
    user = User.query.filter(User.email == email).first()

    if user is None:
        return jsonify(message="Unknown user."), 400

    db.session.delete(user)
    db.session.commit()
    return "", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
