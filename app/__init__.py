import os
import click

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from sqlalchemy import event, inspect, text
from werkzeug.exceptions import HTTPException

from app.version import __version__

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()


def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key enforcement for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class is None:
        from app.config import Config
        config_class = Config

    app.config.from_object(config_class)

    @app.cli.command('init-db')
    def init_db_command():
        """Initialize storage and create the first administrator."""
        _init_db(app)
        click.echo('Database initialized.')

    # Ensure instance, uploads, and images directories exist
    os.makedirs(os.path.join(app.instance_path), exist_ok=True)
    os.makedirs(app.config.get('UPLOADS_DIR', 'uploads'), exist_ok=True)
    os.makedirs(app.config.get('DATASETS_DIR', os.path.join('uploads', 'datasets')), exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # Enable SQLite foreign key support
    with app.app_context():
        if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
            event.listen(db.engine, 'connect', _set_sqlite_pragma)

    # Register API blueprint
    from app.api import bp as api_bp
    app.register_blueprint(api_bp)

    @app.get('/healthz')
    def health():
        db.session.execute(text('SELECT 1'))
        return jsonify(status='ok', version=__version__)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    # Serve React SPA (when frontend/dist exists)
    frontend_dist = os.path.join(os.path.dirname(app.root_path), 'frontend', 'dist')
    if os.path.isdir(frontend_dist):
        @app.route('/', defaults={'path': ''})
        @app.route('/<path:path>')
        def serve_react(path):
            from flask import abort, send_from_directory

            if path == 'api' or path.startswith('api/'):
                abort(404)
            # Serve static assets if they exist
            if path and os.path.exists(os.path.join(frontend_dist, path)):
                return send_from_directory(frontend_dist, path)
            # Otherwise serve index.html for client-side routing
            return send_from_directory(frontend_dist, 'index.html')

    if app.config.get('INIT_DATABASE', True):
        with app.app_context():
            _init_db(app)

    return app



def _init_db(app):
    """Create all tables and seed default users if they don't exist."""
    db.create_all()
    _apply_additive_migrations()

    from app.models import User

    if not User.query.filter_by(role='admin').first():
        password = app.config.get('ADMIN_PASSWORD', '')
        if len(password) < 12 or len(password.encode('utf-8')) > 72:
            raise RuntimeError('Set ADMIN_PASSWORD to 12–72 bytes before the first startup.')
        admin = User(
            first_name='Admin',
            last_name='User',
            email=app.config.get('ADMIN_EMAIL', 'admin'),
            role='admin',
            is_test_user=False,
        )
        admin.set_password(password)
        db.session.add(admin)

    # Create default test user if not present
    if app.config.get('CREATE_TEST_USER') and not User.query.filter_by(email='test').first():
        test_user = User(
            first_name='Test',
            last_name='User',
            email='test',
            role='participant',
            is_test_user=True,
        )
        test_user.set_password('1a2s3d4f5g6h')
        db.session.add(test_user)

    db.session.commit()

    if app.config.get('SEED_DEMO_DATA', False):
        from app.services.seed import seed_database
        seed_database()


def _apply_additive_migrations():
    """Apply simple additive schema changes for existing deployments.

    The app does not use Alembic yet, so additive migrations are handled here
    to keep existing SQLite databases usable after upgrades.
    """
    inspector = inspect(db.engine)
    if 'studies' not in inspector.get_table_names():
        return

    study_columns = {column['name'] for column in inspector.get_columns('studies')}
    if 'default_image_viewer' not in study_columns:
        with db.engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE studies "
                "ADD COLUMN default_image_viewer VARCHAR(20) NOT NULL DEFAULT 'native'"
            )
