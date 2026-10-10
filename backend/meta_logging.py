"""Avoid leaking opaque media grants and webhook challenge secrets in access logs."""

import logging


class MetaAccessFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            address, method, path, version, status = record.args
            if "/meta/" in str(path):
                record.args = (address, method, "/api/meta/[redacted]", version, status)
        return True


def install():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, MetaAccessFilter) for f in logger.filters):
        logger.addFilter(MetaAccessFilter())
