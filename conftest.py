def pytest_collection_modifyitems(items):
    items.sort(key=lambda item: item.nodeid)
