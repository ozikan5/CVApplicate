from __future__ import annotations

from datetime import datetime, timezone


def normalize_greenhouse(company_name: str, slug: str, raw: dict) -> list[dict]:
    postings = []
    for job in raw.get("jobs", []):
        if "id" not in job or "title" not in job or "absolute_url" not in job:
            continue
        postings.append(
            {
                "id": f"{slug}-{job['id']}",
                "company": company_name,
                "title": job["title"],
                "url": job["absolute_url"],
                "location": job.get("location", {}).get("name", "Unknown"),
                "posted_date": job.get("updated_at", "")[:10],
            }
        )
    return postings


def normalize_lever(company_name: str, slug: str, raw: list) -> list[dict]:
    postings = []
    for job in raw:
        if "id" not in job or "text" not in job or "hostedUrl" not in job:
            continue
        created_at = job.get("createdAt")
        if created_at is not None:
            posted_date = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            posted_date = ""
        postings.append(
            {
                "id": f"{slug}-{job['id']}",
                "company": company_name,
                "title": job["text"],
                "url": job["hostedUrl"],
                "location": job.get("categories", {}).get("location", "Unknown"),
                "posted_date": posted_date,
            }
        )
    return postings
