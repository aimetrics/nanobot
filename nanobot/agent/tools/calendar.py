"""Google Calendar tool implemented directly in Python."""

import asyncio
import json
import pickle
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from nanobot.agent.tools.base import Tool


class CalendarTool(Tool):
    """First-class tool to query Google Calendar events."""

    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
    TOKEN_PATH = Path.home() / ".nanobot" / "google-token.pickle"
    CREDENTIALS_PATH = Path.home() / ".nanobot" / "google-credentials.json"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "Check Google Calendar events or run calendar auth flow."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["today", "auth"],
                    "description": "Action to perform: fetch today's events or authorize",
                },
                "json_output": {
                    "type": "boolean",
                    "description": "If true, return event list as JSON output",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds",
                    "minimum": 1,
                    "maximum": 600,
                },
                "retries": {
                    "type": "integer",
                    "description": "Retry attempts for transient failures",
                    "minimum": 0,
                    "maximum": 10,
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        json_output: bool = False,
        timeout: int = 60,
        retries: int = 3,
        **kwargs: Any,
    ) -> str:
        if action == "auth":
            return await asyncio.to_thread(self._authorize)

        return await asyncio.to_thread(
            self._get_today_output,
            json_output,
            timeout,
            retries,
        )

    def _authorize(self) -> str:
        try:
            self._get_calendar_credentials(allow_browser_auth=True)
            return "Authorization successful. Token saved to ~/.nanobot/google-token.pickle"
        except Exception as e:
            return f"Error: {e}"

    def _get_today_output(self, json_output: bool, timeout: int, retries: int) -> str:
        try:
            events = self._get_today_events(timeout=timeout, retries=retries)
            if json_output:
                return json.dumps(events, indent=2, ensure_ascii=False)
            return self._format_events(events)
        except TimeoutError as e:
            return (
                f"Timeout Error: {e}\n"
                "Troubleshooting:\n"
                "1. Check your internet connection\n"
                "2. Try again in a few moments\n"
                "3. If problem persists, run calendar(action=\"auth\")"
            )
        except Exception as e:
            return (
                f"Error: {e}\n"
                "If you see authentication errors, run calendar(action=\"auth\")"
            )

    def _get_calendar_credentials(self, allow_browser_auth: bool) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as e:
            raise RuntimeError(
                "Missing dependencies. Install with: "
                "pip install google-auth google-auth-oauthlib requests"
            ) from e

        creds = None
        if self.TOKEN_PATH.exists():
            with open(self.TOKEN_PATH, "rb") as token_file:
                creds = pickle.load(token_file)

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.TOKEN_PATH, "wb") as token_file:
                pickle.dump(creds, token_file)
            return creds

        if not allow_browser_auth:
            if not self.CREDENTIALS_PATH.exists():
                raise RuntimeError(
                    f"Credentials file not found: {self.CREDENTIALS_PATH}. "
                    "Create OAuth Desktop credentials in Google Cloud and save there, "
                    "then run calendar(action=\"auth\")."
                )
            raise RuntimeError("Not authorized yet. Run calendar(action=\"auth\") first.")

        if not self.CREDENTIALS_PATH.exists():
            raise RuntimeError(
                f"Credentials file not found: {self.CREDENTIALS_PATH}. "
                "Create OAuth Desktop credentials in Google Cloud and save it first."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.CREDENTIALS_PATH),
            self.SCOPES,
        )
        creds = flow.run_local_server(port=0)

        self.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.TOKEN_PATH, "wb") as token_file:
            pickle.dump(creds, token_file)
        return creds

    def _execute_with_retries(
        self,
        callable_request: Callable[[int], Any],
        timeout: int,
        retries: int,
        backoff_base: float = 1.5,
    ) -> Any:
        try:
            import requests
        except ImportError as e:
            raise RuntimeError("Missing dependency 'requests'. Install with: pip install requests") from e

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return callable_request(timeout)
            except (requests.Timeout, requests.ConnectionError, socket.timeout, TimeoutError, OSError) as e:
                last_error = e
            except requests.HTTPError as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status not in (401, 408, 429, 500, 502, 503, 504):
                    raise
                last_error = e

            if attempt < retries:
                time.sleep(backoff_base ** attempt)

        raise TimeoutError(
            f"Request failed after {retries + 1} attempts with timeout={timeout}s: {last_error}"
        )

    def _get_today_events(self, timeout: int = 60, retries: int = 3) -> list[dict[str, Any]]:
        try:
            import requests
            from google.auth.transport.requests import Request
        except ImportError as e:
            raise RuntimeError(
                "Missing dependencies. Install with: "
                "pip install google-auth google-auth-oauthlib requests"
            ) from e

        creds = self._get_calendar_credentials(allow_browser_auth=False)
        today = datetime.now(timezone.utc)
        start = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59, microsecond=0)

        def fetch_events_call(request_timeout: int) -> dict[str, Any]:
            if not creds.valid and creds.refresh_token:
                creds.refresh(Request())

            params = {
                "timeMin": start.isoformat(),
                "timeMax": end.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            }
            headers = {"Authorization": f"Bearer {creds.token}"}

            response = requests.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=headers,
                params=params,
                timeout=request_timeout,
            )

            if response.status_code == 401 and creds.refresh_token:
                creds.refresh(Request())
                headers["Authorization"] = f"Bearer {creds.token}"
                response = requests.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers=headers,
                    params=params,
                    timeout=request_timeout,
                )

            response.raise_for_status()
            return response.json()

        result = self._execute_with_retries(fetch_events_call, timeout=timeout, retries=retries)
        return result.get("items", [])

    def _format_events(self, events: list[dict[str, Any]]) -> str:
        if not events:
            return "HEARTBEAT_OK - No events today"

        today = datetime.now(timezone.utc)
        output = [f"Calendar - {today.strftime('%Y-%m-%d')}\n"]
        now = datetime.now(timezone.utc)

        for event in events:
            start_time = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
            end_time = event.get("end", {}).get("dateTime", event.get("end", {}).get("date"))
            title = event.get("summary", "No title")
            location = event.get("location", "")

            if not start_time or not end_time:
                continue

            if "T" in start_time:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                time_until = (start_dt - now).total_seconds() / 60

                if time_until < 30:
                    marker = "[urgent]"
                elif time_until < 60:
                    marker = "[soon]"
                elif time_until < 120:
                    marker = "[upcoming]"
                else:
                    marker = ""

                start_str = start_dt.strftime("%H:%M")
                end_str = end_dt.strftime("%H:%M")
                line = f"{marker} {start_str}-{end_str} {title}".strip()

                if 0 < time_until < 120:
                    hours = int(time_until // 60)
                    mins = int(time_until % 60)
                    time_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"
                    line += f" (in {time_str})"
            else:
                line = f"[all-day] {title}"

            if location:
                line += f"\n  location: {location}"
            output.append(line)

        return "\n".join(output)
