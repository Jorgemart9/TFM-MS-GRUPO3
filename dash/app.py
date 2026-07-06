import os
from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("dashboard.html")


if __name__ == "__main__":
    # Cloud Run inyecta dinámicamente el puerto en la variable de entorno PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
