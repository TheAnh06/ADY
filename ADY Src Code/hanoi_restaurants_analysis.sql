-- =====================================================================
-- DỰ ÁN: PHÂN TÍCH THỊ TRƯỜNG F&B HÀ NỘI (HANOI RESTAURANTS ANALYSIS)
-- NGUỒN DỮ LIỆU: hanoi_restaurants_cleaned.csv (1.210 records, 22 khu vực)
-- RDBMS: Microsoft SQL Server (T-SQL)
-- =====================================================================

-- =====================================================================
-- BƯỚC 0: THIẾT KẾ SCHEMA, RÀNG BUỘC TOÀN VẸN VÀ ĐÁNH CHỈ MỤC
-- =====================================================================

-- 1. Tạo bảng dữ liệu chuẩn (Single Source of Truth)
IF OBJECT_ID('dbo.SQL_dim_restaurants', 'U') IS NOT NULL
    DROP TABLE dbo.SQL_dim_restaurants;
GO

CREATE TABLE dbo.SQL_dim_restaurants (
    restaurant_id        VARCHAR(20)   NOT NULL PRIMARY KEY,
    restaurant_name      NVARCHAR(255) NOT NULL,
    address              NVARCHAR(500) NOT NULL,
    locality             NVARCHAR(100) NOT NULL,
    locality_verbose     NVARCHAR(200) NOT NULL,
    cuisines             NVARCHAR(300) NOT NULL,
    avg_cost_for_two     INT           NOT NULL CHECK (avg_cost_for_two > 0),
    currency             VARCHAR(10)   NOT NULL DEFAULT 'VND',
    has_table_booking    VARCHAR(5)    NOT NULL CHECK (has_table_booking IN ('Yes', 'No')),
    has_online_delivery  VARCHAR(5)    NOT NULL CHECK (has_online_delivery IN ('Yes', 'No')),
    is_delivering_now    VARCHAR(5)    NOT NULL CHECK (is_delivering_now IN ('Yes', 'No')),
    price_range          TINYINT       NOT NULL CHECK (price_range BETWEEN 1 AND 4),
    aggregate_rating     DECIMAL(3,1)  NOT NULL CHECK (aggregate_rating BETWEEN 0.0 AND 5.0),
    rating_text          NVARCHAR(50)  NOT NULL,
    votes                INT           NOT NULL CHECK (votes >= 0),
    latitude             FLOAT         NOT NULL,
    longitude            FLOAT         NOT NULL
);
GO

-- 2. Đánh chỉ mục phi cụm (Nonclustered Index) kết hợp INCLUDE tối ưu truy vấn gom nhóm theo khu vực
CREATE NONCLUSTERED INDEX IX_Restaurants_Locality 
ON dbo.SQL_dim_restaurants(locality)
INCLUDE (
    avg_cost_for_two, 
    aggregate_rating, 
    votes, 
    has_table_booking, 
    has_online_delivery, 
    price_range, 
    cuisines
);
GO


-- =====================================================================
-- QUERY 3.1: ĐÁNH GIÁ MỨC ĐỘ BÃO HÒA THỊ TRƯỜNG & HIỆU SUẤT THEO KHU VỰC
-- Mục đích: Xác định mật độ tập trung quán ăn và đo lường cung - cầu theo khu vực
-- =====================================================================

DECLARE @TotalCityStores FLOAT = (SELECT COUNT(*) FROM dbo.SQL_dim_restaurants);

SELECT 
    locality AS [Khu vực],
    COUNT(restaurant_id) AS [Số lượng quán],
    ROUND(COUNT(restaurant_id) * 100.0 / @TotalCityStores, 2) AS [Thị phần (%)],
    ROUND(AVG(CAST(avg_cost_for_two AS FLOAT)), 0) AS [Chi phí TB 2 người (VNĐ)],
    ROUND(AVG(aggregate_rating), 2) AS [Điểm TB],
    ROUND(AVG(CAST(votes AS FLOAT)), 1) AS [Lượt Vote TB/quán],
    ROUND(SUM(CASE WHEN aggregate_rating >= 4.5 THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(*), 2) AS [Tỷ lệ quán Xuất sắc (%)]
FROM dbo.SQL_dim_restaurants
GROUP BY locality
ORDER BY [Số lượng quán] DESC;
GO


-- =====================================================================
-- QUERY 3.2: PHÂN TÍCH LỢI THẾ KHÔNG GIAN & TÁC ĐỘNG CỦA CHUYỂN ĐỔI SỐ
-- Mục đích: Đo lường tỷ lệ tích hợp dịch vụ số theo khu vực và hiệu quả theo phân khúc giá
-- =====================================================================

-- Query 3.2a: Tỷ lệ chuyển đổi số (giao hàng online, đặt bàn) theo khu vực
SELECT 
    locality AS [Khu vực],
    COUNT(*) AS [Số quán],
    ROUND(SUM(CASE WHEN has_online_delivery = 'Yes' THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(*), 1) AS [Tỷ lệ Giao hàng Online (%)],
    ROUND(SUM(CASE WHEN has_table_booking = 'Yes' THEN 1.0 ELSE 0.0 END) * 100.0 / COUNT(*), 1) AS [Tỷ lệ Đặt bàn trước (%)],
    ROUND(AVG(CAST(votes AS FLOAT)), 1) AS [Lượt Vote TB]
FROM dbo.SQL_dim_restaurants
GROUP BY locality
ORDER BY [Số quán] DESC;
GO

-- Query 3.2b: Tác động của dịch vụ đặt bàn & giao hàng trực tuyến theo phân khúc giá
SELECT 
    price_range AS [Phân khúc giá],
    has_table_booking AS [Đặt bàn trước],
    has_online_delivery AS [Giao hàng Online],
    COUNT(*) AS [Số lượng quán],
    ROUND(AVG(CAST(avg_cost_for_two AS FLOAT)), 0) AS [Chi phí TB 2 người (VNĐ)],
    ROUND(AVG(aggregate_rating), 2) AS [Điểm đánh giá TB],
    ROUND(AVG(CAST(votes AS FLOAT)), 1) AS [Lượt Vote TB]
FROM dbo.SQL_dim_restaurants
GROUP BY price_range, has_table_booking, has_online_delivery
ORDER BY [Phân khúc giá] DESC, [Lượt Vote TB] DESC;
GO


-- =====================================================================
-- QUERY 3.3: MÔ HÌNH HÓA ĐIỂM TIỀM NĂNG KHU VỰC ĐA TIÊU CHÍ (MCDA)
-- Công thức:
-- Potential Score = (Vote/Max_Vote)*35 + (Rating/Max_Rating)*30 
--                 + (Cost/Max_Cost)*20 + [1 - (Quán/Max_Quán)]*15
-- =====================================================================

WITH LocalityMetrics AS (
    SELECT 
        locality,
        COUNT(*) AS store_count,
        AVG(CAST(votes AS FLOAT)) AS avg_votes,
        AVG(CAST(aggregate_rating AS FLOAT)) AS avg_rating,
        AVG(CAST(avg_cost_for_two AS FLOAT)) AS avg_cost
    FROM dbo.SQL_dim_restaurants
    GROUP BY locality
),
CityBenchmark AS (
    SELECT 
        MAX(avg_votes) AS max_votes,
        MAX(avg_rating) AS max_rating,
        MAX(avg_cost) AS max_cost,
        MAX(store_count) AS max_stores
    FROM LocalityMetrics
)
SELECT 
    m.locality AS [Khu vực],
    m.store_count AS [Số quán],
    ROUND((m.avg_votes / b.max_votes) * 35.0, 2) AS [Điểm Cầu (35đ)],
    ROUND((m.avg_rating / b.max_rating) * 30.0, 2) AS [Điểm Chất lượng (30đ)],
    ROUND((m.avg_cost / b.max_cost) * 20.0, 2) AS [Điểm Chi tiêu (20đ)],
    ROUND((1.0 - (CAST(m.store_count AS FLOAT) / b.max_stores)) * 15.0, 2) AS [Điểm Ít cạnh tranh (15đ)],
    ROUND(
        (m.avg_votes / b.max_votes) * 35.0 +
        (m.avg_rating / b.max_rating) * 30.0 +
        (m.avg_cost / b.max_cost) * 20.0 +
        (1.0 - (CAST(m.store_count AS FLOAT) / b.max_stores)) * 15.0
    , 2) AS [Tổng Điểm Tiềm Năng]
FROM LocalityMetrics m
CROSS JOIN CityBenchmark b
ORDER BY [Tổng Điểm Tiềm Năng] DESC;
GO


-- =====================================================================
-- QUERY 3.4: XÁC ĐỊNH KHOẢNG TRỐNG THỊ TRƯỜNG (WHITESPACE ANALYSIS)
-- Mục đích: Tìm các nhóm ẩm thực có nhu cầu cao nhưng thiếu hụt tại khu vực tiềm năng
-- =====================================================================

-- Bước 1: Các nhóm ẩm thực hút khách nhất toàn thành phố (tối thiểu 20 quán)
SELECT 
    cuisines AS [Nhóm ẩm thực],
    COUNT(*) AS [Số quán toàn TP],
    ROUND(AVG(CAST(votes AS FLOAT)), 1) AS [Lượt Vote TB toàn TP],
    ROUND(AVG(aggregate_rating), 2) AS [Điểm Đánh Giá TB]
FROM dbo.SQL_dim_restaurants
GROUP BY cuisines
HAVING COUNT(*) >= 20
ORDER BY [Lượt Vote TB toàn TP] DESC;
GO

-- Bước 2: Kiểm tra số lượng quán theo nhóm ẩm thực tại khu vực mục tiêu (ví dụ: Long Biên)
SELECT 
    locality AS [Khu vực],
    cuisines AS [Nhóm ẩm thực],
    COUNT(*) AS [Số quán hiện hữu]
FROM dbo.SQL_dim_restaurants
WHERE locality = N'Long Biên'
GROUP BY locality, cuisines
ORDER BY [Số quán hiện hữu] DESC;
GO
