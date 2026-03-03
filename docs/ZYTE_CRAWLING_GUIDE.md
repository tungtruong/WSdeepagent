# Zyte API Crawling Guide - Executive Summary

**Document Version:** 1.0  
**Last Updated:** 2026-03-03  
**Target System:** WSDeepAgent with Zyte API Integration

---

## Mục Đích

Hướng dẫn này cung cấp quy trình đầy đủ, có thể thực thi để crawl một domain bất kỳ bằng Zyte API với:
- ✅ Tuân thủ robots.txt, sitemap, Terms of Service
- ✅ Rate limiting, retry logic, rendering fallback
- ✅ Logging chi tiết, artifacts có thể kiểm chứng
- ✅ Metrics đánh giá chất lượng crawl

**Domain mẫu:** `shopxenhat.com` (có thể thay thế bằng domain khác)

---

## 📋 Bước 1: Pre-Crawl Compliance Check

### 1.1. Fetch & Snapshot Compliance Artifacts

Trước khi crawl, bắt buộc phải snapshot 3 tài liệu:

```bash
#!/bin/bash
DOMAIN="shopxenhat.com"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
OUTPUT_DIR="compliance_snapshots/${DOMAIN}_${TIMESTAMP}"
mkdir -p "$OUTPUT_DIR"

# 1. robots.txt
curl -A "WSDeepAgent/1.0 (Research Bot; +https://github.com/tungtruong/WSdeepagent)" \
  -o "$OUTPUT_DIR/robots.txt" \
  --max-time 10 \
  "https://${DOMAIN}/robots.txt" || echo "No robots.txt found"

# 2. sitemap.xml (thử các variants phổ biến)
for sitemap in sitemap.xml sitemap_index.xml sitemap1.xml; do
  curl -A "WSDeepAgent/1.0" \
    -o "$OUTPUT_DIR/${sitemap}" \
    --max-time 10 \
    "https://${DOMAIN}/${sitemap}" 2>/dev/null && break
done

# 3. Terms of Service (các URL phổ biến)
for tos_path in terms terms-of-service tos dieu-khoan-su-dung; do
  curl -A "WSDeepAgent/1.0" \
    -o "$OUTPUT_DIR/tos_candidate_${tos_path}.html" \
    --max-time 10 \
    "https://${DOMAIN}/${tos_path}" 2>/dev/null
done

# 4. Compute SHA256 hashes + manifest
cd "$OUTPUT_DIR"
sha256sum * > MANIFEST.txt
echo "timestamp_utc: ${TIMESTAMP}" >> MANIFEST.txt
echo "domain: ${DOMAIN}" >> MANIFEST.txt
cd -

echo "✅ Compliance artifacts saved to: $OUTPUT_DIR"
```

### 1.2. Decision Rule: Allow/Partial/Forbidden

**Rule Logic:**

```python
def evaluate_crawl_permission(domain, robots_txt, tos_html):
    """
    Returns: ("allow"|"partial"|"forbidden", reason: str)
    """
    # Rule 1: robots.txt chặn toàn bộ
    if robots_txt and "Disallow: /" in robots_txt:
        return ("forbidden", "robots.txt disallows all crawling")
    
    # Rule 2: ToS explicitly forbids scraping
    tos_keywords = ["no scraping", "prohibit crawling", "automated access prohibited"]
    if tos_html and any(kw in tos_html.lower() for kw in tos_keywords):
        return ("forbidden", "ToS explicitly prohibits scraping")
    
    # Rule 3: Partial allow nếu có Crawl-delay hoặc rate limit trong robots.txt
    if robots_txt and "Crawl-delay:" in robots_txt:
        delay = extract_crawl_delay(robots_txt)
        return ("partial", f"Allowed with crawl-delay: {delay}s")
    
    # Rule 4: Default allow (nhưng apply rate limit conservative)
    return ("allow", "No explicit restrictions found")
```

**Output Example:**
```json
{
  "domain": "shopxenhat.com",
  "decision": "partial",
  "reason": "Allowed with crawl-delay: 2s",
  "snapshots": {
    "robots_sha256": "a3f2...",
    "tos_sha256": "b7e1...",
    "timestamp": "20260303_123045"
  }
}
```

---

## 🚀 Bước 2: Zyte API Job Configuration

### 2.1. Sample Zyte Request (Single URL)

**cURL Example:**

```bash
curl -u YOUR_ZYTE_API_KEY: \
  -X POST https://api.zyte.com/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://shopxenhat.com/products/xe-dap-dia-hinh",
    "browserHtml": true,
    "httpResponseBody": false,
    "httpResponseHeaders": true,
    "screenshot": false,
    "actions": [
      {
        "action": "waitForTimeout",
        "timeout": 3000
      }
    ],
    "geolocation": "VN"
  }'
```

**Python Example:**

```python
import requests
import json
from requests.auth import HTTPBasicAuth

ZYTE_API_KEY = "YOUR_API_KEY_HERE"
ZYTE_ENDPOINT = "https://api.zyte.com/v1/extract"

def fetch_with_zyte(url, timeout=30):
    payload = {
        "url": url,
        "browserHtml": true,
        "httpResponseHeaders": true,
        "geolocation": "VN",
        "actions": [
            {"action": "waitForTimeout", "timeout": 3000}
        ]
    }
    
    response = requests.post(
        ZYTE_ENDPOINT,
        auth=HTTPBasicAuth(ZYTE_API_KEY, ''),
        json=payload,
        timeout=timeout
    )
    
    response.raise_for_status()
    return response.json()

# Usage
result = fetch_with_zyte("https://shopxenhat.com/products/example")
html = result.get("browserHtml", "")
headers = result.get("httpResponseHeaders", [])
```

### 2.2. Batch Crawl Job (100 URLs)

```python
import time
from urllib.robotparser import RobotFileParser

class ZyteCrawler:
    def __init__(self, api_key, rate_limit_ms=1000):
        self.api_key = api_key
        self.rate_limit = rate_limit_ms / 1000.0  # Convert to seconds
        self.last_request_time = 0
        
    def respect_rate_limit(self):
        """Ensure minimum interval between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()
    
    def crawl_batch(self, urls, output_file="crawl_results.jsonl"):
        """
        Crawl a batch of URLs with rate limiting, retry, and logging
        """
        results = []
        
        for idx, url in enumerate(urls):
            print(f"[{idx+1}/{len(urls)}] Crawling: {url}")
            
            # Rate limiting
            self.respect_rate_limit()
            
            # Fetch with retry
            for attempt in range(3):
                try:
                    result = fetch_with_zyte(url)
                    
                    # Log success
                    log_entry = {
                        "url": url,
                        "status": "success",
                        "timestamp": time.time(),
                        "attempt": attempt + 1,
                        "html_size": len(result.get("browserHtml", ""))
                    }
                    results.append(log_entry)
                    
                    # Save raw HTML (first 10 only)
                    if idx < 10:
                        with open(f"raw_html/{idx:03d}.html", "w") as f:
                            f.write(result.get("browserHtml", ""))
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        log_entry = {
                            "url": url,
                            "status": "failed",
                            "timestamp": time.time(),
                            "attempt": attempt + 1,
                            "error": str(e)
                        }
                        results.append(log_entry)
                    else:
                        time.sleep(2 ** attempt)  # Exponential backoff
        
        # Save results to JSONL
        with open(output_file, "w") as f:
            for entry in results:
                f.write(json.dumps(entry) + "\n")
        
        return results
```

---

## 📊 Bước 3: Multi-Phase Crawl Workflow

### Phase A: Discovery (Sitemap Parsing)

```python
import xml.etree.ElementTree as ET
import requests

def discover_urls_from_sitemap(domain):
    """
    Parse sitemap.xml and return list of product URLs
    """
    sitemap_url = f"https://{domain}/sitemap.xml"
    resp = requests.get(sitemap_url, timeout=10)
    
    root = ET.fromstring(resp.content)
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    urls = []
    for url_elem in root.findall('.//ns:url/ns:loc', namespace):
        url = url_elem.text
        # Filter for product pages (adjust pattern per site)
        if '/products/' in url or '/product/' in url:
            urls.append(url)
    
    return urls

# Example usage
product_urls = discover_urls_from_sitemap("shopxenhat.com")
print(f"Discovered {len(product_urls)} product URLs")
```

### Phase B: Sample Extraction (First 10)

```python
# Test crawl on 10 URLs to validate extraction logic
sample_urls = product_urls[:10]
crawler = ZyteCrawler(api_key=ZYTE_API_KEY, rate_limit_ms=1000)
sample_results = crawler.crawl_batch(sample_urls, "sample_crawl.jsonl")

# Validate extraction
success_rate = sum(1 for r in sample_results if r['status'] == 'success') / len(sample_results)
print(f"Sample success rate: {success_rate * 100:.1f}%")

if success_rate < 0.8:
    print("❌ Sample crawl failed threshold (80%). Aborting full crawl.")
    exit(1)
```

### Phase C: Full Extraction (Up to 100)

```python
# Full crawl (limited to 100 URLs for cost control)
full_urls = product_urls[:100]
full_results = crawler.crawl_batch(full_urls, "full_crawl.jsonl")
```

---

## 📝 Bước 4: Logging & Artifact Schemas

### 4.1. Manifest Schema

**File:** `crawl_manifest.json`

```json
{
  "domain": "shopxenhat.com",
  "crawl_id": "shopxenhat_20260303_123045",
  "compliance": {
    "robots_sha256": "a3f2e8...",
    "tos_sha256": "b7e1c4...",
    "decision": "partial",
    "crawl_delay_s": 2
  },
  "config": {
    "zyte_api_version": "v1/extract",
    "rate_limit_ms": 1000,
    "max_urls": 100,
    "rendering": "browser",
    "geolocation": "VN"
  },
  "execution": {
    "start_time": "2026-03-03T12:30:45Z",
    "end_time": "2026-03-03T12:45:12Z",
    "total_urls": 100,
    "successful": 97,
    "failed": 3,
    "duration_s": 867
  },
  "artifacts": {
    "extracted_data": "full_crawl.jsonl",
    "raw_html_samples": "raw_html/*.html (10 files)",
    "per_url_logs": "per_url_logs.jsonl"
  }
}
```

### 4.2. Per-URL Log Schema

**File:** `per_url_logs.jsonl`

```json
{"url": "https://shopxenhat.com/products/xe-1", "status": "success", "timestamp": 1709471445.23, "attempt": 1, "html_size": 45231, "response_time_ms": 1234}
{"url": "https://shopxenhat.com/products/xe-2", "status": "success", "timestamp": 1709471446.89, "attempt": 1, "html_size": 42891, "response_time_ms": 1187}
{"url": "https://shopxenhat.com/products/xe-3", "status": "failed", "timestamp": 1709471448.12, "attempt": 3, "error": "Timeout after 30s"}
```

---

## ✅ Bước 5: Validation & Success Metrics

### 5.1. Metrics to Collect

```python
def compute_crawl_metrics(results):
    total = len(results)
    successful = sum(1 for r in results if r['status'] == 'success')
    failed = sum(1 for r in results if r['status'] == 'failed')
    
    avg_response_time = sum(r.get('response_time_ms', 0) for r in results if r['status'] == 'success') / successful
    avg_html_size = sum(r.get('html_size', 0) for r in results if r['status'] == 'success') / successful
    
    return {
        "total_urls": total,
        "successful": successful,
        "failed": failed,
        "success_rate": successful / total,
        "avg_response_time_ms": avg_response_time,
        "avg_html_size_bytes": avg_html_size
    }

metrics = compute_crawl_metrics(full_results)
print(json.dumps(metrics, indent=2))
```

### 5.2. Success Thresholds

| Metric | Threshold | Action if Failed |
|--------|-----------|------------------|
| Success Rate | ≥ 90% | Review failed URLs, adjust retry logic |
| Avg Response Time | ≤ 2000ms | Check network/Zyte API performance |
| Avg HTML Size | ≥ 5000 bytes | Verify pages are fully rendered (not blanks) |
| Rate Compliance | 100% | Audit rate limiting code |

**Validation Script:**

```python
def validate_crawl(metrics, thresholds):
    issues = []
    
    if metrics['success_rate'] < thresholds['min_success_rate']:
        issues.append(f"Success rate {metrics['success_rate']:.1%} < {thresholds['min_success_rate']:.1%}")
    
    if metrics['avg_response_time_ms'] > thresholds['max_response_time_ms']:
        issues.append(f"Avg response time {metrics['avg_response_time_ms']:.0f}ms > {thresholds['max_response_time_ms']}ms")
    
    if metrics['avg_html_size_bytes'] < thresholds['min_html_size']:
        issues.append(f"Avg HTML size {metrics['avg_html_size_bytes']:.0f} bytes < {thresholds['min_html_size']} bytes")
    
    if issues:
        print("❌ Crawl validation FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("✅ Crawl validation PASSED")
        return True

thresholds = {
    "min_success_rate": 0.90,
    "max_response_time_ms": 2000,
    "min_html_size": 5000
}

validate_crawl(metrics, thresholds)
```

---

## 🚨 Bước 6: Limitations & Caveats

### 6.1. Data Validation Required

**CHƯA KIỂM CHỨNG (cần manual review):**

1. **robots.txt Content:**
   - Sitemap location có đúng không?
   - Crawl-delay có áp dụng cho user-agent của bạn?
   - Disallow rules có ngoại lệ nào không?

2. **ToS Content:**
   - URL của ToS có chính xác không? (có thể là `/privacy-policy`, không phải `/tos`)
   - Keyword detection có đủ chính xác?
   - Ngôn ngữ tiếng Việt: "cấm thu thập dữ liệu", "không được sử dụng robot"?

3. **DOM Structure:**
   - CSS selectors để extract product name, price, description cần phải test thủ công trên raw HTML
   - JSON-LD structured data: có tồn tại không? Format như thế nào?

4. **Zyte Account Limits:**
   - Monthly request quota: cần check dashboard
   - Concurrent requests: default là bao nhiêu?
   - Geolocation VN có available không?

### 6.2. Version & Endpoint Differences

| Aspect | Current Config | Alternatives |
|--------|----------------|--------------|
| Zyte Endpoint | `v1/extract` | Có `v1/batch` cho bulk crawl |
| Rendering | `browserHtml: true` | `httpResponseBody: true` nếu không cần JS |
| Auth Method | Basic Auth (API key as username) | Header-based auth (check docs) |
| Screenshot | `false` (save cost) | `true` nếu cần kiểm chứng visual |

### 6.3. Cost Estimation

**Zyte API Pricing (ước lượng):**
- Browser rendering: ~$0.01-0.03 per request
- 100 URLs = ~$1-3
- 1000 URLs = ~$10-30

**Recommendation:** Test với 10 URLs trước, kiểm tra bill trên Zyte dashboard.

---

## 📦 Bước 7: Deliverables Checklist

Sau khi chạy crawl, cần có các artifacts sau:

- [ ] `compliance_snapshots/DOMAIN_TIMESTAMP/` folder with:
  - [ ] `robots.txt` (SHA256 hash in MANIFEST.txt)
  - [ ] `sitemap.xml` (or variants)
  - [ ] `tos_*.html` (ToS page snapshots)
  - [ ] `MANIFEST.txt` (hashes + timestamp)

- [ ] `crawl_manifest.json` (see schema above)

- [ ] `full_crawl.jsonl` (per-URL logs with status/timing/size)

- [ ] `raw_html/` folder with:
  - [ ] `000.html` to `009.html` (10 sample raw HTML files)

- [ ] Validation report (metrics + threshold check results)

---

## 🔧 Configuration Template (Copy-Paste Ready)

**File:** `zyte_crawl_config.json`

```json
{
  "domain": "shopxenhat.com",
  "zyte_api_key": "YOUR_ZYTE_API_KEY",
  "config": {
    "rate_limit_ms": 1000,
    "max_urls": 100,
    "max_retries": 3,
    "retry_backoff_base": 2,
    "timeout_s": 30,
    "geolocation": "VN",
    "rendering": "browser",
    "wait_for_timeout_ms": 3000
  },
  "thresholds": {
    "min_success_rate": 0.90,
    "max_response_time_ms": 2000,
    "min_html_size_bytes": 5000
  },
  "output": {
    "compliance_dir": "compliance_snapshots",
    "manifest_file": "crawl_manifest.json",
    "crawl_log_file": "full_crawl.jsonl",
    "raw_html_dir": "raw_html",
    "max_raw_html_samples": 10
  }
}
```

---

## ⚡ Quick Start (One Command)

```bash
# Set environment variables
export ZYTE_API_KEY="your_api_key_here"
export TARGET_DOMAIN="shopxenhat.com"

# Run full crawl pipeline
python3 -c "
import sys
sys.path.insert(0, 'src')
from zyte_crawler import ZyteCrawlPipeline

pipeline = ZyteCrawlPipeline(
    domain='$TARGET_DOMAIN',
    api_key='$ZYTE_API_KEY',
    max_urls=100
)

pipeline.run_full_pipeline()
"
```

*(Note: `zyte_crawler.py` module cần được tạo dựa trên code snippets ở trên)*

---

## 📞 Next Steps

**Trước khi chạy production crawl:**

1. **Xác nhận domain:** Bạn muốn crawl `shopxenhat.com` hay domain khác?
2. **Review ToS manually:** Đọc Terms of Service của domain đó để đảm bảo không vi phạm
3. **Test với 10 URLs:** Chạy phase B (sample extraction) trước
4. **Check Zyte quota:** Verify API key có đủ quota cho 100 requests

**Khi có xác nhận domain, tôi sẽ:**
- Fine-tune CSS selectors cho domain cụ thể
- Cung cấp extraction logic (product name, price, specs)
- Tạo module `zyte_crawler.py` hoàn chỉnh

---

**Document End** | Version 1.0 | 2026-03-03
