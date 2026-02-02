import pytest
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create application for testing."""
    from app import app as flask_app

    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": "/tmp/test_uploads",
            "WTF_CSRF_ENABLED": False,
        }
    )

    # Create upload folder
    os.makedirs(flask_app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Create all tables
    with flask_app.app_context():
        from app import db

        db.create_all()

    yield flask_app

    # Cleanup
    import shutil

    if os.path.exists(flask_app.config["UPLOAD_FOLDER"]):
        shutil.rmtree(flask_app.config["UPLOAD_FOLDER"])


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()
