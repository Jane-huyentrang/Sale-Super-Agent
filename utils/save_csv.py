import csv

def save_to_csv(data, filename="vietnambiz_summary.csv"):
    """
    Lưu dữ liệu vào file CSV.
    """
    if not data:
        print("Không có dữ liệu để lưu.")
        return
    
    print(f"\n💾 Đang lưu {len(data)} bài viết vào file {filename}...")
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        # Đảm bảo có đủ các trường 'title', 'url', 'summary'
        writer = csv.DictWriter(f, fieldnames=["title", "url", "summary"])
        writer.writeheader()
        writer.writerows(data)
    print(f"✅ Đã lưu thành công!")