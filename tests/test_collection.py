from unittest.mock import MagicMock

import pytest

from t3api_utils.collection.utils import parallel_load_collection


def create_response(items, total, page_size, page=1):
    """Create a MetrcCollectionResponse for testing."""
    return {
        "data": [{"id": i, "hostname": "test.com", "licenseNumber": "LIC-1", "dataModel": "TEST", "retrievedAt": "2023-01-01T00:00:00Z"} for i in items],
        "total": total,
        "page": page,
        "pageSize": page_size
    }


def test_single_page():
    mock_method = MagicMock()
    mock_method.return_value = create_response([1, 2, 3], total=3, page_size=3)

    result = parallel_load_collection(mock_method)
    assert len(result) == 1
    assert len(result[0]["data"]) == 3
    mock_method.assert_called_once()


def test_multiple_pages():
    def mock_method(page=None):
        if page is None or page == 1:
            return create_response([1, 2, 3], total=6, page_size=3, page=1)
        elif page == 2:
            return create_response([4, 5, 6], total=6, page_size=3, page=2)

    result = parallel_load_collection(mock_method)
    all_items = [item["id"] for r in result for item in r["data"]]
    assert all_items == [1, 2, 3, 4, 5, 6]


def test_page_size_inferred_from_data():
    def mock_method(page=None):
        if page is None or page == 1:
            # Create response without pageSize (should infer from data length)
            resp = create_response([1, 2], total=4, page_size=2)
            del resp["pageSize"]  # Remove pageSize to test fallback
            return resp
        elif page == 2:
            resp = create_response([3, 4], total=4, page_size=2)
            del resp["pageSize"]
            return resp

    result = parallel_load_collection(mock_method)
    all_items = [item["id"] for r in result for item in r["data"]]
    assert all_items == [1, 2, 3, 4]


def test_missing_total_raises():
    def mock_method():
        # Return a dict without total field
        return {"data": [{"id": 1, "hostname": "test.com", "licenseNumber": "LIC-1", "dataModel": "TEST", "retrievedAt": "2023-01-01T00:00:00Z"}]}

    with pytest.raises(KeyError):
        parallel_load_collection(mock_method)


def test_missing_page_size_with_empty_data_raises():
    def mock_method():
        # Return a response with total but no pageSize and empty data
        return {"total": 5, "data": [], "page": 1}

    with pytest.raises(ValueError, match="page size"):
        parallel_load_collection(mock_method)
