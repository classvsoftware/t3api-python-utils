"""T3 API client and models for httpx-based implementation.

Submodules:
    client: :class:`T3APIClient` — async httpx-based API client with authentication.
    interfaces: TypedDict definitions for API responses (auth, licenses, collections).
    operations: Sync and async helpers for sending requests and fetching collections.
    parallel: Rate-limited parallel page loading with sync and async variants.
"""