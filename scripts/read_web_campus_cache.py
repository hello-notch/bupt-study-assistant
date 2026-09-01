from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[2] not in {"portal", "activity"}:
        raise SystemExit("usage: read_web_campus_cache.py DATABASE SOURCE")
    database_path = Path(sys.argv[1]).resolve()
    source = sys.argv[2]
    if not database_path.is_file():
        print("[]")
        return

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT item_id,title,published_at,department,summary,url,metadata,first_seen_at
            FROM source_items WHERE source=?
            ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT 80
            """,
            (source,),
        ).fetchall()

    items: list[dict[str, object]] = []
    for row in rows:
        title = str(row["title"] or "").strip()
        if not title or "\ufffd" in title:
            continue
        try:
            metadata = json.loads(row["metadata"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        published_at = row["published_at"] or row["first_seen_at"]
        if source == "portal":
            items.append(
                {
                    "id": row["item_id"],
                    "url": row["url"],
                    "kind": "notice",
                    "category": "信息门户",
                    "title": title,
                    "summary": row["summary"] or "",
                    "source": row["department"] or "信息门户",
                    "publishedAt": published_at,
                    "subscribed": False,
                    "read": False,
                }
            )
        else:
            items.append(
                {
                    "id": row["item_id"],
                    "url": row["url"] or "https://dekt.bupt.edu.cn/",
                    "kind": "activity",
                    "category": metadata.get("category") or "第二课堂",
                    "title": title,
                    "summary": row["summary"] or "",
                    "source": row["department"] or "第二课堂",
                    "publishedAt": published_at,
                    "eventTime": row["published_at"],
                    "campus": metadata.get("campus") or metadata.get("location"),
                    "subscribed": False,
                    "read": False,
                }
            )
    # Keep stdout ASCII-only so Node decodes it consistently on Windows code pages.
    print(json.dumps(items, ensure_ascii=True))


if __name__ == "__main__":
    main()
