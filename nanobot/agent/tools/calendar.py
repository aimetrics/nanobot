"""Google Calendar tool implemented directly in Python."""

import asyncio
import json
import pickle
import re
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from nanobot.agent.tools.base import Tool


class CalendarTool(Tool):
    """First-class tool to query and create Google Calendar events."""

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    TOKEN_PATH = Path.home() / ".nanobot" / "google-token.pickle"
    CREDENTIALS_PATH = Path.home() / ".nanobot" / "google-credentials.json"
    TIME_RANGE_PATTERN = re.compile(r"(?P<start>\d{1,2}:\d{2})\s*[-~到至]\s*(?P<end>\d{1,2}:\d{2})")

    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "Check Google Calendar events, authorize, or create new events."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["today", "auth", "create"],
                    "description": "Action to perform: fetch today's events, authorize, or create event",
                },
                "json_output": {
                    "type": "boolean",
                    "description": "If true, return event list as JSON output for action=today",
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
                "title": {
                    "type": "string",
                    "description": "Event title for action=create",
                },
                "start": {
                    "type": "string",
                    "description": "Start datetime in ISO format with timezone, e.g. 2026-02-11T17:30:00+08:00",
                },
                "end": {
                    "type": "string",
                    "description": "End datetime in ISO format with timezone, e.g. 2026-02-11T19:00:00+08:00",
                },
                "location": {
                    "type": "string",
                    "description": "Optional event location for action=create",
                },
                "description": {
                    "type": "string",
                    "description": "Optional event description for action=create",
                },
                "text": {
                    "type": "string",
                    "description": "Optional natural-language input for action=create, e.g. '17:30-19:00跑步'",
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
        title: str | None = None,
        start: str | None = None,
        end: str | None = None,
        location: str | None = None,
        description: str | None = None,
        text: str | None = None,
        **kwargs: Any,
    ) -> str:
        if action == "auth":
            return await asyncio.to_thread(self._authorize)

        if action == "create":
            return await asyncio.to_thread(
                self._create_event_output,
                title,
                start,
                end,
                location,
                description,
                text,
                timeout,
                retries,
            )

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
                "If this looks like a permissions/scope issue, run calendar(action=\"auth\") again."
            )

    def _create_event_output(
        self,
        title: str | None,
        start: str | None,
        end: str | None,
        location: str | None,
        description: str | None,
        text: str | None,
        timeout: int,
        retries: int,
    ) -> str:
        try:
            payload = self._resolve_create_payload(title, start, end, location, description, text)
            created = self._create_event(payload, timeout=timeout, retries=retries)
            start_text = created.get("start", {}).get("dateTime", created.get("start", {}).get("date", ""))
            end_text = created.get("end", {}).get("dateTime", created.get("end", {}).get("date", ""))
            return (
                "Created calendar event successfully.\n"
                f"- title: {created.get('summary', '')}\n"
                f"- time: {start_text} -> {end_text}\n"
                f"- id: {created.get('id', '')}\n"
                f"- link: {created.get('htmlLink', '')}"
            )
        except TimeoutError as e:
            return f"Timeout Error: {e}"
        except Exception as e:
            return (
                f"Error: {e}\n"
                "If this is an authorization/scope issue, run calendar(action=\"auth\") to refresh token scopes."
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

        if creds and creds.valid and self._has_required_scopes(creds):
            return creds

        if creds and creds.expired and creds.refresh_token and self._has_required_scopes(creds):
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
            raise RuntimeError(
                "Not authorized yet or token scope outdated. "
                "Run calendar(action=\"auth\") to grant calendar write access."
            )

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

    def _has_required_scopes(self, creds: Any) -> bool:
        try:
            return creds.has_scopes(self.SCOPES)
        except Exception:
            return True

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

    def _create_event(
        self,
        event_payload: dict[str, Any],
        timeout: int = 60,
        retries: int = 3,
    ) -> dict[str, Any]:
        try:
            import requests
            from google.auth.transport.requests import Request
        except ImportError as e:
            raise RuntimeError(
                "Missing dependencies. Install with: "
                "pip install google-auth google-auth-oauthlib requests"
            ) from e

        creds = self._get_calendar_credentials(allow_browser_auth=False)

        def create_event_call(request_timeout: int) -> dict[str, Any]:
            if not creds.valid and creds.refresh_token:
                creds.refresh(Request())

            headers = {
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=headers,
                json=event_payload,
                timeout=request_timeout,
            )

            if response.status_code == 401 and creds.refresh_token:
                creds.refresh(Request())
                headers["Authorization"] = f"Bearer {creds.token}"
                response = requests.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers=headers,
                    json=event_payload,
                    timeout=request_timeout,
                )

            response.raise_for_status()
            return response.json()

        return self._execute_with_retries(create_event_call, timeout=timeout, retries=retries)

    def _resolve_create_payload(
        self,
        title: str | None,
        start: str | None,
        end: str | None,
        location: str | None,
        description: str | None,
        text: str | None,
    ) -> dict[str, Any]:
        resolved_title = (title or "").strip()
        resolved_start = (start or "").strip()
        resolved_end = (end or "").strip()

        if not (resolved_start and resolved_end):
            if not text:
                raise RuntimeError(
                    "For action=create, provide either start+end ISO datetimes or text like '17:30-19:00跑步'."
                )
            parsed_title, parsed_start, parsed_end = self._parse_create_text(text)
            resolved_title = resolved_title or parsed_title
            resolved_start = resolved_start or parsed_start
            resolved_end = resolved_end or parsed_end

        if not resolved_title:
            raise RuntimeError("Missing title for action=create.")

        start_dt = self._parse_iso_datetime_with_timezone(resolved_start, field_name="start")
        end_dt = self._parse_iso_datetime_with_timezone(resolved_end, field_name="end")

        if end_dt <= start_dt:
            raise RuntimeError("Invalid time range: end must be later than start.")

        payload: dict[str, Any] = {
            "summary": resolved_title,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
        if location:
            payload["location"] = location
        if description:
            payload["description"] = description
        return payload

    def _parse_iso_datetime_with_timezone(self, value: str, field_name: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise RuntimeError(
                f"Invalid {field_name}: timezone is required in ISO datetime, got '{value}'."
            )
        return parsed

    def _parse_create_text(self, text: str) -> tuple[str, str, str]:
        match = self.TIME_RANGE_PATTERN.search(text)
        if not match:
            raise RuntimeError(
                "Could not parse time range from text. Use format like '17:30-19:00跑步'."
            )

        start_hm = match.group("start")
        end_hm = match.group("end")

        tail = text[match.end():].strip()
        title = self._normalize_title_text(tail)
        if not title:
            title = "Untitled Event"

        start_dt, end_dt = self._resolve_local_datetimes(start_hm, end_hm)
        return title, start_dt.isoformat(), end_dt.isoformat()

    def _normalize_title_text(self, title: str) -> str:
        normalized = title.strip()
        normalized = normalized.lstrip("，,。.!?？：:;； ")
        for suffix in ("的事项", "事项", "事件", "日程", "安排"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()
                break
        return normalized

    def _resolve_local_datetimes(self, start_hm: str, end_hm: str) -> tuple[datetime, datetime]:
        now_local = datetime.now().astimezone()
        local_tz = now_local.tzinfo
        if local_tz is None:
            raise RuntimeError("Cannot detect local timezone for create action.")

        start_hour, start_minute = [int(part) for part in start_hm.split(":", 1)]
        end_hour, end_minute = [int(part) for part in end_hm.split(":", 1)]

        start_dt = now_local.replace(
            hour=start_hour,
            minute=start_minute,
            second=0,
            microsecond=0,
        )
        if start_dt <= now_local:
            start_dt = start_dt + timedelta(days=1)

        end_dt = start_dt.replace(hour=end_hour, minute=end_minute)
        if end_dt <= start_dt:
            end_dt = end_dt + timedelta(days=1)

        # Keep explicit local tz offset in generated ISO.
        start_dt = start_dt.astimezone(local_tz)
        end_dt = end_dt.astimezone(local_tz)
        return start_dt, end_dt

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
