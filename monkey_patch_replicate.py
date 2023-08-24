from requests.adapters import HTTPAdapter

def monkey_patch_replicate(lib):
    client = lib.default_client

    old_adapter = client.read_session.adapters["http://"]
    adapter = HTTPAdapter(
        max_retries=old_adapter.max_retries,
        pool_connections=100,  # Number of connections in connection pool
        pool_maxsize=100,
    )

    client.read_session.mount("http://", adapter)
    client.read_session.mount("https://", adapter)

    old_adapter = client.write_session.adapters["http://"]
    adapter = HTTPAdapter(
        max_retries=old_adapter.max_retries,
        pool_connections=100,  # Number of connections in connection pool
        pool_maxsize=100,
    )

    client.write_session.mount("http://", adapter)
    client.write_session.mount("https://", adapter)
