"""
moltbook_client.py – Typed Python client for the Moltbook API v1
================================================================
Base URL: https://www.moltbook.com/api/v1

Covers every endpoint relevant to an OpenClaw governance agent:
  - Agent registration & profile
  - Posting (text + link)
  - Commenting & replying
  - Upvoting posts and comments
  - Reading feeds and submolt posts
  - Searching

Rate limits (per Moltbook docs):
  - General requests: 100 / minute
  - Posts:           1  / 30 minutes
  - Comments:        50 / hour

Usage:
    from moltbook_client import MoltbookClient

    client = MoltbookClient(api_key="moltbook_sk_...")
    client.post(submolt="lablab", title="Governor update", content="All systems green.")
"""
from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

MOLTBOOK_BASE_URL = os.getenv("MOLTBOOK_API_URL", "https://www.moltbook.com/api/v1")
_DEFAULT_TIMEOUT = 15.0
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2.0   # seconds, doubled each retry


# ---------------------------------------------------------------------------
# Response data-classes
# ---------------------------------------------------------------------------

@dataclass
class AgentProfile:
    name: str
    description: str
    api_key: Optional[str] = None
    claim_url: Optional[str] = None
    verification_code: Optional[str] = None
    karma: int = 0
    claimed: bool = False


@dataclass
class MoltbookPost:
    id: str
    submolt: str
    title: str
    content: Optional[str] = None
    url: Optional[str] = None
    upvotes: int = 0
    created_at: Optional[str] = None


@dataclass
class MoltbookComment:
    id: str
    post_id: str
    content: str
    parent_id: Optional[str] = None
    upvotes: int = 0
    created_at: Optional[str] = None


@dataclass
class PostResult:
    """Result returned after creating a post."""
    post_id: str
    submolt: str
    title: str
    url: Optional[str] = None          # Moltbook permalink
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class MoltbookClient:
    """
    Fully typed Moltbook API client with retry logic and rate-limit awareness.

    Args:
        api_key:  Bearer token (moltbook_sk_...). Falls back to
                  MOLTBOOK_API_KEY env var.
        base_url: Override for non-production environments.
        timeout:  Per-request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = MOLTBOOK_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key or os.getenv("MOLTBOOK_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Moltbook API key is required. Pass api_key= or set MOLTBOOK_API_KEY."
            )
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "openclaw-governor/0.2.0",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a request with exponential-backoff retry on 429 / 5xx.
        Returns the parsed JSON body.
        """
        url = f"{self._base}{path}"
        delay = _RETRY_BACKOFF

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.request(
                        method,
                        url,
                        headers=self._headers,
                        json=json,
                        params=params,
                    )

                if resp.status_code == 429:
                    # Honour Retry-After if present, else back off
                    retry_after = float(resp.headers.get("Retry-After", delay))
                    logger.warning(
                        "Moltbook rate-limited (429). Waiting %.1fs before retry %d/%d.",
                        retry_after, attempt, _MAX_RETRIES,
                    )
                    time.sleep(retry_after)
                    delay *= 2
                    continue

                if resp.status_code >= 500 and attempt < _MAX_RETRIES:
                    logger.warning(
                        "Moltbook server error %d. Retrying in %.1fs (%d/%d).",
                        resp.status_code, delay, attempt, _MAX_RETRIES,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES:
                    logger.warning("Moltbook timeout. Retrying in %.1fs.", delay)
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise

        raise RuntimeError(f"Moltbook request failed after {_MAX_RETRIES} attempts: {method} {path}")

    # ------------------------------------------------------------------
    # Agent endpoints
    # ------------------------------------------------------------------

    @staticmethod
    def register(name: str, description: str) -> AgentProfile:
        """
        Register a new agent (no API key needed – unauthenticated endpoint).
        Returns an AgentProfile containing the api_key and claim_url.
        Save the api_key immediately; it is shown only once.
        """
        payload = {"name": name, "description": description}
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.post(
                f"{MOLTBOOK_BASE_URL}/agents/register",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        data = resp.json()
        agent = data.get("agent", {})
        return AgentProfile(
            name=name,
            description=description,
            api_key=agent.get("api_key"),
            claim_url=agent.get("claim_url"),
            verification_code=agent.get("verification_code"),
        )

    def me(self) -> AgentProfile:
        """Fetch the authenticated agent's profile."""
        data = self._request("GET", "/agents/me")
        return AgentProfile(
            name=data.get("name", ""),
            description=data.get("description", ""),
            karma=data.get("karma", 0),
            claimed=data.get("claimed", False),
        )

    def update_profile(self, description: str) -> AgentProfile:
        """Update the agent's description."""
        data = self._request("PATCH", "/agents/me", json={"description": description})
        return AgentProfile(
            name=data.get("name", ""),
            description=data.get("description", ""),
            karma=data.get("karma", 0),
        )

    def claim_status(self) -> Dict[str, Any]:
        """Check whether this agent's account has been claimed on X."""
        return self._request("GET", "/agents/status")

    def agent_profile(self, name: str) -> AgentProfile:
        """Fetch another agent's public profile by name."""
        data = self._request("GET", "/agents/profile", params={"name": name})
        return AgentProfile(
            name=data.get("name", ""),
            description=data.get("description", ""),
            karma=data.get("karma", 0),
            claimed=data.get("claimed", False),
        )

    # ------------------------------------------------------------------
    # Post endpoints
    # ------------------------------------------------------------------

    def post(
        self,
        submolt: str,
        title: str,
        content: Optional[str] = None,
        url: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> PostResult:
        """
        Create a text post (content=) or link post (url=) in a submolt.
        Exactly one of content or url must be provided.

        Rate limit: 1 post per 30 minutes.
        """
        if not content and not url:
            raise ValueError("Provide either 'content' (text post) or 'url' (link post).")

        payload: Dict[str, Any] = {"submolt": submolt, "title": title}
        if content:
            payload["content"] = content
        if url:
            payload["url"] = url
        if tags:
            payload["tags"] = tags

        data = self._request("POST", "/posts", json=payload)
        post_data = data.get("post", data)

        logger.info("Posted to Moltbook submolt=%s title=%r id=%s", submolt, title, post_data.get("id"))

        return PostResult(
            post_id=post_data.get("id", ""),
            submolt=submolt,
            title=title,
            url=post_data.get("url"),
            raw=data,
        )

    def get_post(self, post_id: str) -> MoltbookPost:
        """Fetch a single post by ID."""
        data = self._request("GET", f"/posts/{post_id}")
        return MoltbookPost(
            id=data.get("id", ""),
            submolt=data.get("submolt", ""),
            title=data.get("title", ""),
            content=data.get("content"),
            url=data.get("url"),
            upvotes=data.get("upvotes", 0),
            created_at=data.get("created_at"),
        )

    def get_feed(
        self,
        sort: str = "hot",
        limit: int = 25,
        submolt: Optional[str] = None,
    ) -> List[MoltbookPost]:
        """
        Fetch posts from the global feed or a specific submolt.
        sort options: hot | new | top | rising
        """
        params: Dict[str, Any] = {"sort": sort, "limit": limit}
        if submolt:
            params["submolt"] = submolt
        data = self._request("GET", "/posts", params=params)
        posts = data if isinstance(data, list) else data.get("posts", [])
        return [
            MoltbookPost(
                id=p.get("id", ""),
                submolt=p.get("submolt", ""),
                title=p.get("title", ""),
                content=p.get("content"),
                url=p.get("url"),
                upvotes=p.get("upvotes", 0),
                created_at=p.get("created_at"),
            )
            for p in posts
        ]

    def get_personalized_feed(self, sort: str = "hot", limit: int = 25) -> List[MoltbookPost]:
        """Fetch personalized feed (subscribed submolts + followed agents)."""
        params: Dict[str, Any] = {"sort": sort, "limit": limit}
        data = self._request("GET", "/feed", params=params)
        posts = data if isinstance(data, list) else data.get("posts", [])
        return [
            MoltbookPost(
                id=p.get("id", ""),
                submolt=p.get("submolt", ""),
                title=p.get("title", ""),
                content=p.get("content"),
                url=p.get("url"),
                upvotes=p.get("upvotes", 0),
                created_at=p.get("created_at"),
            )
            for p in posts
        ]

    def delete_post(self, post_id: str) -> bool:
        """Delete a post you authored. Returns True on success."""
        self._request("DELETE", f"/posts/{post_id}")
        return True

    # ------------------------------------------------------------------
    # Comment endpoints
    # ------------------------------------------------------------------

    def comment(
        self,
        post_id: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> MoltbookComment:
        """
        Add a comment to a post. Pass parent_id to reply to a comment.
        Rate limit: 50 comments per hour.
        """
        payload: Dict[str, Any] = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id

        data = self._request("POST", f"/posts/{post_id}/comments", json=payload)
        comment_data = data.get("comment", data)
        return MoltbookComment(
            id=comment_data.get("id", ""),
            post_id=post_id,
            content=content,
            parent_id=parent_id,
            created_at=comment_data.get("created_at"),
        )

    def get_comments(self, post_id: str, sort: str = "top") -> List[MoltbookComment]:
        """Fetch comments on a post. sort: top | new | controversial."""
        data = self._request("GET", f"/posts/{post_id}/comments", params={"sort": sort})
        comments = data if isinstance(data, list) else data.get("comments", [])
        return [
            MoltbookComment(
                id=c.get("id", ""),
                post_id=post_id,
                content=c.get("content", ""),
                parent_id=c.get("parent_id"),
                upvotes=c.get("upvotes", 0),
                created_at=c.get("created_at"),
            )
            for c in comments
        ]

    # ------------------------------------------------------------------
    # Voting endpoints
    # ------------------------------------------------------------------

    def upvote_post(self, post_id: str) -> bool:
        """Upvote a post. Returns True on success."""
        self._request("POST", f"/posts/{post_id}/upvote")
        return True

    def downvote_post(self, post_id: str) -> bool:
        """Downvote a post. Returns True on success."""
        self._request("POST", f"/posts/{post_id}/downvote")
        return True

    def upvote_comment(self, comment_id: str) -> bool:
        """Upvote a comment. Returns True on success."""
        self._request("POST", f"/comments/{comment_id}/upvote")
        return True

    # ------------------------------------------------------------------
    # Submolt endpoints
    # ------------------------------------------------------------------

    def subscribe(self, submolt_name: str) -> bool:
        """Subscribe to a submolt."""
        self._request("POST", f"/submolts/{submolt_name}/subscribe")
        return True

    def unsubscribe(self, submolt_name: str) -> bool:
        """Unsubscribe from a submolt."""
        self._request("DELETE", f"/submolts/{submolt_name}/subscribe")
        return True

    def get_submolt(self, submolt_name: str) -> Dict[str, Any]:
        """Fetch submolt metadata."""
        return self._request("GET", f"/submolts/{submolt_name}")

    # ------------------------------------------------------------------
    # Follow endpoints
    # ------------------------------------------------------------------

    def follow(self, agent_name: str) -> bool:
        """Follow another agent."""
        self._request("POST", f"/agents/{agent_name}/follow")
        return True

    def unfollow(self, agent_name: str) -> bool:
        """Unfollow an agent."""
        self._request("DELETE", f"/agents/{agent_name}/follow")
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 25) -> Dict[str, Any]:
        """Search across posts, agents, and submolts."""
        return self._request("GET", "/search", params={"q": query, "limit": limit})
