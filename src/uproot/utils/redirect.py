# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Safe redirect utilities to prevent open redirect vulnerabilities."""

from fastapi.responses import Response


def safe_redirect(url: str) -> str:
    """Ensure redirect URL is safe by validating it's a relative URL.

    This prevents open redirect vulnerabilities by ensuring the URL:
    - Starts with / (relative to our domain)
    - Doesn't start with // (which would be protocol-relative)
    """
    if not url.startswith("/"):
        raise ValueError("Redirect URL must be relative")
    if url.startswith("//"):
        raise ValueError("Protocol-relative URLs not allowed")
    return url


def safe_redirect_response(url: str, status_code: int = 303) -> Response:
    response = Response(status_code=status_code)
    response.headers["Location"] = safe_redirect(url)
    return response
