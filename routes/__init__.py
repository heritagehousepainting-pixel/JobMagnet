"""Route blueprint registration for JobMagnet."""

from routes.public import bp as public_bp
from routes.settings import bp as settings_bp


def register_blueprints(app):
    """Attach feature route groups to the Flask app."""
    app.register_blueprint(public_bp)
    app.register_blueprint(settings_bp)
