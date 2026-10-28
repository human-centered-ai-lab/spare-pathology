import pytest

from app import create_app, db as _db
from app.config import TestConfig
from app.models import User, Study
from app.services.statistics import invalidate_stats_cache
from tests.helpers import create_study_with_images, create_study_with_schema


@pytest.fixture()
def app(tmp_path):
    """Create a Flask application configured for testing."""
    class IsolatedConfig(TestConfig):
        UPLOADS_DIR = str(tmp_path / 'uploads')
        DATASETS_DIR = str(tmp_path / 'uploads' / 'datasets')
        NOTEBOOKS_DIR = str(tmp_path / 'notebooks')

    app = create_app(IsolatedConfig)
    yield app


@pytest.fixture()
def db(app):
    """Provide a clean database for each test.

    Creates all tables before the test and drops them after.
    """
    with app.app_context():
        _db.create_all()
        invalidate_stats_cache()
        yield _db
        invalidate_stats_cache()
        _db.session.rollback()
        _db.drop_all()


@pytest.fixture()
def client(app, db):
    """Flask test client with database tables ready."""
    return app.test_client()


@pytest.fixture()
def admin_user(db):
    """Return the default admin user seeded by _init_db, updating its password for tests."""
    user = User.query.filter_by(email='admin').first()
    user.set_password('adminpassword')
    db.session.commit()
    return user


@pytest.fixture()
def test_user(db):
    """Create and return a regular participant user."""
    user = User(
        first_name='Test',
        last_name='Participant',
        email='participant@example.com',
        institution='Test Hospital',
        role='participant',
        is_test_user=False,
    )
    user.set_password('testpassword')
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture()
def sample_study(db):
    """Create and return a sample study with default settings."""
    study = Study(
        name='Test Study',
        description='A test study for evaluation',
        status='draft',
        rating_schema={'questions': []},
    )
    db.session.add(study)
    db.session.commit()
    return study


@pytest.fixture()
def study_with_schema(db):
    """Create and return a study with the default 6-question rating schema."""
    return create_study_with_schema(db)


@pytest.fixture()
def study_with_images(db):
    """Create and return a study with schema + 10 dataset images (5 real, 5 synthetic)."""
    return create_study_with_images(db, n=10)
