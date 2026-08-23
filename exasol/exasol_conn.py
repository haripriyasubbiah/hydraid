"""
Shared connection helper for HydraID's Exasol scripts.

The original scripts connected with:
    pyexasol.connect(dsn='localhost:8563', user='sys', password='exasol',
                      schema='HYDRAID', websocket_sslopt={'cert_reqs': 0})

That's *missing* `encryption=True`. Exasol Nano (the image docker-compose.yml
now uses) terminates TLS on the SQL port by default, so without
`encryption=True` the connection just hangs/fails instead of connecting.
`websocket_sslopt={'cert_reqs': 0}` is still needed on top of that, to accept
Nano's self-signed dev certificate.

Password defaults to Nano's out-of-the-box default ("exasol"). If you set a
real password on first boot (see docker-compose.yml), export
HYDRAID_DB_PASSWORD before running any of these scripts instead of editing
this file.
"""

import os
import ssl
import pyexasol

DSN = os.environ.get("HYDRAID_DB_DSN", "localhost:8563")
USER = os.environ.get("HYDRAID_DB_USER", "sys")
PASSWORD = os.environ.get("HYDRAID_DB_PASSWORD", "exasol")
SCHEMA = os.environ.get("HYDRAID_DB_SCHEMA", "HYDRAID")


def connect(schema=SCHEMA):
    return pyexasol.connect(
        dsn=DSN,
        user=USER,
        password=PASSWORD,
        schema=schema,
        encryption=True,
        websocket_sslopt={"cert_reqs": ssl.CERT_NONE},
    )
