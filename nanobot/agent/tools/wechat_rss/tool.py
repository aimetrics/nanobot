"""WeChat RSS tool for nanobot agent framework."""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import (
    BooleanSchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)

# feeds.json 存储在 workspace/wechat_rss/feeds.json
# 格式: [{"name": "公众号名称", "fakeid": "optional_cached_fakeid"}, ...]
_FEEDS_FILENAME = "feeds.json"


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(
            "Action to perform",
            enum=[
                "login", "search", "fetch", "fetch_all",
                "generate_feed", "subscribe", "unsubscribe", "list_feeds",
            ],
        ),
        keyword=StringSchema("公众号名称关键词（search/fetch/subscribe 时使用）"),
        fakeid=StringSchema("公众号 fakeid（fetch 时直接使用，跳过搜索）"),
        count=IntegerSchema(
            60, description="每个公众号获取的文章数量（与 since 互斥，二选一）", minimum=1, maximum=100
        ),
        since=StringSchema(
            "时间过滤，支持两种格式: "
            "1) 相对时间如 '7d'(7天), '24h'(24小时), '3d12h'; "
            "2) ISO 日期如 '2026-04-01'. "
            "设置后忽略 count，自动获取该时间之后的所有文章"
        ),
        with_content=BooleanSchema(
            description="是否获取文章正文内容（fetch 时使用）", default=False
        ),
        timeout=IntegerSchema(
            180, description="登录二维码超时时间（秒，仅 login 时使用）", minimum=30, maximum=600
        ),
        required=["action"],
    )
)
class WeChatRSSTool(Tool):
    """WeChat official account RSS tool for searching, fetching articles, and generating feeds."""

    def __init__(
        self,
        token_file: str = "wx_token.json",
        workspace: Path | None = None,
    ):
        self._token_file = token_file
        self._workspace = workspace
        self._data_dir = (workspace / "wechat_rss") if workspace else Path("wechat_rss")
        self._mp = None  # lazy init to avoid import errors when playwright is not installed

    def _ensure_mp(self):
        """Lazily initialize WeChatMP instance."""
        if self._mp is None:
            from . import WeChatMP
            self._mp = WeChatMP(token_file=self._token_file)
        return self._mp

    @property
    def _feeds_path(self) -> Path:
        return self._data_dir / _FEEDS_FILENAME

    def _load_feeds(self) -> list[dict[str, str]]:
        """Load feeds list from JSON file."""
        if not self._feeds_path.exists():
            return []
        try:
            with open(self._feeds_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save_feeds(self, feeds: list[dict[str, str]]) -> None:
        """Save feeds list to JSON file."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._feeds_path, "w", encoding="utf-8") as f:
            json.dump(feeds, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_since(since: str) -> int:
        """Parse since string to unix timestamp (seconds).

        Supports:
          - Relative: '7d', '24h', '3d12h', '1d6h'
          - ISO date: '2026-04-01', '2026-04-01T09:00:00'
        """
        import re
        from datetime import datetime, timezone

        s = since.strip()

        # Relative: e.g. '7d', '24h', '3d12h'
        rel_match = re.fullmatch(r'(?:(\d+)d)?(?:(\d+)h)?', s)
        if rel_match and (rel_match.group(1) or rel_match.group(2)):
            days = int(rel_match.group(1) or 0)
            hours = int(rel_match.group(2) or 0)
            delta_seconds = days * 86400 + hours * 3600
            return int(time.time()) - delta_seconds

        # ISO date/datetime
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp())
            except ValueError:
                continue

        raise ValueError(f"无法解析时间: '{since}'。支持格式: '7d', '24h', '3d12h', '2026-04-01'")

    @property
    def name(self) -> str:
        return "wechat_rss"

    @property
    def max_result_chars(self) -> int | None:
        return 64000  # articles with links need more room than the default 16k

    @property
    def description(self) -> str:
        return (
            "WeChat Official Account (微信公众号) article fetcher. "
            "Use this tool to fetch/read articles from WeChat public accounts. "
            "When a user asks to get, read, or fetch WeChat articles, ALWAYS use this tool instead of web_search or exec.\n"
            "IMPORTANT: When user mentions a time range (最近一周/最近3天/本周 etc.), "
            "ALWAYS use the 'since' parameter (e.g. since='7d') instead of count. "
            "Use fetch_all + since for fetching all subscribed accounts at once.\n"
            "OUTPUT FORMAT: The tool returns markdown with clickable [title](url) links. "
            "When presenting results to the user, preserve the markdown link format as-is. "
            "Do NOT reformat into tables (tables break clickable links in chat apps).\n"
            "Actions:\n"
            "- login: 扫码登录微信公众平台\n"
            "- search: 按名称搜索公众号，需要 keyword\n"
            "- subscribe / unsubscribe: 管理订阅列表，需要 keyword\n"
            "- list_feeds: 查看当前订阅列表\n"
            "- fetch: 抓取单个公众号文章 (keyword or fakeid, + since='7d' for time filter)\n"
            "- fetch_all: 抓取所有已订阅公众号文章 (+ since='7d' for time filter)\n"
            "- generate_feed: 抓取并生成 JSON Feed\n"
            f"订阅列表: {self._feeds_path} | 输出目录: {self._data_dir}"
        )

    async def execute(
        self,
        action: str,
        keyword: str = "",
        fakeid: str = "",
        count: int = 60,
        since: str = "",
        with_content: bool = False,
        timeout: int = 180,
        **kwargs: Any,
    ) -> str:
        try:
            if action == "login":
                return await self._login(timeout)
            elif action == "search":
                return await self._search(keyword, count)
            elif action == "subscribe":
                return self._subscribe(keyword, fakeid)
            elif action == "unsubscribe":
                return self._unsubscribe(keyword)
            elif action == "list_feeds":
                return self._list_feeds()
            elif action == "fetch":
                return await self._fetch(keyword, fakeid, count, since, with_content)
            elif action == "fetch_all":
                return await self._fetch_all(count, since, with_content)
            elif action == "generate_feed":
                return await self._generate_feed(keyword, fakeid, count, since, with_content)
            else:
                return f"Error: unknown action '{action}'"
        except Exception as e:
            return f"Error: {e}"

    # --- login ---

    async def _login(self, timeout: int) -> str:
        mp = self._ensure_mp()
        result = await asyncio.to_thread(mp.login, timeout)
        if result.get("is_logged_in"):
            return "登录成功。可以使用 search/fetch/fetch_all/subscribe 等功能了。"
        return "Error: 登录失败"

    # --- feeds management ---

    def _subscribe(self, keyword: str, fakeid: str) -> str:
        if not keyword:
            return "Error: keyword is required for subscribe"
        feeds = self._load_feeds()
        for f in feeds:
            if f["name"] == keyword:
                return f"'{keyword}' 已在订阅列表中。"
        entry: dict[str, str] = {"name": keyword}
        if fakeid:
            entry["fakeid"] = fakeid
        feeds.append(entry)
        self._save_feeds(feeds)
        return f"已订阅 '{keyword}'。当前共 {len(feeds)} 个订阅。"

    def _unsubscribe(self, keyword: str) -> str:
        if not keyword:
            return "Error: keyword is required for unsubscribe"
        feeds = self._load_feeds()
        new_feeds = [f for f in feeds if f["name"] != keyword]
        if len(new_feeds) == len(feeds):
            return f"'{keyword}' 不在订阅列表中。"
        self._save_feeds(new_feeds)
        return f"已取消订阅 '{keyword}'。当前共 {len(new_feeds)} 个订阅。"

    def _list_feeds(self) -> str:
        feeds = self._load_feeds()
        if not feeds:
            return "订阅列表为空。使用 subscribe action 添加公众号。"
        lines = [f"当前订阅 {len(feeds)} 个公众号:"]
        for f in feeds:
            fid = f.get("fakeid", "未缓存")
            lines.append(f"  - {f['name']} (fakeid: {fid})")
        return "\n".join(lines)

    # --- search ---

    async def _search(self, keyword: str, count: int) -> str:
        if not keyword:
            return "Error: keyword is required for search"
        mp = self._ensure_mp()
        results = await asyncio.to_thread(mp.search_feed, keyword, count)
        return json.dumps(results, ensure_ascii=False, indent=2)

    # --- fetch ---

    async def _fetch_articles(self, mp, fid: str, count: int, since: str, with_content: bool) -> list:
        """Fetch articles by count or since timestamp."""
        if since:
            ts = self._parse_since(since)
            return await asyncio.to_thread(mp.fetch_articles_since, fid, ts, with_content)
        return await asyncio.to_thread(mp.fetch_articles, fid, count, with_content)

    @staticmethod
    def _format_articles(articles: list, feed_name: str = "") -> str:
        """Format articles as markdown with clickable title links."""
        from datetime import datetime, timezone, timedelta

        if not articles:
            prefix = f"**{feed_name}**: " if feed_name else ""
            return f"{prefix}暂无文章"

        tz_cn = timezone(timedelta(hours=8))
        lines: list[str] = []
        if feed_name:
            lines.append(f"**{feed_name}** ({len(articles)} 篇):\n")
        for a in articles:
            ts = a.get("publish_time", 0)
            date_str = datetime.fromtimestamp(ts, tz=tz_cn).strftime("%m-%d") if ts else "未知"
            title = a.get("title", "无标题")
            url = a.get("url", "")
            if url:
                lines.append(f"- {date_str} [{title}]({url})")
            else:
                lines.append(f"- {date_str} {title}")
        return "\n".join(lines)

    def _lookup_fakeid(self, keyword: str) -> str:
        """Look up fakeid from feeds.json by name, avoiding an API search call."""
        if not keyword:
            return ""
        for f in self._load_feeds():
            if f.get("name") == keyword and f.get("fakeid"):
                return f["fakeid"]
        return ""

    async def _fetch(self, keyword: str, fakeid: str, count: int, since: str, with_content: bool) -> str:
        mp = self._ensure_mp()
        fid = fakeid or self._lookup_fakeid(keyword) or await self._resolve_fakeid(mp, keyword)
        if not fid:
            return f"Error: 未找到公众号 '{keyword}'"
        articles = await self._fetch_articles(mp, fid, count, since, with_content)
        return self._format_articles(articles, keyword or fid)

    async def _fetch_all(self, count: int, since: str, with_content: bool) -> str:
        feeds = self._load_feeds()
        if not feeds:
            return "Error: 订阅列表为空。请先使用 subscribe action 添加公众号。"
        mp = self._ensure_mp()
        parts: list[str] = []
        feeds_updated = False
        for entry in feeds:
            feed_name = entry["name"]
            try:
                fid = entry.get("fakeid") or await self._resolve_fakeid(mp, feed_name)
                if not fid:
                    parts.append(f"**{feed_name}**: 未找到公众号")
                    continue
                if "fakeid" not in entry:
                    entry["fakeid"] = fid
                    feeds_updated = True
                articles = await self._fetch_articles(mp, fid, count, since, with_content)
                parts.append(self._format_articles(articles, feed_name))
            except Exception as e:
                parts.append(f"**{feed_name}**: Error: {e}")
        if feeds_updated:
            self._save_feeds(feeds)
        return "\n\n".join(parts)

    # --- generate feed ---

    async def _generate_feed(self, keyword: str, fakeid: str, count: int, since: str, with_content: bool) -> str:
        mp = self._ensure_mp()
        fid = fakeid or self._lookup_fakeid(keyword) or await self._resolve_fakeid(mp, keyword)
        if not fid:
            return f"Error: 未找到公众号 '{keyword}'"
        articles = await self._fetch_articles(mp, fid, count, since, with_content)
        feed_json = await asyncio.to_thread(
            mp.generate_json_feed,
            keyword or fid,
            articles,
            full_text=with_content,
            feed_id=fid,
        )
        return feed_json

    # --- helpers ---

    async def _resolve_fakeid(self, mp, keyword: str) -> str:
        if not keyword:
            return ""
        return await asyncio.to_thread(mp.get_feed_fakeid, keyword)
