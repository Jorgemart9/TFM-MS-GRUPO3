import os
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/")
def health_check():
    return jsonify({"status": "healthy", "service": "gemma-monitoring"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
