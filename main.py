import requests
import csv
import re
import time

API_KEY = 'AIzaSyCNyGhpZHiTHA1_SL7rLpXV5kDrVAJXiaU'
SEARCH_ENGINE_ID = 'f665266b01c05417d'

# Regex tìm email
def extract_email(text):
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    emails = re.findall(email_pattern, text)
    return emails[0] if emails else None

# Regex tìm địa chỉ (sơ bộ)
def extract_address(text):
    pattern = r'(\d{1,4}\s?\w*[\s,]*)*(quận|phường|thành phố|TP\.?|Hà Nội|Hồ Chí Minh|Đà Nẵng|Biên Hòa|Cần Thơ)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    return "Có thể là địa chỉ: " + text if matches else ""

# Regex tìm tên giám đốc
def extract_ceo_name(text):
    match = re.search(r"(ông|bà|chị|anh)\s+[A-ZĐ][a-zàáảãạăắằẳẵặâấầẩẫậêếềểễệôốồổỗộơớờởỡợưứừửữựúùủũụíìỉĩịýỳỷỹỵêèéẽẻ]+(\s+[A-ZĐ][a-zàáảãạăắằẳẵặâấầẩẫậêếềểễệôốồổỗộơớờởỡợưứừửữựúùủũụíìỉĩịýỳỷỹỵêèéẽẻ]+)+", text)
    return match.group(0) if match else ""

# Gọi API Google
def google_search(query, api_key, cse_id, num_results=10):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": min(num_results, 10)
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Lỗi API: {e}")
        return []

    results = []
    data = response.json()
    for item in data.get("items", []):
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        title = item.get("title", "")

        result = {
            "title": title,
            "link": link,
            "snippet": snippet,
            "email": extract_email(snippet + " " + link),
            "ceo_name": extract_ceo_name(snippet) if "giám đốc" in snippet.lower() else "",
            "address_hint": extract_address(snippet) if any(kw in snippet.lower() for kw in ["chi nhánh", "địa chỉ", "văn phòng"]) else "",
            "business_model": "Kinh doanh: " + snippet if "dịch vụ" in snippet.lower() or "sản phẩm" in snippet.lower() or "kinh doanh" in snippet.lower() else ""
        }
        results.append(result)
    return results

# Hàm chính
def main():
    ten_cong_ty = input("🔎 Nhập tên công ty: ").strip()

    roles = ["Giám đốc", "Chi Nhánh", "Mô hình kinh doanh", "liên hệ"]
    domains = ["linkedin.com", "facebook.com", ""]

    all_results = []
    seen_links = set()

    for role in roles:
        for domain in domains:
            query = f"{role} công ty {ten_cong_ty}"
            if domain:
                query += f" site:{domain}"

            print(f"🔍 Đang tìm kiếm: {query}")
            results = google_search(query, API_KEY, SEARCH_ENGINE_ID)

            for result in results:
                if result["link"] not in seen_links:
                    seen_links.add(result["link"])
                    result["role"] = role
                    result["domain"] = domain if domain else "general"
                    all_results.append(result)

            time.sleep(1)

    if not all_results:
        print("⚠️ Không tìm thấy kết quả.")
        return

    # Gộp dữ liệu lại theo từng phần
    ceo_names = set()
    branches = set()
    emails = set()
    business_models = set()

    for r in all_results:
        if r["ceo_name"]:
            ceo_names.add(r["ceo_name"])
        if r["address_hint"]:
            branches.add(r["address_hint"])
        if r["email"]:
            emails.add(r["email"])
        if r["business_model"]:
            business_models.add(r["business_model"])

    # Ghi file tổng hợp
    summary_file = f"{ten_cong_ty.replace(' ', '_')}_thongtin_tonghop.csv"
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Trường thông tin", "Giá trị"])

        writer.writerow(["Tên Giám đốc/CEO", "; ".join(ceo_names) if ceo_names else "Chưa tìm thấy"])
        writer.writerow(["Chi nhánh / Địa chỉ", "; ".join(branches) if branches else "Chưa có thông tin"])
        writer.writerow(["Mô hình kinh doanh", "; ".join(business_models) if business_models else "Chưa rõ"])
        writer.writerow(["Email liên hệ", "; ".join(emails) if emails else "Không tìm thấy email"])

    print(f"✅ Đã lưu file tổng hợp: {summary_file}")

if __name__ == "__main__":
    main()
