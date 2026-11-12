"""
Nạp hanoi_restaurants_cleaned.csv vào SQL Server thành 3 bảng: Location, Restaurant, Review.

Cài thư viện (1 lần):   pip install pandas pyodbc
Chạy (Windows Auth):    python import_to_sqlserver.py --csv hanoi_restaurants_cleaned.csv --server localhost
Chạy (SQLEXPRESS):      python import_to_sqlserver.py --csv hanoi_restaurants_cleaned.csv --server "localhost\\SQLEXPRESS"
Chạy (user/password):   python import_to_sqlserver.py --csv ... --server localhost --user sa --password MatKhau
Thử không cần SQL Server (SQLite):  python import_to_sqlserver.py --csv ... --sqlite test.db
"""
import argparse
import sys
import pandas as pd

HOA_LAC = ["Hòa Lạc", "Thạch Hòa", "Tân Xã", "Bắc Phú Cát", "Thạch Thất",
           "Liên Quan", "Tây Phương", "Yên Bình", "Bình Yên", "Phú Cát"]

RENAME = {
    "Restaurant ID": "restaurant_id", "Restaurant Name": "restaurant_name", "Address": "address",
    "Locality": "locality", "Locality Verbose": "locality_verbose", "Cuisines": "cuisines",
    "Average Cost for two": "average_cost_for_two", "Currency": "currency",
    "Has Table booking": "has_table_booking", "Has Online delivery": "has_online_delivery",
    "Is delivering now": "is_delivering_now", "Price range": "price_range",
    "Aggregate rating": "aggregate_rating", "Rating text": "rating_text", "Votes": "votes",
}


# ---------------------------------------------------------------- 1. Chuẩn bị dữ liệu
def prepare(csv_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig").rename(columns=RENAME)
    need = list(RENAME.values()) + ["latitude", "longitude"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        sys.exit(f"File CSV thiếu cột: {missing}. Hãy dùng đúng file hanoi_restaurants_cleaned.csv")
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].astype(str).str.strip()
    assert df.restaurant_id.is_unique, "restaurant_id bị trùng"
    df["area_group"] = df.locality.apply(lambda x: "Hoa Lac" if x in HOA_LAC else "Inner-City")

    loc = (df[["locality", "locality_verbose", "area_group"]].drop_duplicates()
           .sort_values(["area_group", "locality"]).reset_index(drop=True))
    assert loc.locality.is_unique, "Một locality có nhiều locality_verbose, hãy kiểm tra lại dữ liệu"
    loc.insert(0, "location_id", range(1, len(loc) + 1))
    df = df.merge(loc, on=["locality", "locality_verbose", "area_group"], how="left")

    restaurant = df[["restaurant_id", "restaurant_name", "location_id", "address", "cuisines",
                     "average_cost_for_two", "currency", "has_table_booking", "has_online_delivery",
                     "is_delivering_now", "latitude", "longitude", "price_range"]]
    review = df[["restaurant_id", "aggregate_rating", "rating_text", "votes"]]
    return loc, restaurant, review


def rows(frame):
    """DataFrame -> list tuple kiểu Python thuần (pyodbc/sqlite không nhận numpy)."""
    return list(frame.astype(object).where(frame.notna(), None).itertuples(index=False, name=None))


# ---------------------------------------------------------------- 2. Câu lệnh tạo bảng
DDL_SQLSERVER = [
    "IF OBJECT_ID('dbo.Review','U') IS NOT NULL DROP TABLE dbo.Review",
    "IF OBJECT_ID('dbo.Restaurant','U') IS NOT NULL DROP TABLE dbo.Restaurant",
    "IF OBJECT_ID('dbo.Location','U') IS NOT NULL DROP TABLE dbo.Location",
    """CREATE TABLE dbo.Location (
        location_id INT NOT NULL PRIMARY KEY,
        locality NVARCHAR(100) NOT NULL,
        locality_verbose NVARCHAR(200) NOT NULL,
        area_group NVARCHAR(20) NOT NULL)""",
    """CREATE TABLE dbo.Restaurant (
        restaurant_id NVARCHAR(20) NOT NULL PRIMARY KEY,
        restaurant_name NVARCHAR(300) NOT NULL,
        location_id INT NOT NULL REFERENCES dbo.Location(location_id),
        address NVARCHAR(500) NULL,
        cuisines NVARCHAR(300) NULL,
        average_cost_for_two INT NOT NULL,
        currency NVARCHAR(10) NOT NULL,
        has_table_booking NVARCHAR(3) NOT NULL,
        has_online_delivery NVARCHAR(3) NOT NULL,
        is_delivering_now NVARCHAR(3) NOT NULL,
        latitude FLOAT NOT NULL,
        longitude FLOAT NOT NULL,
        price_range INT NOT NULL)""",
    """CREATE TABLE dbo.Review (
        restaurant_id NVARCHAR(20) NOT NULL PRIMARY KEY REFERENCES dbo.Restaurant(restaurant_id),
        aggregate_rating FLOAT NOT NULL,
        rating_text NVARCHAR(50) NULL,
        votes INT NOT NULL)""",
    "CREATE INDEX ix_restaurant_location ON dbo.Restaurant(location_id)",
]
DDL_SQLITE = [
    "DROP TABLE IF EXISTS Review", "DROP TABLE IF EXISTS Restaurant", "DROP TABLE IF EXISTS Location",
    "CREATE TABLE Location (location_id INTEGER PRIMARY KEY, locality TEXT, locality_verbose TEXT, area_group TEXT)",
    """CREATE TABLE Restaurant (restaurant_id TEXT PRIMARY KEY, restaurant_name TEXT, location_id INTEGER,
        address TEXT, cuisines TEXT, average_cost_for_two INTEGER, currency TEXT, has_table_booking TEXT,
        has_online_delivery TEXT, is_delivering_now TEXT, latitude REAL, longitude REAL, price_range INTEGER)""",
    "CREATE TABLE Review (restaurant_id TEXT PRIMARY KEY, aggregate_rating REAL, rating_text TEXT, votes INTEGER)",
]

CHECKS = [
    ("Số khu vực (kỳ vọng 22)", "SELECT COUNT(*) FROM Location"),
    ("Số quán (kỳ vọng 1210)", "SELECT COUNT(*) FROM Restaurant"),
    ("Số review (kỳ vọng 1210)", "SELECT COUNT(*) FROM Review"),
    ("Quán theo khu vực (kỳ vọng Hoa Lac 210, Inner-City 1000)",
     "SELECT l.area_group, COUNT(*) FROM Restaurant r JOIN Location l ON r.location_id = l.location_id GROUP BY l.area_group"),
    ("Chi phí TB theo khu vực (kỳ vọng ~201262 / ~269024)",
     "SELECT l.area_group, ROUND(AVG(CAST(r.average_cost_for_two AS FLOAT)),0) FROM Restaurant r "
     "JOIN Location l ON r.location_id = l.location_id GROUP BY l.area_group"),
]


def report(cur):
    print("\n=== KIỂM TRA SAU KHI NẠP ===")
    for title, sql in CHECKS:
        cur.execute(sql)
        print(f"- {title}: {cur.fetchall()}")


# ---------------------------------------------------------------- 3. Nạp vào CSDL
def load_sqlserver(args, loc, rest, rev):
    try:
        import pyodbc
    except ImportError:
        sys.exit("Chưa cài pyodbc. Chạy: pip install pyodbc")
    auth = f"UID={args.user};PWD={args.password}" if args.user else "Trusted_Connection=yes"
    base = (f"DRIVER={{{args.driver}}};SERVER={args.server};{auth};TrustServerCertificate=yes")
    try:
        master = pyodbc.connect(base + ";DATABASE=master", autocommit=True)
    except pyodbc.Error as e:
        sys.exit(f"Không kết nối được SQL Server: {e}\nDriver đang có trên máy: {pyodbc.drivers()}\n"
                 f"Đổi --driver cho khớp (vd 'ODBC Driver 18 for SQL Server') hoặc kiểm tra --server.")
    master.execute(f"IF DB_ID(N'{args.database}') IS NULL CREATE DATABASE [{args.database}]")
    master.close()

    conn = pyodbc.connect(base + f";DATABASE={args.database}")
    cur = conn.cursor()
    cur.fast_executemany = True
    for stmt in DDL_SQLSERVER:
        cur.execute(stmt)
    cur.executemany("INSERT INTO dbo.Location VALUES (?,?,?,?)", rows(loc))
    cur.executemany("INSERT INTO dbo.Restaurant VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows(rest))
    cur.executemany("INSERT INTO dbo.Review VALUES (?,?,?,?)", rows(rev))
    conn.commit()
    report(cur)
    conn.close()
    print(f"\nXong. Database: {args.database} trên {args.server}")


def load_sqlite(path, loc, rest, rev):
    import sqlite3
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    for stmt in DDL_SQLITE:
        cur.execute(stmt)
    cur.executemany("INSERT INTO Location VALUES (?,?,?,?)", rows(loc))
    cur.executemany("INSERT INTO Restaurant VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows(rest))
    cur.executemany("INSERT INTO Review VALUES (?,?,?,?)", rows(rev))
    conn.commit()
    report(cur)
    conn.close()
    print(f"\nXong (SQLite). File: {path}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Nạp CSV nhà hàng Hà Nội vào SQL Server")
    p.add_argument("--csv", default="hanoi_restaurants_cleaned.csv")
    p.add_argument("--server", default="localhost", help=r"vd: localhost hoặc localhost\SQLEXPRESS")
    p.add_argument("--database", default="RestaurantAnalysis")
    p.add_argument("--driver", default="ODBC Driver 17 for SQL Server")
    p.add_argument("--user", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--sqlite", default=None, help="Chỉ để thử: ghi ra file SQLite thay vì SQL Server")
    a = p.parse_args()

    L, R, V = prepare(a.csv)
    print(f"Đã đọc CSV: {len(R)} quán, {len(L)} khu vực")
    if a.sqlite:
        load_sqlite(a.sqlite, L, R, V)
    else:
        load_sqlserver(a, L, R, V)
