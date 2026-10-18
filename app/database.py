
import os
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_database(app):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
