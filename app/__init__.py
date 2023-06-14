import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_htmx import HTMX
from datetime import datetime
from distutils.version import LooseVersion
from . import config
from .utils import basedir
db = SQLAlchemy()
htmx = HTMX()

def sort_versions(versions):
    return sorted(versions, key=lambda x: LooseVersion(x.version_code), reverse=True)


def create_app():
    app = Flask(__name__)
    app.config.from_object(config.Config)
    db.init_app(app)
    htmx.init_app(app)

    from app.ui_routes import ui
    from app.api_routes import api
    app.register_blueprint(ui)
    app.register_blueprint(api)
    
    

    app.jinja_env.filters['sort_versions'] = sort_versions

    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    with app.app_context():
        db.create_all()
    return app