"""Tests for inspector module."""

import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from t3api_utils.inspector import CollectionInspectorApp, inspect_collection
from t3api_utils.inspector.app import JSONViewer, SearchBar, StatusBar


class TestJSONViewer:
    """Test JSONViewer widget."""

    def test_json_viewer_creation(self):
        """Test JSONViewer widget creation."""
        viewer = JSONViewer()

        assert viewer.can_focus is True
        assert viewer.json_data is None
        assert hasattr(viewer, '_content_static')

    def test_json_viewer_watch_json_data_none(self):
        """Test JSONViewer with None data."""
        viewer = JSONViewer()

        # Mock the content static to avoid Textual widget issues
        viewer._content_static = MagicMock()

        viewer.watch_json_data(None)

        viewer._content_static.update.assert_called_once_with("⚠ No data available")

    def test_json_viewer_watch_json_data_valid(self):
        """Test JSONViewer with valid JSON data."""
        viewer = JSONViewer()

        # Mock the content static
        viewer._content_static = MagicMock()

        test_data = {"id": "123", "name": "Test Item", "active": True}
        expected_json = json.dumps(test_data, indent=2, ensure_ascii=False)

        viewer.watch_json_data(test_data)

        viewer._content_static.update.assert_called_once_with(expected_json)

    def test_json_viewer_watch_json_data_complex(self):
        """Test JSONViewer with complex nested data."""
        viewer = JSONViewer()

        # Mock the content static
        viewer._content_static = MagicMock()

        complex_data = {
            "id": "456",
            "metadata": {
                "created": "2024-01-01",
                "tags": ["tag1", "tag2"]
            },
            "values": [1, 2, 3]
        }
        expected_json = json.dumps(complex_data, indent=2, ensure_ascii=False)

        viewer.watch_json_data(complex_data)

        viewer._content_static.update.assert_called_once_with(expected_json)

    def test_json_viewer_watch_json_data_without_content_static(self):
        """Test JSONViewer when _content_static doesn't exist yet."""
        viewer = JSONViewer()

        # Remove _content_static to simulate before mount
        if hasattr(viewer, '_content_static'):
            delattr(viewer, '_content_static')

        test_data = {"test": "data"}

        # Should not raise an exception
        viewer.watch_json_data(test_data)


class TestSearchBar:
    """Test SearchBar widget."""

    def test_search_bar_creation(self):
        """Test SearchBar widget creation."""
        search_bar = SearchBar()

        assert isinstance(search_bar, SearchBar)

    def test_search_bar_compose(self):
        """Test SearchBar compose method."""
        search_bar = SearchBar()

        # Should be able to call compose without error
        result = list(search_bar.compose())

        assert len(result) == 1
        # The result should be some kind of widget (Input)
        assert hasattr(result[0], 'placeholder')


class TestStatusBar:
    """Test StatusBar widget."""

    def test_status_bar_creation(self):
        """Test StatusBar creation with collection name."""
        status_bar = StatusBar("Test Collection")

        assert status_bar.collection_name == "Test Collection"
        assert status_bar.current_index == 0
        assert status_bar.total_count == 0
        assert status_bar.filtered_count == 0
        assert status_bar.search_query == ""

    def test_status_bar_set_position(self):
        """Test setting position information."""
        status_bar = StatusBar("Test")

        # Mock the update method to avoid Textual widget issues
        with patch.object(status_bar, 'update') as mock_update:
            status_bar.set_position(current=5, filtered=10, total=20)

            assert status_bar.current_index == 5
            assert status_bar.filtered_count == 10
            assert status_bar.total_count == 20

    def test_status_bar_set_search(self):
        """Test setting search information."""
        status_bar = StatusBar("Test")

        # Mock the update method
        with patch.object(status_bar, 'update') as mock_update:
            status_bar.set_search("test query", 5)

            assert status_bar.search_query == "test query"
            assert status_bar.filtered_count == 5

    def test_status_bar_update_status_no_search(self):
        """Test status update without search."""
        status_bar = StatusBar("My Collection")
        status_bar.current_index = 2
        status_bar.filtered_count = 10
        status_bar.total_count = 15

        # Mock the update method
        with patch.object(status_bar, 'update') as mock_update:
            status_bar.update_status()

            expected_text = "Collection: My Collection | Position: 3/10"
            mock_update.assert_called_once_with(expected_text)

    def test_status_bar_update_status_with_search(self):
        """Test status update with search query."""
        status_bar = StatusBar("My Collection")
        status_bar.current_index = 1
        status_bar.filtered_count = 5
        status_bar.total_count = 20
        status_bar.search_query = "search term"

        # Mock the update method
        with patch.object(status_bar, 'update') as mock_update:
            status_bar.update_status()

            expected_text = "Collection: My Collection | Position: 2/5 | Search: 'search term' (5/20)"
            mock_update.assert_called_once_with(expected_text)

    def test_status_bar_update_status_empty_collection(self):
        """Test status update with empty collection."""
        status_bar = StatusBar("Empty Collection")
        status_bar.current_index = 0
        status_bar.filtered_count = 0
        status_bar.total_count = 0

        # Mock the update method
        with patch.object(status_bar, 'update') as mock_update:
            status_bar.update_status()

            expected_text = "Collection: Empty Collection | Position: 0/0"
            mock_update.assert_called_once_with(expected_text)


class TestCollectionInspectorApp:
    """Test CollectionInspectorApp."""

    def test_app_creation(self):
        """Test CollectionInspectorApp creation."""
        test_data = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]

        app = CollectionInspectorApp(data=test_data, collection_name="Test Collection")

        assert app.original_data == test_data
        assert app.filtered_data == test_data
        assert app.current_index == 0
        assert app.collection_name == "Test Collection"
        assert app.search_query == ""

    def test_app_creation_default_collection_name(self):
        """Test CollectionInspectorApp creation with default collection name."""
        test_data = [{"id": "1"}]

        app = CollectionInspectorApp(data=test_data)

        assert app.collection_name == "collection"

    def test_app_object_contains_text_string_match(self):
        """Test object text search with string values."""
        test_data = [{"id": "1"}]
        app = CollectionInspectorApp(data=test_data)

        test_obj = {"name": "Test Item", "description": "This is a test"}

        assert app._object_contains_text(obj=test_obj, search_text="test") is True
        assert app._object_contains_text(obj=test_obj, search_text="Test") is True
        assert app._object_contains_text(obj=test_obj, search_text="item") is True
        assert app._object_contains_text(obj=test_obj, search_text="missing") is False

    def test_app_object_contains_text_numeric_match(self):
        """Test object text search with numeric values."""
        test_data = [{"id": "1"}]
        app = CollectionInspectorApp(data=test_data)

        test_obj = {"id": 123, "price": 45.67, "active": True}

        assert app._object_contains_text(obj=test_obj, search_text="123") is True
        assert app._object_contains_text(obj=test_obj, search_text="45") is True
        assert app._object_contains_text(obj=test_obj, search_text="true") is True
        assert app._object_contains_text(obj=test_obj, search_text="999") is False

    def test_app_object_contains_text_nested_match(self):
        """Test object text search with nested objects."""
        test_data = [{"id": "1"}]
        app = CollectionInspectorApp(data=test_data)

        test_obj = {
            "id": "123",
            "metadata": {
                "created": "2024-01-01",
                "tags": ["important", "test"]
            }
        }

        assert app._object_contains_text(obj=test_obj, search_text="2024") is True
        assert app._object_contains_text(obj=test_obj, search_text="important") is True
        assert app._object_contains_text(obj=test_obj, search_text="test") is True
        assert app._object_contains_text(obj=test_obj, search_text="missing") is False

    def test_app_apply_search_filter_empty_query(self):
        """Test applying empty search filter."""
        test_data = [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}]
        app = CollectionInspectorApp(data=test_data)

        # Mock _update_display to avoid Textual widget issues
        with patch.object(app, '_update_display'):
            app._apply_search_filter(query="")

            assert app.search_query == ""
            assert app.filtered_data == test_data
            assert app.current_index == 0

    def test_app_apply_search_filter_with_matches(self):
        """Test applying search filter with matches."""
        test_data = [
            {"id": "1", "name": "Apple"},
            {"id": "2", "name": "Banana"},
            {"id": "3", "name": "Cherry"}
        ]
        app = CollectionInspectorApp(data=test_data)

        # Mock _update_display to avoid Textual widget issues
        with patch.object(app, '_update_display'):
            app._apply_search_filter(query="a")  # Should match Apple and Banana

            assert app.search_query == "a"
            assert len(app.filtered_data) == 2
            assert app.filtered_data[0]["name"] == "Apple"
            assert app.filtered_data[1]["name"] == "Banana"
            assert app.current_index == 0

    def test_app_apply_search_filter_no_matches(self):
        """Test applying search filter with no matches."""
        test_data = [{"id": "1", "name": "Apple"}, {"id": "2", "name": "Banana"}]
        app = CollectionInspectorApp(data=test_data)

        # Mock _update_display to avoid Textual widget issues
        with patch.object(app, '_update_display'):
            app._apply_search_filter(query="xyz")

            assert app.search_query == "xyz"
            assert app.filtered_data == []
            assert app.current_index == 0

    def test_app_action_navigation(self):
        """Test navigation actions."""
        test_data = [{"id": str(i)} for i in range(5)]
        app = CollectionInspectorApp(data=test_data)

        # Mock _update_display to avoid Textual widget issues
        with patch.object(app, '_update_display'):
            # Test next navigation
            app.action_next()
            assert app.current_index == 1

            app.action_next()
            assert app.current_index == 2

            # Test previous navigation
            app.action_previous()
            assert app.current_index == 1

            # Test first navigation
            app.action_first()
            assert app.current_index == 0

            # Test last navigation
            app.action_last()
            assert app.current_index == 4

    def test_app_action_navigation_bounds(self):
        """Test navigation actions with boundary conditions."""
        test_data = [{"id": "1"}, {"id": "2"}]
        app = CollectionInspectorApp(data=test_data)

        # Mock _update_display
        with patch.object(app, '_update_display'):
            # At first position, previous should do nothing
            app.current_index = 0
            app.action_previous()
            assert app.current_index == 0

            # At last position, next should do nothing
            app.current_index = 1
            app.action_next()
            assert app.current_index == 1

    def test_app_action_navigation_empty_data(self):
        """Test navigation actions with empty data."""
        app = CollectionInspectorApp(data=[])

        # Mock _update_display
        with patch.object(app, '_update_display'):
            # All navigation should be safe with empty data
            app.action_next()
            app.action_previous()
            app.action_first()
            app.action_last()

            assert app.current_index == 0

    @patch('t3api_utils.inspector.app.Input')
    def test_app_action_clear(self, mock_input_class):
        """Test clear search action."""
        test_data = [{"id": "1"}]
        app = CollectionInspectorApp(data=test_data)

        # Mock the input widget and query methods
        mock_input = MagicMock()
        mock_status = MagicMock()

        with patch.object(app, 'query_one') as mock_query_one, \
             patch.object(app, '_apply_search_filter') as mock_apply_filter:

            mock_query_one.side_effect = lambda selector, widget_type=None: {
                "#search-input": mock_input,
                "#status": mock_status
            }[selector]

            app.action_clear()

            mock_input.value = ""
            mock_apply_filter.assert_called_once_with(query="")
            mock_status.set_search.assert_called_once()

    @patch('t3api_utils.inspector.app.Input')
    def test_app_action_focus_search(self, mock_input_class):
        """Test focus search action."""
        test_data = [{"id": "1"}]
        app = CollectionInspectorApp(data=test_data)

        # Mock the input widget and query method
        mock_input = MagicMock()
        with patch.object(app, 'query_one', return_value=mock_input) as mock_query_one:
            app.action_focus_search()

            mock_query_one.assert_called_once()
            mock_input.focus.assert_called_once()

    def test_app_action_help(self):
        """Test help action."""
        test_data = [{"id": "1"}]
        app = CollectionInspectorApp(data=test_data)

        # Mock notify method
        with patch.object(app, 'notify') as mock_notify:
            app.action_help()

            mock_notify.assert_called_once()
            args, kwargs = mock_notify.call_args
            assert "Navigation" in args[0]
            assert kwargs.get("severity") == "information"


class TestInspectCollection:
    """Test inspect_collection function."""

    @patch('t3api_utils.inspector.app.CollectionInspectorApp')
    def test_inspect_collection_with_data(self, mock_app_class):
        """Test inspect_collection with valid data."""
        test_data = [{"id": "1", "name": "Test"}]
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app

        inspect_collection(data=test_data, collection_name="Test Collection")

        mock_app_class.assert_called_once_with(data=test_data, collection_name="Test Collection")
        mock_app.run.assert_called_once()

    @patch('t3api_utils.inspector.app.CollectionInspectorApp')
    def test_inspect_collection_default_name(self, mock_app_class):
        """Test inspect_collection with default collection name."""
        test_data = [{"id": "1"}]
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app

        inspect_collection(data=test_data)

        mock_app_class.assert_called_once_with(data=test_data, collection_name="collection")
        mock_app.run.assert_called_once()

    @patch('t3api_utils.inspector.app.print_info')
    def test_inspect_collection_empty_data(self, mock_print_info):
        """Test inspect_collection with empty data."""
        inspect_collection(data=[])

        mock_print_info.assert_called_once_with("No data to inspect")

    @patch('t3api_utils.inspector.app.print_info')
    def test_inspect_collection_none_data(self, mock_print_info):
        """Test inspect_collection with None-like empty data."""
        # Test with empty list
        inspect_collection(data=[])
        mock_print_info.assert_called_once_with("No data to inspect")


class TestInspectorModule:
    """Test inspector module structure."""

    def test_module_imports(self):
        """Test inspector module imports."""
        import t3api_utils.inspector as inspector

        assert hasattr(inspector, 'CollectionInspectorApp')
        assert hasattr(inspector, 'inspect_collection')

    def test_module_exports(self):
        """Test inspector module __all__ exports."""
        from t3api_utils.inspector import __all__

        expected_exports = ["CollectionInspectorApp", "inspect_collection"]
        assert __all__ == expected_exports

    def test_cross_module_imports(self):
        """Test importing specific items from inspector."""
        from t3api_utils.inspector import CollectionInspectorApp, inspect_collection
        from t3api_utils.inspector.app import JSONViewer, SearchBar, StatusBar

        # Should be able to import all components
        assert CollectionInspectorApp is not None
        assert inspect_collection is not None
        assert JSONViewer is not None
        assert SearchBar is not None
        assert StatusBar is not None


class TestInspectorIntegration:
    """Test inspector integration scenarios."""

    def test_end_to_end_workflow(self):
        """Test complete inspector workflow simulation."""
        # Simulate real-world data
        test_data: List[Dict[str, Any]] = [
            {"id": "PKG123", "type": "Package", "status": "Active", "quantity": 100},
            {"id": "PKG456", "type": "Package", "status": "Inactive", "quantity": 0},
            {"id": "PLT789", "type": "Plant", "status": "Growing", "strain": "OG Kush"}
        ]

        app = CollectionInspectorApp(data=test_data, collection_name="Cannabis Inventory")

        # Mock _update_display to avoid Textual issues
        with patch.object(app, '_update_display'):
            # Test search functionality
            app._apply_search_filter(query="Package")
            assert len(app.filtered_data) == 2
            assert all("Package" in str(item.values()) for item in app.filtered_data)

            app._apply_search_filter(query="Active")
            # "Active" should match PKG123 with status "Active", and "Inactive" contains "Active"
            assert len(app.filtered_data) == 2

            # Test navigation after filtering
            app.action_first()
            assert app.current_index == 0

            # Clear filter
            app._apply_search_filter(query="")
            assert len(app.filtered_data) == 3
            assert app.filtered_data == test_data

    def test_search_edge_cases(self):
        """Test search functionality edge cases."""
        test_data: List[Dict[str, Any]] = [
            {"id": 123, "name": None, "active": True},
            {"nested": {"deep": {"value": "hidden"}}},
            {"list_field": [1, "two", {"three": 3}]}
        ]

        app = CollectionInspectorApp(data=test_data)

        # Mock _update_display to avoid Textual widget issues
        with patch.object(app, '_update_display'):
            # Search for numeric values
            app._apply_search_filter(query="123")
            assert len(app.filtered_data) == 1

            # Search in nested objects
            app._apply_search_filter(query="hidden")
            assert len(app.filtered_data) == 1

            # Search in lists
            app._apply_search_filter(query="two")
            assert len(app.filtered_data) == 1

            # Search for boolean values
            app._apply_search_filter(query="true")
            assert len(app.filtered_data) == 1

    def test_large_dataset_performance(self):
        """Test inspector with large dataset."""
        # Create a large dataset
        large_data = [
            {"id": f"ITEM_{i:05d}", "value": i % 100, "category": f"CAT_{i % 10}"}
            for i in range(1000)
        ]

        app = CollectionInspectorApp(data=large_data, collection_name="Large Dataset")

        # Mock _update_display
        with patch.object(app, '_update_display'):
            # Test that filtering still works efficiently
            app._apply_search_filter(query="CAT_5")
            assert len(app.filtered_data) == 100  # Every 10th item

            # Test navigation with large filtered dataset
            app.action_last()
            assert app.current_index == 99  # Last item in filtered set