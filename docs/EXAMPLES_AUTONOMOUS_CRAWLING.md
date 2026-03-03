# Example: Autonomous Crawling Policy in Action

Ví dụ này minh họa cách WSDeepAgent **tự động áp dụng** crawling policy mà không cần config riêng cho từng domain.

---

## Scenario 1: So sánh giá sản phẩm

**User query (Telegram):**
```
/ask So sánh giá 5 xe đạp địa hình trên shopxenhat.com và tiki.vn
```

### Bot tự động thực hiện:

#### 1. Planning Phase
```python
# Bot tạo research plan:
sub_questions = [
    "Tìm top 5 xe đạp địa hình phổ biến trên shopxenhat.com với giá",
    "Tìm top 5 xe đạp địa hình tương đương trên tiki.vn với giá",
    "So sánh giá và đưa khuyến nghị"
]
```

#### 2. Research Phase - shopxenhat.com

Bot nhận được sub-question và **tự động đọc crawling policy từ prompt**:

```python
# Agent thấy trong system prompt:
"""
⚠️ WEB CRAWLING POLICY:
• fetch_url tự động check robots.txt
• Nếu cần crawl 3+ URLs từ CÙNG domain:
  - THÊM time.sleep(1.0) giữa mỗi lần
  - Giới hạn ≤10 URLs
"""

# Agent quyết định crawl chiến lược:
# 1. Tìm product listing page trước
search_result = tavily_search("xe đạp địa hình site:shopxenhat.com")

# 2. Lấy listing page
listing_url = "https://shopxenhat.com/category/xe-dap-dia-hinh"
listing_html = fetch_url(listing_url)  # robots.txt được check tự động

# 3. Parse để lấy 5 product URLs
product_urls = extract_product_urls(listing_html)[:5]

# 4. Crawl từng product với rate limiting (BOT TỰ ĐỘNG THÊM)
products = []
for i, url in enumerate(product_urls):
    print(f"Fetching {i+1}/5: {url}")  # Bot tự log tiến trình
    
    html = fetch_url(url)  # robots.txt checked mỗi lần
    
    if "Error: robots.txt disallow" in html:
        print(f"Skipped {url}: blocked by robots.txt")
        continue
    
    product_data = extract_product_data(html)
    products.append(product_data)
    
    if i < len(product_urls) - 1:
        time.sleep(1.0)  # BOT TỰ ĐỘNG THÊM rate limiting
```

**Output trong Telegram:**
```
🔍 Đang nghiên cứu shopxenhat.com...
Fetching 1/5: https://shopxenhat.com/products/xe-dap-giant-atx-1
Fetching 2/5: https://shopxenhat.com/products/xe-dap-trek-marlin-7
Fetching 3/5: https://shopxenhat.com/products/xe-dap-merida-big-nine
...
✅ Crawl hoàn tất: 5/5 URLs thành công
```

#### 3. Research Phase - tiki.vn

Bot lặp lại process tương tự cho tiki.vn:

```python
# Tự động crawl tiki.vn với cùng policy
# - Check robots.txt của tiki.vn (domain khác)
# - Rate limit 1s giữa mỗi request
# - Log tiến trình
```

#### 4. Synthesis Phase

```markdown
## So sánh giá xe đạp địa hình

### shopxenhat.com
1. Giant ATX 1: 8.500.000đ
2. Trek Marlin 7: 12.900.000đ
...

### tiki.vn
1. Giant ATX 1: 8.700.000đ (cao hơn 200k)
2. Trek Marlin 7: 12.500.000đ (rẻ hơn 400k)
...

### Khuyến nghị
- Mua Giant ATX 1 trên shopxenhat.com (rẻ hơn)
- Mua Trek Marlin 7 trên tiki.vn (rẻ hơn)

---
**Lưu ý:** Crawl tuân thủ robots.txt của cả 2 site. 
Đã crawl 10 URLs tổng cộng với rate limiting 1s/request.
```

---

## Scenario 2: Domain bị chặn bởi robots.txt

**User query:**
```
/ask Tóm tắt 10 bài viết mới nhất từ privateblog.com
```

### Bot tự động xử lý:

```python
# 1. Bot tìm 10 article URLs
article_urls = search_for_articles("privateblog.com", limit=10)

# 2. Thử fetch URL đầu tiên
result = fetch_url(article_urls[0])

# 3. fetch_url tự động check robots.txt và trả về:
# "Error: robots.txt disallows crawling of https://privateblog.com/articles/..."

# 4. Bot KHÔNG retry, KHÔNG bypass, mà report cho user:
return """
❌ Không thể crawl privateblog.com

Lý do: Site này có robots.txt chặn bot crawling.

Giải pháp:
1. Truy cập thủ công các URL
2. Liên hệ site owner xin phép
3. Hoặc tìm nguồn thay thế

(Tôi được cấu hình để tôn trọng robots.txt - đạo đức crawling)
"""
```

**User thấy trong Telegram:**
```
❌ Không thể crawl privateblog.com

Lý do: Site này có robots.txt chặn bot crawling.
...
```

---

## Scenario 3: Scale lớn (>10 URLs)

**User query:**
```
/ask Phân tích giá cả 50 sản phẩm laptop trên sendo.vn
```

### Bot tự động hỏi user:

```python
# Bot detect scale lớn (>10 URLs)
if len(product_urls) > 10:
    # Tự động hỏi user (trong Telegram)
    return """
    🔍 Tôi tìm thấy 50 product URLs trên sendo.vn
    
    ⚠️ Crawl 50 URLs sẽ mất ~50 giây (rate limiting)
    
    Bạn muốn:
    A) Crawl tất cả 50 URLs (~1 phút)
    B) Lấy mẫu 10 URLs đại diện (nhanh, ~10 giây)
    C) Hướng dẫn setup production crawl (docs/ZYTE_CRAWLING_GUIDE.md)
    
    Trả lời: A, B, hoặc C
    """

# User chọn B → Bot crawl 10 URLs với policy
# User chọn A → Bot crawl 50 với policy (nhưng cảnh báo thời gian)
# User chọn C → Bot gửi link tới ZYTE_CRAWLING_GUIDE.md
```

---

## Scenario 4: Multi-domain research

**User query:**
```
/ask So sánh giá iPhone 15 trên: shopee.vn, lazada.vn, tiki.vn
```

### Bot crawl chiến lược:

```python
# Bot tạo plan:
sub_questions = [
    "Tìm giá iPhone 15 trên shopee.vn",  # Sub-Q 1
    "Tìm giá iPhone 15 trên lazada.vn",  # Sub-Q 2
    "Tìm giá iPhone 15 trên tiki.vn",    # Sub-Q 3
]

# Mỗi sub-question xử lý 1 domain riêng
# → Rate limiting áp dụng PER domain
# → Có thể chạy song song (nếu dùng parallel tools)

# Kết quả: Mỗi domain bị rate limit riêng
# shopee: 1s giữa mỗi shopee URL
# lazada: 1s giữa mỗi lazada URL (không ảnh hưởng shopee)
# tiki: 1s giữa mỗi tiki URL
```

**Insight:** Bot hiểu rate limiting là **per-domain**, không phải global.

---

## Key Takeaways

### ✅ Bot TỰ ĐỘNG làm gì:

1. **Check robots.txt** cho MỌI domain (không cần config)
2. **Rate limiting 1s** khi crawl nhiều URLs từ cùng domain
3. **Giới hạn 10 URLs** mặc định (hỏi user nếu cần nhiều hơn)
4. **Log tiến trình** rõ ràng: `Fetching 3/10: url...`
5. **Báo lỗi rõ** khi bị robots.txt chặn (không bypass)
6. **Tổng hợp kết quả** chỉ từ URLs thành công
7. **Nêu limitations** trong final report

### 🚫 Bot KHÔNG BAO GIỜ làm:

1. ❌ Bypass robots.txt
2. ❌ Spam requests (no rate limiting)
3. ❌ Crawl >10 URLs mà không hỏi user
4. ❌ Retry URL đã bị robots.txt chặn
5. ❌ Ẩn giấu crawl failures
6. ❌ Fabricate data cho URLs failed

### 🔧 User KHÔNG CẦN làm gì:

- ✅ Không cần config riêng cho shopxenhat.com, tiki.vn, lazada.vn...
- ✅ Không cần set rate limit thủ công
- ✅ Không cần check robots.txt bằng tay
- ✅ Chỉ cần hỏi câu hỏi → bot tự áp dụng policy

---

## Testing

Để test policy tự động, chạy:

```bash
# Test 1: Single URL (no rate limiting needed)
python src/main.py --query "Giá iPhone 15 trên tiki.vn"

# Test 2: Multi-URL từ cùng domain (auto rate limit)
python src/main.py --query "So sánh 5 laptop Dell trên sendo.vn"

# Test 3: Multi-domain
python src/main.py --query "Giá iPhone 15 trên shopee, lazada, tiki"

# Test 4: robots.txt block (cần site có Disallow)
python src/main.py --query "Crawl https://site-with-robots-block.example"
```

**Expected behavior:**
- Test 1: Instant (1 URL)
- Test 2: ~5 seconds (5 URLs × 1s rate limit)
- Test 3: ~3 seconds (1 URL per domain, parallel)
- Test 4: Error message về robots.txt, không retry

---

## Configuration Override

Nếu user muốn **TẮT** policy (không khuyến cáo):

```bash
# .env
WEB_FETCH_RESPECT_ROBOTS_TXT=false  # Tắt robots.txt check
# Lưu ý: Rate limiting vẫn được khuyến cáo giữ nguyên
```

Nếu muốn tăng limit (rủi ro bị block):

```bash
# Hiện tại bot hard-code 10 URLs limit
# Để thay đổi: sửa trong deep_agent.py prompt
# Hoặc dùng production workflow: docs/ZYTE_CRAWLING_GUIDE.md
```

---

**Kết luận:** Bot giờ đã **tự trị hoàn toàn** trong việc crawl đạo đức. 
User chỉ cần hỏi, bot tự quyết định domain và áp dụng policy phù hợp.
