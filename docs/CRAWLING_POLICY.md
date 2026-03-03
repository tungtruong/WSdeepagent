# Web Crawling Policy for WSDeepAgent

**Version:** 1.0  
**Effective:** 2026-03-03  
**Purpose:** Guide autonomous agent to crawl websites ethically and effectively

---

## Core Principles

**ALWAYS** follow this order when crawling ANY domain:

```
1. Check robots.txt → 2. Respect rate limits → 3. Use appropriate method → 4. Log everything
```

---

## Pre-Crawl Checklist (MANDATORY)

Before fetching ANY URL from a domain, verify:

### ✅ Step 1: robots.txt Compliance

```python
# The fetch_url tool AUTOMATICALLY checks robots.txt if WEB_FETCH_RESPECT_ROBOTS_TXT=true
# You don't need to do anything - just call fetch_url(url)
# If robots.txt disallows, you'll get an error message
```

**What to do if blocked:**
- ❌ DON'T crawl if robots.txt says `Disallow: /`
- ⚠️ ASK user if you encounter `Disallow: /products/` but need product data
- ✅ PROCEED if allowed, respecting Crawl-delay if specified

### ✅ Step 2: Rate Limiting

**Rule:** Wait ≥1 second between requests to the SAME domain

```python
# When you need to fetch multiple URLs from same domain:
import time

urls = ["https://example.com/page1", "https://example.com/page2", ...]
results = []

for url in urls:
    result = fetch_url(url)
    results.append(result)
    time.sleep(1.0)  # MANDATORY 1-second delay
```

**Never:**
- Fetch >10 URLs per minute from same domain
- Make parallel requests to same domain
- Ignore Crawl-delay in robots.txt

### ✅ Step 3: Method Selection

The `fetch_url` tool automatically chooses the best method:

1. **Zyte API** (if `ZYTE_API_KEY` set) → Best for production, has proxies
2. **requests** → Fast for static HTML
3. **Playwright** → For JavaScript-heavy sites

**You don't control this** - just call `fetch_url(url)` and it handles fallback.

### ✅ Step 4: Error Handling

**If fetch_url fails:**

```python
result = fetch_url("https://example.com/page")

if "Error:" in result or "robots.txt disallow" in result.lower():
    # DON'T retry the same URL immediately
    # DON'T try to bypass the block
    # DO inform the user about the limitation
    return "Cannot access this URL due to: " + result
```

**Common errors:**
- `"Error: robots.txt disallows"` → Respect it, don't retry
- `"Error: Timeout"` → OK to retry ONCE after 2 seconds
- `"Error: 403 Forbidden"` → Site is blocking, inform user

---

## Multi-URL Crawling Workflow

When research requires crawling **3+ URLs from same domain:**

### Phase 1: Planning (Before any fetch)

```
1. Identify the domain (e.g., "shopxenhat.com")
2. Count how many URLs you need (e.g., 5 product pages)
3. Estimate time: num_urls × 1 second = minimum duration
4. INFORM user: "I will crawl 5 URLs from shopxenhat.com (~5 seconds with rate limiting)"
```

### Phase 2: Systematic Crawling

```python
# Example: Research 5 bike products on shopxenhat.com

urls = [
    "https://shopxenhat.com/products/xe-dap-dia-hinh-1",
    "https://shopxenhat.com/products/xe-dap-dia-hinh-2",
    "https://shopxenhat.com/products/xe-dap-dia-hinh-3",
    "https://shopxenhat.com/products/xe-dap-dia-hinh-4",
    "https://shopxenhat.com/products/xe-dap-leo-nui",
]

crawl_results = []
for i, url in enumerate(urls):
    print(f"Fetching {i+1}/{len(urls)}: {url}")
    
    result = fetch_url(url)
    
    if "Error:" in result:
        crawl_results.append({"url": url, "status": "failed", "error": result})
        # Continue to next URL (don't abort entire research)
    else:
        crawl_results.append({"url": url, "status": "success", "content": result[:500]})
    
    # MANDATORY: Rate limiting
    if i < len(urls) - 1:  # Don't sleep after last URL
        time.sleep(1.0)

# Synthesize findings from successful crawls
successful = [r for r in crawl_results if r['status'] == 'success']
print(f"Successfully crawled {len(successful)}/{len(urls)} URLs")
```

### Phase 3: Synthesis

```
- Use data from SUCCESSFUL crawls only
- Report failed URLs to user with reason
- Don't fabricate data for failed URLs
```

---

## Domain-Specific Adaptations

### E-commerce Sites (shopxenhat.com, lazada.vn, etc.)

**Common needs:**
- Product pages: `/products/`, `/product/`, `/item/`
- Category listings: `/category/`, `/c/`
- Search results: `/search?q=`

**Strategy:**
```
1. Start with category/search page (1 URL) → extract product links
2. Crawl top 5-10 product pages (with rate limiting)
3. Extract: name, price, description, specs, images
```

### News Sites (vnexpress.net, tuoitre.vn, etc.)

**Common needs:**
- Article pages: `/news/`, `/article/`, `/tin-tuc/`

**Strategy:**
```
1. Check robots.txt for news crawl policy
2. Fetch article URL
3. Extract: headline, author, publish_date, body_text
```

### Documentation Sites (docs.python.org, etc.)

**Usually allowed:**
- Most tech docs allow crawling
- Rate limit: 1 req/second is safe
- No need for Playwright (static HTML)

---

## Respect Patterns

### ✅ GOOD Examples

```python
# Good: Rate-limited crawl with error handling
urls = get_product_urls(search_page)[:10]  # Limit to 10 max
for url in urls:
    result = fetch_url(url)
    time.sleep(1.0)
    if "Error:" not in result:
        extract_product_data(result)
```

```python
# Good: Inform user about limitations
if "robots.txt disallow" in result:
    return "This site's robots.txt prevents crawling product pages. I can only provide general information about the site."
```

### ❌ BAD Examples

```python
# BAD: No rate limiting
for url in urls:
    fetch_url(url)  # Hammering the server!
```

```python
# BAD: Ignoring robots.txt
if "robots.txt disallow" in result:
    # Try to fetch it with requests directly (bypass check)
    result = requests.get(url)  # DON'T DO THIS
```

```python
# BAD: Fetching too many URLs without user awareness
urls = get_all_product_urls()  # Could be 1000+ URLs
for url in urls:
    fetch_url(url)  # User doesn't know you're crawling 1000 pages
```

---

## Scale Guidelines

| Number of URLs | Action Required |
|----------------|-----------------|
| 1-2 | Just fetch, no special handling needed |
| 3-10 | Rate limit 1s, inform user of duration |
| 11-50 | ASK user for permission first: "I found 30 URLs. Crawl all (~30s) or sample 10?" |
| 51+ | DON'T crawl automatically. Tell user: "This requires systematic crawling (see docs/ZYTE_CRAWLING_GUIDE.md)" |

---

## Integration with Research Workflow

### During _plan() phase:

```python
# When creating sub_questions, consider:
if "research multiple products" in query or "compare websites" in query:
    # Plan to crawl 5-10 URLs max per sub_question
    # Each sub_question should handle 1 domain
    sub_questions = [
        "Find top 5 products on shopxenhat.com and extract specs",
        "Find top 5 products on lazada.vn for comparison",
        # Split domains into separate sub_questions for clear rate limiting
    ]
```

### During _research_sub_question() phase:

```python
# If you discover you need to crawl multiple URLs:
1. Count them
2. Check scale guidelines above
3. Proceed if ≤10, ask if 11-50, abort if 51+
4. Always use time.sleep(1.0) between fetches from same domain
```

---

## Logging Best Practices

**For transparency, always log:**

```python
# At start of multi-URL crawl:
print(f"Starting crawl of {len(urls)} URLs from {domain}")
print(f"Estimated duration: {len(urls)} seconds (with rate limiting)")

# For each URL:
print(f"[{i+1}/{total}] Fetching: {url}")

# At end:
print(f"Crawl complete: {success_count} succeeded, {fail_count} failed")
```

**Why this matters:**
- User sees progress (especially in Telegram with `TELEGRAM_PROGRESS_REPORTING=true`)
- User understands why research takes time
- Transparency builds trust

---

## Emergency Override (User Request)

**If user explicitly says:**
- "Ignore robots.txt" → Inform them: "I'm configured to respect robots.txt. Set `WEB_FETCH_RESPECT_ROBOTS_TXT=false` in .env to override."
- "Crawl faster" → Explain: "Rate limiting protects both the site and prevents blocking. Minimum 1s interval recommended."
- "Crawl 100+ URLs" → Point them to `docs/ZYTE_CRAWLING_GUIDE.md` for production workflow

---

## Summary Checklist

Before **ANY** multi-URL crawl, verify:

- [ ] robots.txt check enabled (`WEB_FETCH_RESPECT_ROBOTS_TXT=true`)
- [ ] Rate limiting code in place (`time.sleep(1.0)`)
- [ ] URL count ≤ 10 (or user permission if more)
- [ ] Error handling for each fetch
- [ ] Progress logging for user visibility
- [ ] Synthesis plan for successful results only

**Remember:** The goal is ethical, effective research - not maximum data extraction.

---

**Last Updated:** 2026-03-03  
**See Also:** [ZYTE_CRAWLING_GUIDE.md](ZYTE_CRAWLING_GUIDE.md) for production-scale crawling (50+ URLs)
