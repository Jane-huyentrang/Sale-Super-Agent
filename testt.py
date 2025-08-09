# main.py
from crawler.vietnambiz import crawl_vietnambiz_page, extract_article_content, summarize_content_with_retry
from utils.save_csv import save_to_csv
import time

def main():

    all_leads_with_summary = []
    
    # Crawl 1 trang để kiểm tra (bạn có thể tăng lên, ví dụ range(1, 4) để crawl 3 trang)
    for page in range(1, 2): 
        url = f"https://vietnambiz.vn/doanh-nghiep/trang-{page}.htm"
        leads = crawl_vietnambiz_page(url)

        for lead in leads:
            print("-" * 50)
            content = extract_article_content(lead['url'])
            
            # Chỉ tóm tắt nếu có nội dung
            if content:
                summary = summarize_content_with_retry(content)
                lead["summary"] = summary
                print(f"Tóm tắt: {summary[:100]}...") # In ra 100 ký tự đầu của tóm tắt
            else:
                lead["summary"] = "Không thể trích xuất nội dung."
                print("Không thể trích xuất nội dung, bỏ qua tóm tắt.")
            
            all_leads_with_summary.append(lead)
            
            # Thêm một khoảng nghỉ ngắn giữa các bài viết để tránh làm quá tải server của trang web
            time.sleep(1)

    if all_leads_with_summary:
        save_to_csv(all_leads_with_summary)
    else:
        print("\nKhông thu thập được bài viết nào.")

if __name__ == "__main__":
    main()
