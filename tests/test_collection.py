from unittest.mock import MagicMock

import pytest

from t3api_utils.collection.utils import parallel_load_collection


class Response:
    def __init__(self, items, total, page_size):
        self.items = items
        self.total = total
        self.page_size = page_size

    def __len__(self):
        return len(self.items)


def test_single_page():
    mock_method = MagicMock()
    mock_method.return_value = Response([1, 2, 3], total=3, page_size=3)

    result = parallel_load_collection(mock_method)
    assert len(result) == 1
    assert result[0].items == [1, 2, 3]
    mock_method.assert_called_once()


def test_multiple_pages():
    def mock_method(page=None):
        if page is None or page == 1:
            return Response([1, 2, 3], total=6, page_size=3)
        elif page == 2:
            return Response([4, 5, 6], total=6, page_size=3)

    result = parallel_load_collection(mock_method)
    all_items = [item for r in result for item in r.items]
    assert all_items == [1, 2, 3, 4, 5, 6]


def test_page_size_fallback_to_len():
    class LenOnlyResponse:
        def __init__(self, items, total):
            self.items = items
            self.total = total
        def __len__(self):
            return len(self.items)

    def mock_method(page=None):
        if page is None or page == 1:
            return LenOnlyResponse([1, 2], total=4)
        elif page == 2:
            return LenOnlyResponse([3, 4], total=4)

    result = parallel_load_collection(mock_method)
    all_items = [item for r in result for item in r.items]
    assert all_items == [1, 2, 3, 4]


def test_missing_total_raises():
    class NoTotal:
        def __len__(self): return 1

    mock_method = MagicMock()
    mock_method.return_value = NoTotal()

    with pytest.raises(ValueError, match="total"):
        parallel_load_collection(mock_method)


def test_missing_page_size_and_len_raises():
    class NoLenNoPageSize:
        def __init__(self):
            self.total = 5

    mock_method = MagicMock()
    mock_method.return_value = NoLenNoPageSize()

    with pytest.raises(ValueError, match="page size"):
        parallel_load_collection(mock_method)
