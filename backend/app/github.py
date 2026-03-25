"""GitHub API client utilities.

Usage example::

    from app.github import get_github_client, list_org_repos

    async with get_github_client(token) as client:
        resp = await client.get("https://api.github.com/user")
        ...

    repos = await list_org_repos("myorg", token)
"""

from typing import Any

import httpx

_GITHUB_API_BASE = "https://api.github.com"
_GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


async def get_github_client(token: str) -> httpx.AsyncClient:
    """Return a pre-configured :class:`httpx.AsyncClient` with the GitHub
    ``Authorization`` header set.

    The caller is responsible for closing the client (use as an async context
    manager)::

        async with get_github_client(token) as client:
            ...
    """
    return httpx.AsyncClient(
        base_url=_GITHUB_API_BASE,
        headers={
            **_GITHUB_HEADERS,
            "Authorization": f"Bearer {token}",
        },
    )


async def list_org_repos(org: str, token: str) -> list[dict[str, Any]]:
    """Return the list of repositories for *org*.

    Makes a single paginated request (up to 100 results).  For full
    pagination support callers should iterate over pages directly using
    :func:`get_github_client`.
    """
    client = await get_github_client(token)
    async with client as c:
        response = await c.get(f"/orgs/{org}/repos", params={"per_page": 100})
        response.raise_for_status()
        return response.json()
