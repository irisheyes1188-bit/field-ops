"""
server.py - FieldOps API Server
Serves the FieldOps frontend and exposes API endpoints.
Deployed on Render via render.yaml Blueprint.
"""

import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "fieldops-api"}), 200


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    # Placeholder - extend with real data source
    return jsonify({"tasks": []}), 200


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json()
    return jsonify({"created": True, "task": data}), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
