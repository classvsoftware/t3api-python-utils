# connect() and auth

How `connect()` picks a credential is explained in the
[authentication guide](../guide/authentication.md).

::: t3api_utils.auth.resolve.connect

::: t3api_utils.auth.secret_keys.SecretKeys

::: t3api_utils.auth.store.Profile
    options:
      members: false

::: t3api_utils.auth.credentials.SecretKeyAuth
    options:
      members: false

::: t3api_utils.auth.credentials.BearerAuth
    options:
      members: [expires_at]
