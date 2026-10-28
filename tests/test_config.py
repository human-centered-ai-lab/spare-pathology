
import sqlite3

from app.config import _database_url, _load_secret_key, _secret_key_path


def test_load_secret_key_prefers_environment(tmp_path):
    secret = _load_secret_key(
        base_dir=tmp_path,
        environ={'SECRET_KEY': 'env-secret'},
    )
    assert secret == 'env-secret'
    assert not _secret_key_path(tmp_path).exists()


def test_load_secret_key_persists_generated_value(tmp_path):
    secret1 = _load_secret_key(base_dir=tmp_path, environ={})
    secret2 = _load_secret_key(base_dir=tmp_path, environ={})

    secret_path = _secret_key_path(tmp_path)
    assert secret_path.exists()
    assert secret1 == secret2
    assert secret_path.read_text(encoding='utf-8') == secret1
    assert len(secret1) == 64


def test_fresh_database_uses_spare_name(tmp_path):
    assert _database_url(tmp_path, {}) == f"sqlite:///{tmp_path / 'instance' / 'spare.db'}"


def test_rename_reuses_existing_database_even_if_new_name_exists(tmp_path):
    instance = tmp_path / 'instance'
    instance.mkdir()
    legacy = instance / 'syneval.db'
    with sqlite3.connect(legacy) as connection:
        connection.execute('CREATE TABLE saved_ratings (score INTEGER)')
        connection.execute('INSERT INTO saved_ratings VALUES (2)')
    (instance / 'spare.db').touch()

    selected = _database_url(tmp_path, {})
    assert selected == f'sqlite:///{legacy}'
    with sqlite3.connect(selected.removeprefix('sqlite:///')) as connection:
        assert connection.execute('SELECT score FROM saved_ratings').fetchall() == [(2,)]
    assert _database_url(tmp_path, {}) == selected


def test_explicit_database_overrides_existing_database(tmp_path):
    (tmp_path / 'instance').mkdir()
    (tmp_path / 'instance' / 'syneval.db').touch()
    assert _database_url(tmp_path, {'DATABASE_URL': 'sqlite:///custom.db'}) == 'sqlite:///custom.db'
