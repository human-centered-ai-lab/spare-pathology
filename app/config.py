import os
import secrets
import fcntl
from pathlib import Path

basedir = Path(__file__).resolve().parent.parent


def _database_url(
    base_dir: str | Path | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    if env.get('DATABASE_URL'):
        return env['DATABASE_URL']
    root = Path(base_dir) if base_dir is not None else basedir
    # Reuse existing installations without moving a live SQLite database.
    legacy_path = root / 'instance' / 'syneval.db'
    path = legacy_path if legacy_path.exists() else root / 'instance' / 'spare.db'
    return f'sqlite:///{path}'


def _secret_key_path(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir) if base_dir is not None else basedir
    return root / 'instance' / 'secret_key'


def _load_secret_key(
    base_dir: str | Path | None = None,
    environ: dict[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    env_secret = env.get('SECRET_KEY')
    if env_secret:
        return env_secret

    secret_path = _secret_key_path(base_dir)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    # Multiple workers must agree on the key during the first startup.
    fd = os.open(secret_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+', encoding='utf-8') as key_file:
        fcntl.flock(key_file, fcntl.LOCK_EX)
        secret = key_file.read().strip()
        if not secret:
            secret = secrets.token_hex(32)
            key_file.seek(0)
            key_file.truncate()
            key_file.write(secret)
            key_file.flush()
        return secret


class Config:
    SECRET_KEY = _load_secret_key()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024
    INIT_DATABASE = os.environ.get('INIT_DATABASE', '1') == '1'
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
    SEED_DEMO_DATA = os.environ.get('SEED_DEMO_DATA', '0') == '1'
    CREATE_TEST_USER = False
    DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD', '')
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOADS_DIR = os.environ.get('UPLOADS_DIR', str(basedir / 'uploads'))
    DATASETS_DIR = os.environ.get('DATASETS_DIR', str(Path(UPLOADS_DIR) / 'datasets'))
    JUPYTER_PORT = int(os.environ.get('JUPYTER_PORT', 8888))
    ENABLE_JUPYTER = os.environ.get('ENABLE_JUPYTER', '0') == '1'
    JUPYTER_TOKEN = os.environ.get('JUPYTER_TOKEN', '')
    NOTEBOOKS_DIR = os.environ.get('NOTEBOOKS_DIR', str(basedir / 'notebooks'))
    XOPAT_NODE_PORT = int(os.environ.get('XOPAT_NODE_PORT', 9010))
    XOPAT_SERVER_URL = os.environ.get(
        'XOPAT_SERVER_URL',
        f'http://127.0.0.1:{XOPAT_NODE_PORT}',
    )
    XOPAT_DIR = os.environ.get('XOPAT_DIR', str(basedir / 'vendor' / 'xopat'))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'  # In-memory SQLite
    SECRET_KEY = 'test-secret-key'
    ADMIN_PASSWORD = '1a2s3d4f5g6h'
    BCRYPT_LOG_ROUNDS = 4
    DEMO_PASSWORD = 'password123'
    CREATE_TEST_USER = True
    SEED_DEMO_DATA = False
    INIT_DATABASE = True


class E2ETestConfig(Config):
    E2E_BASE_DIR = str(basedir / 'instance' / 'e2e')
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{Path(E2E_BASE_DIR) / 'e2e_test.db'}"
    UPLOADS_DIR = str(Path(E2E_BASE_DIR) / 'uploads')
    DATASETS_DIR = str(Path(UPLOADS_DIR) / 'datasets')
    SECRET_KEY = 'e2e-test-key'
    ADMIN_PASSWORD = '1a2s3d4f5g6h'
    BCRYPT_LOG_ROUNDS = 4
    DEMO_PASSWORD = 'password123'
    CREATE_TEST_USER = True
    SEED_DEMO_DATA = True
    INIT_DATABASE = True
    NOTEBOOKS_DIR = str(Path(E2E_BASE_DIR) / 'notebooks')
