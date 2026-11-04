# OPML Feed Import & Content Pool Optimization Design

## Background

Jasmine's onboarding content pool currently suffers from quality issues:
- Some feeds have no content or only short summaries with external links.
- Some feeds deliver poorly formatted content (excessive HTML/advertising).
- The `starterPackFeedsZh` list mixes English sources for Chinese users.
- New users subscribing via starter pack see an empty feed list because pre-populated feeds aren't validated for quality.

## Goal

Build a Python CLI tool that imports curated RSS feeds from publicly shared OPML files, validates them against strict quality rules, and updates both the frontend `recommendedFeeds.js` and the backend `feed_validation` table.

## Scope

This design covers:
1. The CLI tool (`scripts/import_opml_feeds.py`).
2. Reuse of existing `RSSFetcher` and `html_sanitizer`.
3. Integration with the `feed_validation` table and `frontend/src/config/recommendedFeeds.js`.
4. A `--dry-run` mode for safe preview before writing changes.

Out of scope:
- Automatic registration/subscription on third-party platforms (Readwise, Inoreader, Matter, etc.).
- UI changes to the onboarding flow beyond using the updated data sources.

## Input Sources

| Source | URL | Category Mapping |
|---|---|---|
| `kilimchoi/engineering-blogs` | `https://raw.githubusercontent.com/kilimchoi/engineering-blogs/master/engineering_blogs.opml` | `tech`, `dev`, `ai` (English) |
| `timqian/chinese-independent-blogs` | `https://raw.githubusercontent.com/timqian/chinese-independent-blogs/master/feed.opml` | `chinese`, `dev` (Chinese) |

## Validation Rules

For every feed extracted from OPML, the script fetches the **latest 5 articles** and applies the following filters.

### Rule 1: Recency
- The feed must have at least **1 article published within the last 30 days**.
- If the feed has fewer than 5 total articles, all available articles are checked.

### Rule 2: Content Availability
- At least **3 of the 5 sampled articles** must contain a non-empty `content` body.
- Articles whose body is only a summary or a single external link are considered "unavailable".

### Rule 3: Minimum Content Length
- The **average plain-text length** of the 5 sampled articles must be **>= 200 characters**.
- Plain text is computed after HTML sanitization.

### Rule 4: HTML/Format Cleanliness Score
- After sanitization, the **plain-text ratio** must be **>= 60%** (`len(plain_text) / len(raw_html_or_content) >= 0.6`).
- The content must not match common ad-heavy patterns (e.g., excessive `<script>`, repeated tracking pixels, known ad-network classes).

### Rule 5: Language Consistency
- The **dominant language** of the feed (detected from the 5 articles' combined plain text) must match the target classification:
  - English OPML feeds -> `en`
  - Chinese OPML feeds -> `zh`
- Language detection uses `langdetect` (new lightweight dependency).

## Categorization Mapping

### From English OPML (`engineering-blogs`)
| OPML Group / Heuristic | Target Category |
|---|---|
| Companies + Products/Technologies | `tech` |
| Individuals (programming, web, software) | `dev` |
| Individuals (AI/ML-specific keywords in title: OpenAI, Hugging Face, ML, AI) | `ai` |
| Top 8 highest-quality feeds across all English categories (sorted by `avg_content_length DESC` among passing feeds) | `popular` (starter pack) |

### From Chinese OPML (`chinese-independent-blogs`)
| OPML Tag / Heuristic | Target Category |
|---|---|
| Tags: 编程, 前端, 开源, 算法 | `chinese` -> sub-group dev/tech |
| Tags: 机器学习, AI | `ai` |
| Tags: 生活, 随笔, 摄影, 投资, 物理, 文学 | `chinese` -> sub-group lifestyle/culture |
| Top 8 highest-quality feeds across all Chinese categories | `popular` (starter pack for `zh`) |

*Note:* The existing `news`, `business`, `science`, `longform`, `lifestyle`, `security` categories in `recommendedFeeds.js` are preserved but **not automatically populated** by this script unless a matching OPML source is added later.

## CLI Design

```bash
# Preview mode (default): fetch, validate, and print a report without modifying files/DB
python scripts/import_opml_feeds.py --dry-run

# Write mode: after validation, generate recommendedFeeds.js and update DB
python scripts/import_opml_feeds.py --write

# Optional: point to local OPML files instead of fetching from GitHub
python scripts/import_opml_feeds.py --en-opml ./data/en.opml --zh-opml ./data/zh.opml --dry-run
```

## Output Artifacts

### 1. Console / Report
A Markdown report printed to stdout (and optionally saved to `logs/opml_import_YYYY-MM-DD_HHMMSS.md`) containing:
- Total feeds parsed from each OPML.
- Number of feeds passing each validation rule.
- Final counts per target category.
- Rejected feeds with reasons (rule failure breakdown).

### 2. Frontend File
`frontend/src/config/recommendedFeeds.js` is regenerated with:
- Updated `starterPackFeedsEn` and `starterPackFeedsZh` (top 8 validated feeds each).
- Updated `recommendedFeeds` array with validated feeds mapped to their categories.
- Existing manual categories (`news`, `business`, etc.) preserved but marked with a comment so future script runs do not overwrite them.

### 3. Backend Database
For every validated feed, an `UPSERT` into `feed_validation` is performed via `DatabaseManager` initialized with `core.config.settings` (same configuration used by the API):
```sql
INSERT INTO feed_validation (feed_url, feed_name, language, is_valid, article_count, avg_content_length, last_article_at, last_validated_at, validation_metadata)
VALUES (...)
ON CONFLICT (feed_url) DO UPDATE SET ...
```

## Component Architecture

```
scripts/import_opml_feeds.py
├── OPMLParser
│   ├── fetch_opml(url) -> xml string
│   └── parse_opml(xml) -> List[FeedCandidate]
├── FeedValidator
│   ├── __init__(rss_fetcher, html_sanitizer)
│   ├── validate(feed_candidate) -> ValidationResult
│   └── _detect_language(plain_texts) -> str
├── Categorizer
│   └── assign_category(feed_candidate, source_type) -> str
├── ReportGenerator
│   └── generate_report(results) -> markdown string
├── FrontendWriter
│   └── write_recommended_feeds(validated_feeds, output_path)
└── BackendWriter
    └── upsert_feed_validation(db_manager, validated_feeds)
```

## Dependencies

- `langdetect>=0.2` — language detection for Rule 5.
  - Must be added to both `requirements.test.txt` and `deploy/docker/requirements.prod.txt`.

## Error Handling

- **Network failure fetching OPML**: Log warning, skip that source, continue with the other.
- **Network failure fetching a single feed**: Mark feed as failed, include in report.
- **Language detection failure**: Fallback to `unknown`; if `unknown` conflicts with target language, reject the feed.
- **Database connection failure in `--write` mode**: Abort before writing `recommendedFeeds.js`, print clear error.

## Testing Strategy

1. **Manual validation**: Run `--dry-run` and manually inspect the report for top 10 feeds.
2. **Local DB test**: Run `--write` against a local test DB (`docker-compose.test.yml`) and verify `feed_validation` rows.
3. **Frontend check**: Verify generated `recommendedFeeds.js` loads correctly in the dev server and that `FeedDiscoverView` renders without errors.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| OPML sources change structure or go offline | Script gracefully skips missing sources; report clearly indicates missing data. |
| `langdetect` is slow on large batches | Run language detection after content-length filtering to reduce input size; batch only validated feeds. |
| Overwriting `recommendedFeeds.js` destroys manual curation | Use template generation with preserved sections (comment markers) so manual categories are kept intact. |
| Concurrent RSS fetching triggers rate limits | Reuse `RSSFetcher` which already implements `PerHostRateLimiter`. |
