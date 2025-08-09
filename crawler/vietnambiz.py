import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv
import os
import time
import csv

# --- Cấu hình ---
# Tải các biến môi trường từ file .env
load_dotenv()

# Lấy API key và cấu hình cho Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Chưa cung cấp GEMINI_API_KEY")
    exit()

genai.configure(api_key=GEMINI_API_KEY)

# Chọn model phù hợp. 'gemini-1.5-flash-latest' nhanh và hiệu quả cho việc tóm tắt.
model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")

# --- Các hàm xử lý ---

def crawl_vietnambiz_page(page_url):
    """
    Thu thập dữ liệu các bài viết từ một trang của Vietnambiz.
    """
    print(f"🕷️  Đang thu thập dữ liệu từ: {page_url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        r = requests.get(page_url, headers=headers, timeout=15)
        r.raise_for_status()  # Báo lỗi nếu status code không phải 2xx
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi truy cập {page_url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    items = soup.select("h3.title a")
    
    leads = []
    for a in items:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        # Đảm bảo URL là hoàn chỉnh
        url = href if href.startswith("http") else "https://vietnambiz.vn" + href
        if title and url:
            leads.append({"title": title, "url": url})
            
    return leads

def extract_article_content(article_url):
    """
    Trích xuất nội dung chính của một bài viết.
    """
    print(f"📄 Trích xuất nội dung từ: {article_url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(article_url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Selector này cần được kiểm tra để đảm bảo lấy đúng nội dung
        content_body = soup.select_one("div.vnbcbc-body.vceditor-content")
        if not content_body:
            return ""
        
        paragraphs = content_body.find_all("p")
        # Nối các đoạn văn bản, loại bỏ các dòng trống
        full_text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        return full_text
    except requests.exceptions.RequestException as e:
        print(f"Lỗi lấy nội dung từ {article_url}: {e}")
        return ""

def summarize_content_with_retry(text):
    """
    Tóm tắt nội dung bằng Gemini, có cơ chế thử lại khi gặp lỗi giới hạn.
    """
    if not text or len(text.split()) < 50: # Kiểm tra số từ thay vì ký tự
        return "Nội dung không đủ dài để tóm tắt."

    # Số lần thử lại tối đa
    max_retries = 3
    # Thời gian chờ ban đầu (giây)
    initial_delay = 60

    for attempt in range(max_retries):
        try:
            prompt = f"Bạn là một chuyên gia phân tích kinh doanh. Hãy đọc và tóm tắt nội dung sau bằng tiếng Việt một cách súc tích trong khoảng 3-4 câu, tập trung vào những thông tin quan trọng nhất:\n\n---\n\n{text}"
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            # Kiểm tra xem có phải lỗi giới hạn truy cập (429) không
            if "429" in str(e) or "ResourceExhausted" in str(e):
                print(f"❗️ Lỗi giới hạn truy cập (429). Đang chờ {initial_delay} giây để thử lại... (Lần {attempt + 1}/{max_retries})")
                time.sleep(initial_delay)
                # Tăng thời gian chờ cho lần thử lại tiếp theo
                initial_delay *= 2
            else:
                print(f"❌ Lỗi không xác định khi gọi Gemini: {e}")
                # Không thử lại với các lỗi khác
                return "Lỗi tóm tắt do một vấn đề không xác định."
    
    print("❌ Không thể tóm tắt sau nhiều lần thử. Vui lòng thử lại sau.")
    return "Lỗi tóm tắt do hết giới hạn truy cập."