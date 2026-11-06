"""Book research module using Google Books API and Open Library.

Finds real books with proper citations. Does NOT scrape content (copyright).
Books are recommended as references only.
"""

import logging

import httpx

from backend.config import settings
from backend.schemas import Source, SourceType

logger = logging.getLogger(__name__)


async def search_books(queries: list[str], max_results: int = 3) -> list[Source]:
    """Search for books using Google Books API.

    Args:
        queries: Book-related search queries.
        max_results: Maximum total books to return.

    Returns:
        List of Source objects (type=book) with metadata only (no scraped content).
    """
    all_books = []
    seen_titles = set()

    for query in queries:
        try:
            params = {
                "q": query,
                "maxResults": 5,
                "printType": "books",
                "orderBy": "relevance",
            }
            if settings.google_books_api_key:
                params["key"] = settings.google_books_api_key

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            for item in data.get("items", []):
                vol = item.get("volumeInfo", {})
                title = vol.get("title", "")

                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                authors = vol.get("authors", [])

                # Extract ISBN
                isbn_list = vol.get("industryIdentifiers", [])
                isbn = ""
                for ident in isbn_list:
                    if ident.get("type") == "ISBN_13":
                        isbn = ident.get("identifier", "")
                        break
                    elif ident.get("type") == "ISBN_10":
                        isbn = ident.get("identifier", "")

                book = Source(
                    id=f"B{len(all_books)+1}",
                    type=SourceType.BOOK,
                    title=title,
                    author=", ".join(authors) if authors else "Unknown",
                    year=vol.get("publishedDate", "")[:4],
                    isbn=isbn,
                    url=vol.get("infoLink", vol.get("previewLink", "")),
                    snippet=vol.get("description", "")[:500],
                    extracted_text="",  # Intentionally empty — copyright
                    reliability_score=0.85,
                    reliability_reason="Published book — cited as reference only, content not scraped (copyright)",
                )
                all_books.append(book)

                if len(all_books) >= max_results:
                    break

            logger.info(f"Book search '{query}': found {len(data.get('items', []))} results")

        except Exception as e:
            logger.error(f"Book search failed for '{query}': {e}")
            continue

        if len(all_books) >= max_results:
            break

    logger.info(f"Total books found: {len(all_books)}")
    return all_books[:max_results]


async def search_open_library(queries: list[str], max_results: int = 2) -> list[Source]:
    """Fallback book search using Open Library API (no API key needed).

    Used when Google Books API is unavailable or returns too few results.
    """
    all_books = []
    seen_titles = set()

    for query in queries:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": 5},
                )
                response.raise_for_status()
                data = response.json()

            for doc in data.get("docs", []):
                title = doc.get("title", "")
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                authors = doc.get("author_name", [])
                isbn_list = doc.get("isbn", [])
                year = str(doc.get("first_publish_year", ""))
                key = doc.get("key", "")

                book = Source(
                    id=f"B{len(all_books)+1}",
                    type=SourceType.BOOK,
                    title=title,
                    author=", ".join(authors[:3]) if authors else "Unknown",
                    year=year,
                    isbn=isbn_list[0] if isbn_list else "",
                    url=f"https://openlibrary.org{key}" if key else "",
                    snippet="",
                    extracted_text="",
                    reliability_score=0.85,
                    reliability_reason="Published book — reference only",
                )
                all_books.append(book)

                if len(all_books) >= max_results:
                    break

        except Exception as e:
            logger.error(f"Open Library search failed for '{query}': {e}")
            continue

        if len(all_books) >= max_results:
            break

    logger.info(f"Open Library books found: {len(all_books)}")
    return all_books[:max_results]
