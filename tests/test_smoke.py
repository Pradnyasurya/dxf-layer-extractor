"""Basic smoke tests for the DXF Layer Validator."""


class TestAppInitialization:
    """Test that the Flask app initializes correctly."""

    def test_app_exists(self, app):
        """Test that the app fixture creates an app instance."""
        assert app is not None

    def test_app_is_testing(self, app):
        """Test that the app is in testing mode."""
        assert app.config["TESTING"] is True

    def test_database_uri_is_sqlite_memory(self, app):
        """Test that we use an in-memory database for tests."""
        assert ":memory:" in app.config["SQLALCHEMY_DATABASE_URI"]


class TestRoutesSmoke:
    """Smoke tests for main routes - just check they don't crash."""

    def test_index_route_redirects_to_login(self, client):
        """Test that index redirects when not logged in."""
        response = client.get("/", follow_redirects=False)
        # Should redirect to login page
        assert response.status_code == 302
        assert "/login" in response.location

    def test_login_page_loads(self, client):
        """Test that login page loads without errors."""
        response = client.get("/login")
        assert response.status_code == 200
        assert b"Login" in response.data or b"login" in response.data.lower()

    def test_register_page_loads(self, client):
        """Test that register page loads without errors."""
        response = client.get("/register")
        assert response.status_code == 200
        assert b"Register" in response.data or b"register" in response.data.lower()


class TestHealth:
    """Health check tests."""

    def test_imports_work(self):
        """Test that all main modules can be imported."""
        try:
            import app
            import comparison_engine

            assert True
        except ImportError as e:
            pytest.fail(f"Failed to import modules: {e}")

    def test_ezdxf_available(self):
        """Test that ezdxf is available and working."""
        import ezdxf

        version = ezdxf.__version__
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0


class TestJSONFiles:
    """Test that JSON rule files are valid."""

    def test_odisha_layers_json_is_valid(self):
        """Test that odisha_layers.json is valid JSON."""
        import json
        import os

        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "odisha_layers.json"
        )

        with open(filepath, "r") as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) > 0
        # Check first item has expected keys
        first_item = data[0]
        assert isinstance(first_item, dict)
        assert "Layer Name" in first_item

    def test_ppa_layers_json_is_valid(self):
        """Test that ppa_layers.json is valid JSON."""
        import json
        import os

        filepath = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "ppa_layers.json"
        )

        with open(filepath, "r") as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) > 0
