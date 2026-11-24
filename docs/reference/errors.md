# Errors

Every exception the library raises on purpose derives from `T3Error`, and all
of them are importable from the top-level package (`t3.APIError`, ...). See
[errors and logging](../guide/errors-and-logging.md) for the tree and for what
gets retried.

::: t3api_utils.errors
    options:
      show_root_heading: false
      members:
        - T3Error
        - AuthRequired
        - NotInteractive
        - SpecError
        - UnknownEndpoint
        - APIError
        - AuthError
        - NotFound
        - ValidationError
        - TagListResolveError
        - RateLimited
        - ServerError
