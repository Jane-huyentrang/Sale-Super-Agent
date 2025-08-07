import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv
import os
import time
import csv
import json
from datetime import datetime
import re

# --- 🔐 CẤU HÌNH ---
# Tải các biến môi trường từ file .env
load_dotenv()

# Lấy API keys từ biến môi trường
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Kiểm tra API keys ngay từ đầu
if not all([GOOGLE_API_KEY, SEARCH_ENGINE_ID, GEMINI_API_KEY]):
    print("[ERROR] Lỗi nghiêm trọng: Không tìm thấy đủ API Keys.")
    print("        Vui lòng kiểm tra lại file .env của bạn phải có đủ:")
    print("        - GOOGLE_API_KEY")
    print("        - SEARCH_ENGINE_ID")
    print("        - GEMINI_API_KEY")
    exit()

# Cấu hình Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")
    print("[OK] Cấu hình và kết nối tới Gemini thành công.")
except Exception as e:
    print(f"[ERROR] Lỗi cấu hình Gemini API: {e}")
    print("        Vui lòng kiểm tra lại GEMINI_API_KEY.")
    exit()


# --- 🌐 CÁC HÀM HỖ TRỢ ---

def search_google_for_urls(query, num_results=5):
    """
    Sử dụng Google Custom Search API để tìm kiếm và trả về danh sách các URL.
    """
    print(f"  [SEARCH] Tìm kiếm Google với truy vấn: '{query}'")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": GOOGLE_API_KEY,
        "cx": SEARCH_ENGINE_ID,
        "num": num_results,
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        results = res.json().get("items", [])
        return [item["link"] for item in results]
    except requests.exceptions.RequestException as e:
        print(f"  [WARN] Lỗi khi gọi Google Search API: {e}")
        return []

def scrape_website_content(url):
    """
    Tải và trích xuất nội dung văn bản từ một URL.
    """
    print(f"  [SCRAPE] Đang quét nội dung từ: {url}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
            script_or_style.decompose()
            
        text = soup.get_text(separator="\n", strip=True)
        return text
    except Exception as e:
        print(f"  [WARN] Không thể quét nội dung từ {url}: {e}")
        return ""

def _call_gemini_with_retry(prompt):
    """
    Hàm nội bộ để gọi Gemini, có cơ chế tự động thử lại khi gặp lỗi giới hạn.
    """
    max_retries = 3
    delay_seconds = 60 # Thời gian chờ ban đầu là 60 giây

    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(prompt)
            # Dọn dẹp phản hồi để đảm bảo nó là JSON hợp lệ
            cleaned_response = response.text.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            
            return json.loads(cleaned_response)
        except Exception as e:
            if "429" in str(e): # Lỗi giới hạn truy cập
                print(f"  [WARN] Lỗi giới hạn truy cập (429). Đang chờ {delay_seconds} giây để thử lại... (Lần {attempt + 1}/{max_retries})")
                time.sleep(delay_seconds)
                delay_seconds *= 2 
            elif isinstance(e, json.JSONDecodeError):
                print("  [WARN] Gemini trả về không phải định dạng JSON hợp lệ.")
                return {"error": "Lỗi phân tích JSON từ Gemini.", "raw_response": response.text if 'response' in locals() else 'Không có phản hồi'}
            else:
                print(f"  [WARN] Lỗi không xác định khi gọi Gemini API: {e}")
                return {"error": f"Lỗi Gemini không xác định: {e}"}

    print("  [ERROR] Vẫn gặp lỗi giới hạn sau nhiều lần thử. Vui lòng thử lại sau.")
    return {"error": "Hết giới hạn truy cập API sau nhiều lần thử."}


def analyze_scraped_content_with_gemini(company_name, context):
    """
    Phân tích nội dung đã quét từ web.
    """
    print("  [ANALYZE 1/2] Đưa dữ liệu web-scrape cho Gemini phân tích...")
    if not context.strip():
        return {"error": "Không có nội dung web-scrape để phân tích."}

    prompt = f"""
    Bạn là một trợ lý phân tích kinh doanh. Dựa vào khối văn bản được cung cấp dưới đây về công ty '{company_name}', hãy trích xuất thông tin và tóm tắt theo định dạng JSON sau.
    Hãy dọn dẹp và loại bỏ các giá trị trùng lặp.
    
    Cấu trúc JSON:
    {{
        "ten_giam_doc": ["Tên 1", "Tên 2"],
        "dia_chi": ["Địa chỉ 1", "Địa chỉ 2"],
        "mo_hinh_kd": ["Ngành nghề kinh doanh hoặc sản phẩm/dịch vụ cụ thể 1", "Dịch vụ 2"],
        "email": ["email1@example.com"],
        "ten_mien": ["domain1.com"],
        "tom_tat": "Bản tóm tắt chi tiết về công ty dựa trên nội dung được cung cấp..."
    }}

    --- NỘI DUNG VĂN BẢN (từ web scrape) ---
    {context}
    --- KẾT THÚC NỘI DUNG ---
    """
    return _call_gemini_with_retry(prompt)

# <<< MỚI: Hàm để lấy thông tin trực tiếp từ kiến thức của Gemini >>>
def get_info_directly_from_gemini(company_name):
    """
    Hỏi trực tiếp Gemini về thông tin của công ty.
    """
    print(f"  [ANALYZE 2/2] Hỏi trực tiếp Gemini về '{company_name}'...")

    prompt = f"""
    Bạn là một chuyên gia thu thập thông tin doanh nghiệp. Dựa trên kiến thức của bạn, hãy cung cấp thông tin về công ty có tên là '{company_name}'.
    Hãy trả lời bằng một đối tượng JSON duy nhất theo cấu trúc sau.
    
    Cấu trúc JSON:
    {{
        "ten_giam_doc": ["Tên giám đốc hoặc người đại diện"],
        "dia_chi": ["Địa chỉ trụ sở chính hoặc các chi nhánh nổi bật"],
        "mo_hinh_kd": ["Các ngành nghề kinh doanh, sản phẩm, dịch vụ chính"],
        "email": ["Email liên hệ chính"],
        "ten_mien": ["Tên miền website chính thức"],
        "tom_tat": "Một bản tóm tắt tổng quan về công ty, lịch sử, quy mô và lĩnh vực hoạt động."
    }}
    """
    return _call_gemini_with_retry(prompt)

# <<< MỚI: Hàm để tổng hợp dữ liệu từ hai nguồn >>>
def merge_data(scraped_data, direct_data):
    """
    Trộn dữ liệu từ kết quả web-scrape và kết quả hỏi trực tiếp Gemini.
    """
    print("  [MERGE] Đang tổng hợp dữ liệu từ 2 nguồn...")
    if "error" in scraped_data: scraped_data = {}
    if "error" in direct_data: direct_data = {}

    merged = {}
    
    # Các trường dạng danh sách (list)
    list_keys = ["ten_giam_doc", "dia_chi", "mo_hinh_kd", "email", "ten_mien"]
    for key in list_keys:
        # Sử dụng set để tự động loại bỏ trùng lặp
        combined_set = set(scraped_data.get(key, []))
        combined_set.update(direct_data.get(key, []))
        # Chuyển lại thành list, loại bỏ các giá trị rỗng nếu có
        merged[key] = sorted([item for item in list(combined_set) if item])

    # Xử lý phần tóm tắt
    summary_scraped = scraped_data.get("tom_tat", "").strip()
    summary_direct = direct_data.get("tom_tat", "").strip()
    
    final_summary = ""
    if summary_scraped:
        final_summary += f"--- TÓM TẮT TỪ PHÂN TÍCH WEB ---\n{summary_scraped}\n\n"
    if summary_direct:
        final_summary += f"--- TÓM TẮT TỪ KIẾN THỨC GEMINI ---\n{summary_direct}"
        
    merged["tom_tat"] = final_summary.strip() or "Không tạo được tóm tắt."

    return merged


def save_data_to_csv(company_name, data_row):
    """
    Lưu một dòng dữ liệu vào file CSV riêng biệt cho công ty.
    """
    safe_filename = re.sub(r'[\\/*?:"<>|]', "", company_name)
    safe_filename = safe_filename.replace(' ', '_')
    output_filename = f"{safe_filename}.csv"

    print(f"  [SAVE] Đang lưu dữ liệu vào file: {output_filename}")
    try:
        with open(output_filename, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Tên công ty", "Tóm tắt tổng hợp", "Tên Giám đốc", "Địa chỉ/Chi nhánh",
                "Mô hình KD", "Email", "Tên miền", "Thời gian quét"
            ])
            writer.writerow(data_row)
        print(f"[OK] Đã lưu thành công file '{output_filename}'")
    except IOError as e:
        print(f"[ERROR] Không thể ghi vào file {output_filename}: {e}")


# --- 🚀 HÀM CHÍNH (Đã cập nhật quy trình) ---

def process_company(company_name):
    """
    Thực hiện toàn bộ quy trình cho một công ty: tìm kiếm, quét, phân tích và lưu.
    """
    print(f"\n{'='*20} ĐANG XỬ LÝ: {company_name.upper()} {'='*20}")

    # === BƯỚC 1: THU THẬP DỮ LIỆU TỪ WEB ===
    queries = [
        f'"{company_name}" địa chỉ chi nhánh',
        f'"{company_name}" hệ thống cửa hàng',
        f'"{company_name}" ngành nghề kinh doanh',
        f'"{company_name}" giới thiệu công ty',
        f'"{company_name}" masothue.com',
        f'"{company_name}" linkedin',
    ]
    all_urls = []
    for q in queries:
        all_urls.extend(search_google_for_urls(q, num_results=2))
        time.sleep(1)

    unique_urls = list(dict.fromkeys(all_urls))
    print(f"  [INFO] Tìm thấy tổng cộng {len(unique_urls)} URL độc nhất.")

    full_context = ""
    for url in unique_urls:
        content = scrape_website_content(url)
        if content:
            full_context += f"\n\n--- Nguồn: {url} ---\n{content}"
        time.sleep(1)

    # === BƯỚC 2: PHÂN TÍCH DỮ LIỆU BẰNG HAI LUỒNG ===
    scraped_analysis_result = analyze_scraped_content_with_gemini(company_name, full_context)
    direct_analysis_result = get_info_directly_from_gemini(company_name)

    # === BƯỚC 3: TỔNG HỢP KẾT QUẢ ===
    if "error" in scraped_analysis_result and "error" in direct_analysis_result:
        print(f"[ERROR] Cả hai luồng phân tích đều thất bại cho '{company_name}'.")
        error_message = f"Lỗi Scrape: {scraped_analysis_result.get('error', 'N/A')}\nLỗi Direct: {direct_analysis_result.get('error', 'N/A')}"
        data_row = [company_name, error_message, "", "", "", "", "", datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        save_data_to_csv(company_name, data_row)
        return
        
    final_data = merge_data(scraped_analysis_result, direct_analysis_result)

    # === BƯỚC 4: LƯU VÀO CSV ===
    separator = "\n" # Dùng newline để ngăn cách các giá trị trong một ô
    ceo = separator.join(final_data.get("ten_giam_doc", []))
    address = separator.join(final_data.get("dia_chi", []))
    model = separator.join(final_data.get("mo_hinh_kd", []))
    email = separator.join(final_data.get("email", []))
    domain = separator.join(final_data.get("ten_mien", []))
    summary = final_data.get("tom_tat", "Không có tóm tắt.")

    data_row = [
        company_name, summary, ceo or "Chưa rõ", address or "Không có",
        model or "Không rõ", email or "Không tìm thấy", domain or "Không có",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ]
    
    save_data_to_csv(company_name, data_row)


def run_manual_mode():
    """
    Chạy chương trình ở chế độ nhập tay.
    """
    print("\n--- CHƯƠNG TRÌNH TÌM KIẾM THÔNG TIN DOANH NGHIỆP (v2.0 - TỔNG HỢP) ---")
    print("Mỗi công ty sẽ được xử lý qua 2 luồng và lưu vào một file CSV riêng biệt.")
            
    while True:
        company_name = input("\n>>> Nhập tên công ty cần tìm (hoặc gõ 'exit' để thoát): ").strip()
        if company_name.lower() == 'exit':
            break
        if company_name:
            process_company(company_name)

    print("\nChương trình đã kết thúc.")


if __name__ == "__main__":
    run_manual_mode()