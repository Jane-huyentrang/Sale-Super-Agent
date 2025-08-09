import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv
import os
import time
import json
from datetime import datetime
import re

load_dotenv()

# Lấy API keys từ biến môi trường
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Kiểm tra API keys ngay từ đầu
if not all([GOOGLE_API_KEY, SEARCH_ENGINE_ID, GEMINI_API_KEY]):
    print("Không tìm thấy đủ API Keys.")
    print("Vui lòng kiểm tra lại file .env của bạn.")
    exit()

# Cấu hình Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel(model_name="gemini-1.5-flash-latest")
    print(" Cấu hình và kết nối tới Gemini thành công.")
except Exception as e:
    print(f" Lỗi cấu hình Gemini API: {e}")
    exit()

def search_google_for_urls(query, num_results=3):
    print(f"[SEARCH] Tìm kiếm Google với truy vấn: '{query}'")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": query, "key": GOOGLE_API_KEY, "cx": SEARCH_ENGINE_ID, "num": num_results}
    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        return [item["link"] for item in res.json().get("items", [])]
    except Exception as e:
        print(f"  [WARN] Lỗi khi gọi Google Search API: {e}")
        return []

def scrape_website_content(url):
    print(f"  [SCRAPE] Đang quét nội dung từ: {url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for script_or_style in soup(["script", "style", "header", "footer", "nav", "aside"]):
            script_or_style.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"  [WARN] Không thể quét nội dung từ {url}: {e}")
        return ""

def _call_gemini_with_retry(prompt):
    max_retries = 3
    delay_seconds = 60
    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(prompt)
            cleaned_response = response.text.strip().lstrip("```json").rstrip("```")
            return json.loads(cleaned_response)
        except Exception as e:
            if "429" in str(e):
                print(f" Lỗi giới hạn (429). Chờ {delay_seconds}s... (Lần {attempt + 1}/{max_retries})")
                time.sleep(delay_seconds)
                delay_seconds *= 2
            else:
                print(f" Lỗi Gemini/JSON: {e}")
                return {"error": str(e), "raw_response": response.text if 'response' in locals() else 'Không có phản hồi'}
    return {"error": "Hết giới hạn API sau nhiều lần thử."}


def analyze_scraped_content_with_gemini(company_name, context):
    """Phân tích nội dung đã quét để tìm xu hướng phát triển."""
    print("  [ANALYZE 1/2] Đưa dữ liệu web-scrape cho Gemini phân tích xu hướng...")
    if not context.strip():
        return {"error": "Không có nội dung web-scrape để phân tích."}

    prompt = f"""
    Bạn là một nhà phân tích kinh doanh. Dựa vào khối văn bản được cung cấp về công ty '{company_name}', hãy trích xuất thông tin và PHÂN TÍCH XU HƯỚNG PHÁT TRIỂN của họ. Trả về kết quả theo cấu trúc JSON sau.
    
    Cấu trúc JSON:
    {{
        "thong_tin_co_ban": {{
            "ten_giam_doc": ["Tên 1", "Tên 2"],
            "dia_chi": ["Địa chỉ 1"],
            "mo_hinh_kd": ["Ngành nghề kinh doanh 1"],
            "email": ["email1@example.com"],
            "ten_mien": ["domain1.com"],
            "doi_tac_khach_hang": ["Tên đối tác 1"]
        }},
        "phan_tich_xu_huong": {{
            "diem_tich_cuc": [
                "Ví dụ: Doanh thu tăng trưởng 20% so với cùng kỳ.",
                "Ví dụ: Ra mắt thành công sản phẩm mới X được thị trường đón nhận."
            ],
            "thach_thuc_diem_tieu_cuc": [
                "Ví dụ: Biên lợi nhuận giảm do chi phí nguyên liệu tăng.",
                "Ví dụ: Đối mặt cạnh tranh gay gắt từ đối thủ Y."
            ],
            "ke_hoach_tuong_lai": [
                "Ví dụ: Kế hoạch mở rộng sang thị trường Đông Nam Á.",
                "Ví dụ: Dự kiến đầu tư vào công nghệ AI để tối ưu vận hành."
            ],
            "tom_tat_xu_huong": "Tóm tắt ngắn gọn về xu hướng phát triển chung của công ty dựa trên các điểm trên."
        }}
    }}

    --- NỘI DUNG VĂN BẢN (từ web scrape) ---
    {context}
    --- KẾT THÚC NỘI DUNG ---
    """
    return _call_gemini_with_retry(prompt)

def get_info_directly_from_gemini(company_name):
    """Hỏi trực tiếp Gemini để phân tích xu hướng dựa trên kiến thức của nó."""
    print(f"  [ANALYZE 2/2] Hỏi trực tiếp Gemini về xu hướng của '{company_name}'...")
    prompt = f"""
    Bạn là một chuyên gia phân tích thị trường. Dựa trên kiến thức của bạn, hãy phân tích tổng quan về công ty '{company_name}' và xu hướng phát triển của họ. Trả về kết quả dưới dạng một đối tượng JSON duy nhất theo cấu trúc sau.

    Cấu trúc JSON:
    {{
        "thong_tin_co_ban": {{
            "ten_giam_doc": ["Tên giám đốc hoặc người đại diện"],
            "dia_chi": ["Địa chỉ trụ sở chính"],
            "mo_hinh_kd": ["Các ngành nghề kinh doanh chính"],
            "email": ["Email liên hệ chính"],
            "ten_mien": ["Tên miền website"],
            "doi_tac_khach_hang": ["Tên các đối tác chiến lược hoặc khách hàng lớn"]
        }},
        "phan_tich_xu_huong": {{
            "diem_tich_cuc": ["Các thành tựu, điểm mạnh, tăng trưởng nổi bật."],
            "thach_thuc_diem_tieu_cuc": ["Những khó khăn, thách thức, hoặc điểm yếu mà công ty đang đối mặt."],
            "ke_hoach_tuong_lai": ["Các định hướng, kế hoạch, dự án tương lai đã được công bố."],
            "tom_tat_xu_huong": "Một bản tóm tắt súc tích về quỹ đạo phát triển của công ty (ví dụ: đang tăng trưởng mạnh, ổn định, hay đang trong giai đoạn tái cấu trúc)."
        }}
    }}
    """
    return _call_gemini_with_retry(prompt)

def merge_data(scraped_data, direct_data):
    """Hợp nhất dữ liệu từ hai nguồn, tập trung vào việc gộp các danh sách."""
    print("  [MERGE] Đang tổng hợp dữ liệu từ 2 nguồn...")
    if "error" in scraped_data: scraped_data = {}
    if "error" in direct_data: direct_data = {}

    final_data = {"thong_tin_co_ban": {}, "phan_tich_xu_huong": {}}

    # Hợp nhất thông tin cơ bản
    base_info_keys = ["ten_giam_doc", "dia_chi", "mo_hinh_kd", "email", "ten_mien", "doi_tac_khach_hang"]
    for key in base_info_keys:
        s1 = set(scraped_data.get("thong_tin_co_ban", {}).get(key, []))
        s2 = set(direct_data.get("thong_tin_co_ban", {}).get(key, []))
        final_data["thong_tin_co_ban"][key] = sorted(list(s1.union(s2)))

    # Hợp nhất phân tích xu hướng
    trend_keys = ["diem_tich_cuc", "thach_thuc_diem_tieu_cuc", "ke_hoach_tuong_lai"]
    for key in trend_keys:
        s1 = set(scraped_data.get("phan_tich_xu_huong", {}).get(key, []))
        s2 = set(direct_data.get("phan_tich_xu_huong", {}).get(key, []))
        final_data["phan_tich_xu_huong"][key] = sorted(list(s1.union(s2)))

    summary1 = scraped_data.get("phan_tich_xu_huong", {}).get("tom_tat_xu_huong", "")
    summary2 = direct_data.get("phan_tich_xu_huong", {}).get("tom_tat_xu_huong", "")
    final_data["phan_tich_xu_huong"]["tom_tat_xu_huong"] = summary2 if summary2 else summary1

    return final_data

def save_data_to_json(company_name, data_dict):
    """Lưu một đối tượng dữ liệu vào file JSON riêng biệt cho công ty."""
    safe_filename = re.sub(r'[\\/*?:"<>|]', "", company_name).replace(' ', '_')
    output_filename = f"{safe_filename}.json"
    print(f"  [SAVE] Đang lưu dữ liệu vào file: {output_filename}")
    try:
        with open(output_filename, "w", encoding="utf-8") as file:
            json.dump(data_dict, file, ensure_ascii=False, indent=4)
        print(f"[OK] Đã lưu thành công file '{output_filename}'")
    except IOError as e:
        print(f"[ERROR] Không thể ghi vào file {output_filename}: {e}")

def process_company(company_name):
    """Thực hiện toàn bộ quy trình cho một công ty."""
    print(f"\n{'='*20} ĐANG XỬ LÝ: {company_name.upper()} {'='*20}")
    
    queries = [
        f'"{company_name}" báo cáo thường niên',
        f'"{company_name}" kết quả kinh doanh gần đây',
        f'"{company_name}" kế hoạch phát triển',
        f'"{company_name}" tin tức sự kiện',
        f'"{company_name}" phân tích cổ phiếu',
        f'"{company_name}" định hướng chiến lược'
    ]
    
    all_urls = []
    for q in queries:
        all_urls.extend(search_google_for_urls(q))
        time.sleep(1)

    unique_urls = list(dict.fromkeys(all_urls))
    print(f"  [INFO] Tìm thấy tổng cộng {len(unique_urls)} URL độc nhất.")

    full_context = ""
    for url in unique_urls:
        content = scrape_website_content(url)
        if content:
            full_context += f"\n\n--- Nguồn: {url} ---\n{content}"
        time.sleep(1)

    scraped_analysis = analyze_scraped_content_with_gemini(company_name, full_context)
    direct_analysis = get_info_directly_from_gemini(company_name)
    
    final_data = merge_data(scraped_analysis, direct_analysis)
    final_data["ten_cong_ty_query"] = company_name
    final_data["thoi_gian_quet"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    save_data_to_json(company_name, final_data)

def run_manual_mode():
    """Chạy chương trình ở chế độ nhập tay."""
    print("\n--- CHƯƠNG TRÌNH PHÂN TÍCH XU HƯỚNG DOANH NGHIỆP (v3.0) ---")
    print("Mỗi công ty sẽ được phân tích và lưu vào một file JSON riêng biệt.")
    while True:
        company_name = input("\n>>> Nhập tên công ty cần phân tích (hoặc gõ 'exit' để thoát): ").strip()
        if company_name.lower() == 'exit':
            break
        if company_name:
            process_company(company_name)
    print("\nChương trình đã kết thúc.")

if __name__ == "__main__":
    run_manual_mode()