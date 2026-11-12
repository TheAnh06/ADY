"""
clean_data.py - Quy trình làm sạch dữ liệu tập quán ăn Hà Nội (hanoi_restaurants_1.csv)
"""

import sys

# Đảm bảo in tiếng Việt trên console Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import pandas as pd


def clean_hanoi_restaurants(
    input_path: str = 'hanoi_restaurants_1.csv',
    output_path: str = 'hanoi_restaurants_cleaned.csv',
):
    print(f'[+] Đang tải dữ liệu từ {input_path}...')
    df = pd.read_csv(input_path)
    print(f'    Tổng số dòng: {len(df)}, số cột ban đầu: {len(df.columns)}')

    # 1. Điền giá trị khuyết thiếu cho Locality Verbose
    print('[+] Xử lý giá trị khuyết thiếu cho "Locality Verbose"...')
    urban_districts = {
        'Ba Đình',
        'Bắc Từ Liêm',
        'Cầu Giấy',
        'Đống Đa',
        'Hà Đông',
        'Hai Bà Trưng',
        'Hoàn Kiếm',
        'Hoàng Mai',
        'Long Biên',
        'Nam Từ Liêm',
        'Tây Hồ',
        'Thanh Xuân',
    }

    def fill_locality_verbose(row):
        val = row['Locality Verbose']
        if pd.isna(val) or str(val).strip() == '':
            loc = row['Locality']
            if loc in urban_districts:
                return f'Quận {loc}, Hà Nội'
            else:
                return f'{loc}, Hà Nội'
        return str(val).strip()

    df['Locality Verbose'] = df.apply(fill_locality_verbose, axis=1)

    # 2. Loại bỏ các cột không cần thiết theo yêu cầu: 'Country Code', 'Switch to order menu', 'City'
    cols_to_drop = [
        col
        for col in ['Country Code', 'Switch to order menu', 'City']
        if col in df.columns
    ]
    if cols_to_drop:
        print(f'[+] Loại bỏ các cột không cần thiết: {cols_to_drop}...')
        df = df.drop(columns=cols_to_drop)

    # 3. Chuẩn hóa ngôn ngữ Rating text sang Tiếng Việt
    print('[+] Chuẩn hóa ngôn ngữ cho cột "Rating text"...')
    rating_map_vi = {
        'Excellent': 'Xuất sắc',
        'Very Good': 'Rất tốt',
        'Good': 'Tốt',
        'Average': 'Trung bình',
        'Xuất sắc': 'Xuất sắc',
        'Rất tốt': 'Rất tốt',
        'Tốt': 'Tốt',
        'Trung bình': 'Trung bình',
    }
    df['Rating text'] = df['Rating text'].map(rating_map_vi)

    # 4. Chuẩn hóa định dạng Address (đồng nhất đuôi ", Hà Nội")
    print('[+] Chuẩn hóa địa chỉ trong cột "Address"...')

    def standardize_address(addr):
        addr = str(addr).strip()
        if not addr.endswith('Hà Nội'):
            addr = addr.rstrip(', ') + ', Hà Nội'
        return addr

    df['Address'] = df['Address'].apply(standardize_address)

    # 5. Đồng bộ hóa phân loại giá "Price range"
    print('[+] Đồng bộ hóa phân loại giá "Price range"...')

    def standardize_price_range(cost):
        if cost <= 115000:
            return 1
        elif cost <= 260000:
            return 2
        elif cost <= 450000:
            return 3
        else:
            return 4

    df['Price range'] = df['Average Cost for two'].apply(standardize_price_range)

    # 6. Chuẩn hóa chính tả và viết hoa trong Cuisines
    print('[+] Chuẩn hóa danh mục món ăn trong "Cuisines"...')
    canonical_tags = {
        'đồ âu': 'Đồ Âu',
        'món việt': 'Món Việt',
        'món hàn': 'Món Hàn',
        'món nhật': 'Món Nhật',
        'món trung': 'Món Trung',
        'món thái': 'Món Thái',
        'món huế': 'Món Huế',
        'món ý': 'Món Ý',
        'món á': 'Món Á',
        'món tây bắc': 'Món Tây Bắc',
        'bbq': 'BBQ',
        'buffet': 'Buffet',
        'cafe': 'Cafe',
        'lẩu': 'Lẩu',
        'đồ nướng': 'Đồ nướng',
        'đồ ăn nhanh': 'Đồ ăn nhanh',
        'ăn vặt': 'Ăn vặt',
        'cơm bình dân': 'Cơm bình dân',
        'đồ nướng hàn quốc': 'Đồ nướng Hàn Quốc',
        'đồ nướng nhật bản': 'Đồ nướng Nhật Bản',
        'lẩu trung hoa': 'Lẩu Trung Hoa',
        'lẩu nấm thiên nhiên': 'Lẩu nấm thiên nhiên',
        'lẩu thái': 'Lẩu Thái',
        'lẩu đài loan': 'Lẩu Đài Loan',
        'cơm niêu singapore': 'Cơm niêu Singapore',
    }

    def clean_cuisines(c_str):
        tags = [t.strip() for t in str(c_str).split(',') if t.strip()]
        normalized = []
        for t in tags:
            low = t.lower()
            if low in canonical_tags:
                normalized.append(canonical_tags[low])
            else:
                normalized.append(t)
        return ', '.join(normalized)

    df['Cuisines'] = df['Cuisines'].apply(clean_cuisines)

    # 7. Xóa khoảng trắng thừa ở tất cả các cột dạng text
    str_cols = df.select_dtypes(include=['object', 'string']).columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()

    # 8. Lưu kết quả ra file mới
    try:
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
    except PermissionError:
        print(
            f'[!] Cảnh báo: Không thể ghi đè {output_path} do file đang được mở trong Excel/ứng dụng khác.'
        )
        print('[!] Vui lòng đóng file trong Excel và chạy lại nếu muốn ghi đè.')
        return df
    print(
        f'[✓] Hoàn thành làm sạch dữ liệu! Kết quả được lưu tại: {output_path}'
    )
    print(f'    Số dòng: {len(df)}, số cột sau làm sạch: {len(df.columns)}')
    print(f'    Danh sách cột: {list(df.columns)}')
    print(f'    Số giá trị null còn lại: {df.isnull().sum().sum()}')
    return df


if __name__ == '__main__':
    clean_hanoi_restaurants()
