"""Tests for route sorting functionality in FastAPI extension."""
from contract_governor.extensions.fastapi_extension import sort_routes_for_fastapi


class TestSortRoutesForFastapi:
    """Test suite for sort_routes_for_fastapi function."""

    def test_static_before_parameterized_same_level(self):
        """Static routes should come before parameterized routes at the same path level."""
        paths = {
            '/files/{id}': {},
            '/files/search': {},
            '/files': {},
        }

        result = sort_routes_for_fastapi(paths)

        # /files/search (static) should come before /files/{id} (parameterized)
        assert result.index('/files/search') < result.index('/files/{id}')

    def test_file_browser_real_world_case(self):
        """Test the actual file_browser case that caused the bug."""
        paths = {
            '/files': {},
            '/files/{base_filename}': {},
            '/files/search': {},
        }

        result = sort_routes_for_fastapi(paths)

        # /files/search MUST come before /files/{base_filename}
        assert result.index('/files/search') < result.index('/files/{base_filename}')
        # /files should be first (shortest path)
        assert result[0] == '/files'

    def test_nested_paths_static_before_parameterized(self):
        """Static routes should come before parameterized at nested levels too."""
        paths = {
            '/users/{id}/posts': {},
            '/users/{id}/posts/{post_id}': {},  # parameterized at same level as 'latest'
            '/users/{id}/posts/latest': {},      # static at same level as {post_id}
            '/users/{id}': {},
            '/users/search': {},
            '/users': {},
        }

        result = sort_routes_for_fastapi(paths)

        # /users/search should come before /users/{id}
        assert result.index('/users/search') < result.index('/users/{id}')
        # /users/{id}/posts/latest (static 'latest') should come before /users/{id}/posts/{post_id}
        assert result.index('/users/{id}/posts/latest') < result.index('/users/{id}/posts/{post_id}')

    def test_preserves_order_when_no_conflicts(self):
        """When there are no static/parameterized conflicts, alphabetical order is used."""
        paths = {
            '/alpha': {},
            '/beta': {},
            '/gamma': {},
        }

        result = sort_routes_for_fastapi(paths)

        assert result == ['/alpha', '/beta', '/gamma']

    def test_empty_paths(self):
        """Empty paths dict should return empty list."""
        result = sort_routes_for_fastapi({})
        assert result == []

    def test_single_path(self):
        """Single path should return list with that path."""
        paths = {'/health': {}}
        result = sort_routes_for_fastapi(paths)
        assert result == ['/health']

    def test_multiple_parameterized_segments(self):
        """Paths with multiple parameterized segments should sort correctly."""
        paths = {
            '/orgs/{org_id}/repos/{repo_id}': {},
            '/orgs/{org_id}/repos/starred': {},
            '/orgs/{org_id}/settings': {},
            '/orgs/public': {},
        }

        result = sort_routes_for_fastapi(paths)

        # /orgs/public should come before /orgs/{org_id}/*
        assert result.index('/orgs/public') < result.index('/orgs/{org_id}/settings')
        # /orgs/{org_id}/repos/starred should come before /orgs/{org_id}/repos/{repo_id}
        assert result.index('/orgs/{org_id}/repos/starred') < result.index('/orgs/{org_id}/repos/{repo_id}')

    def test_depth_sorting(self):
        """Shorter paths should come before longer paths."""
        paths = {
            '/a/b/c': {},
            '/a': {},
            '/a/b': {},
        }

        result = sort_routes_for_fastapi(paths)

        assert result == ['/a', '/a/b', '/a/b/c']

    def test_complex_api_structure(self):
        """Test a complex API structure similar to real-world usage."""
        paths = {
            '/api/v1/items': {},
            '/api/v1/items/{item_id}': {},
            '/api/v1/items/search': {},
            '/api/v1/items/{item_id}/comments': {},
            '/api/v1/items/{item_id}/comments/{comment_id}': {},
            '/api/v1/items/{item_id}/comments/recent': {},
            '/api/v1/users': {},
            '/api/v1/users/{user_id}': {},
            '/api/v1/users/me': {},
        }

        result = sort_routes_for_fastapi(paths)

        # Verify critical orderings
        assert result.index('/api/v1/items/search') < result.index('/api/v1/items/{item_id}')
        assert result.index('/api/v1/users/me') < result.index('/api/v1/users/{user_id}')
        assert result.index('/api/v1/items/{item_id}/comments/recent') < result.index('/api/v1/items/{item_id}/comments/{comment_id}')
