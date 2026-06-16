-- ============================================================================
-- 考研国家线数据（2024-2026年）
-- ============================================================================
--
-- 数据来源说明：
-- 本脚本提供国家线数据结构和示例数据，用于系统开发测试。
--
-- ⚠️ 重要提示：
-- 1. 实际使用前请从以下官方渠道核验准确数值：
--    - 中国研究生招生信息网：https://yz.chsi.com.cn/
--    - 中国教育在线：https://yz.eol.cn/
--    - 教育部官网
-- 2. 国家线每年3月中下旬公布，2026年数据尚未发布
-- 3. 以下数据仅供参考，实际分数线以官方公布为准
--
-- 国家线说明：
-- - line_type: 'national' 表示国家线
-- - university_id, department_id, major_id: NULL（国家线不属于具体学校/专业）
-- - major_category: 学科门类或专业学位类别
-- - 分为 A区（东部发达地区）和 B区（西部欠发达地区），重庆属于 A区
--
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2024年 A区 国家线 - 学术学位（学硕）
-- ----------------------------------------------------------------------------
INSERT INTO score_lines (
    year, line_type, university_id, department_id, major_id,
    major_category, total_score_line,
    politics_line, english_line, subject_one_line, subject_two_line,
    score_diff_to_national, source_id, created_at
) VALUES
    -- 哲学
    (2024, 'national', NULL, NULL, NULL, '哲学', 325, 45, 45, 68, 68, 0, NULL, NOW()),

    -- 经济学
    (2024, 'national', NULL, NULL, NULL, '经济学', 346, 48, 48, 72, 72, 0, NULL, NOW()),

    -- 法学
    (2024, 'national', NULL, NULL, NULL, '法学', 325, 45, 45, 68, 68, 0, NULL, NOW()),

    -- 教育学（不含体育学）
    (2024, 'national', NULL, NULL, NULL, '教育学', 350, 51, 51, 153, 0, 0, NULL, NOW()),

    -- 文学
    (2024, 'national', NULL, NULL, NULL, '文学', 363, 54, 54, 81, 81, 0, NULL, NOW()),

    -- 历史学
    (2024, 'national', NULL, NULL, NULL, '历史学', 336, 46, 46, 138, 0, 0, NULL, NOW()),

    -- 理学
    (2024, 'national', NULL, NULL, NULL, '理学', 279, 39, 39, 59, 59, 0, NULL, NOW()),

    -- 工学（不含工学照顾专业）
    (2024, 'national', NULL, NULL, NULL, '工学', 265, 38, 38, 57, 57, 0, NULL, NOW()),

    -- 农学
    (2024, 'national', NULL, NULL, NULL, '农学', 251, 34, 34, 51, 51, 0, NULL, NOW()),

    -- 医学（不含中医类照顾专业）
    (2024, 'national', NULL, NULL, NULL, '医学', 299, 41, 41, 123, 0, 0, NULL, NOW()),

    -- 军事学
    (2024, 'national', NULL, NULL, NULL, '军事学', 260, 37, 37, 56, 56, 0, NULL, NOW()),

    -- 管理学
    (2024, 'national', NULL, NULL, NULL, '管理学', 340, 48, 48, 72, 72, 0, NULL, NOW()),

    -- 艺术学
    (2024, 'national', NULL, NULL, NULL, '艺术学', 362, 40, 40, 60, 60, 0, NULL, NOW()),

    -- 体育学
    (2024, 'national', NULL, NULL, NULL, '体育学', 300, 42, 42, 126, 0, 0, NULL, NOW()),

    -- 工学照顾专业（力学、冶金、动力、水利、地质、矿业、船舶、航空、兵器、核科学、农业工程）
    (2024, 'national', NULL, NULL, NULL, '工学照顾专业', 255, 36, 36, 54, 54, 0, NULL, NOW()),

    -- 中医类照顾专业
    (2024, 'national', NULL, NULL, NULL, '中医类照顾专业', 289, 39, 39, 117, 0, 0, NULL, NOW());

-- ----------------------------------------------------------------------------
-- 2024年 A区 国家线 - 专业学位（专硕）
-- ----------------------------------------------------------------------------
INSERT INTO score_lines (
    year, line_type, university_id, department_id, major_id,
    major_category, total_score_line,
    politics_line, english_line, subject_one_line, subject_two_line,
    score_diff_to_national, source_id, created_at
) VALUES
    -- 金融、应用统计、税务、国际商务、保险、资产评估
    (2024, 'national', NULL, NULL, NULL, '金融', 346, 48, 48, 72, 72, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '应用统计', 346, 48, 48, 72, 72, 0, NULL, NOW()),

    -- 审计
    (2024, 'national', NULL, NULL, NULL, '审计', 197, 50, 100, 0, 0, 0, NULL, NOW()),

    -- 法律（非法学）、法律（法学）、社会工作、警务
    (2024, 'national', NULL, NULL, NULL, '法律', 325, 45, 45, 68, 68, 0, NULL, NOW()),

    -- 教育、汉语国际教育
    (2024, 'national', NULL, NULL, NULL, '教育', 350, 51, 51, 77, 77, 0, NULL, NOW()),

    -- 应用心理
    (2024, 'national', NULL, NULL, NULL, '应用心理', 350, 51, 51, 153, 0, 0, NULL, NOW()),

    -- 体育
    (2024, 'national', NULL, NULL, NULL, '体育', 300, 42, 42, 126, 0, 0, NULL, NOW()),

    -- 翻译、新闻与传播、出版
    (2024, 'national', NULL, NULL, NULL, '翻译', 363, 54, 54, 81, 81, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '新闻与传播', 363, 54, 54, 81, 81, 0, NULL, NOW()),

    -- 文物与博物馆
    (2024, 'national', NULL, NULL, NULL, '文物与博物馆', 336, 46, 46, 138, 0, 0, NULL, NOW()),

    -- 建筑学、城市规划
    (2024, 'national', NULL, NULL, NULL, '建筑学', 265, 38, 38, 57, 57, 0, NULL, NOW()),

    -- 电子信息、机械、材料与化工、资源与环境、能源动力、土木水利、生物与医药、交通运输
    (2024, 'national', NULL, NULL, NULL, '电子信息', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '机械', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '材料与化工', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '资源与环境', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '能源动力', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '土木水利', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '生物与医药', 260, 38, 38, 57, 57, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '交通运输', 260, 38, 38, 57, 57, 0, NULL, NOW()),

    -- 农业、兽医、风景园林、林业
    (2024, 'national', NULL, NULL, NULL, '农业', 251, 34, 34, 51, 51, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '兽医', 251, 34, 34, 51, 51, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '风景园林', 251, 34, 34, 51, 51, 0, NULL, NOW()),

    -- 临床医学、口腔医学、公共卫生、护理、药学、中药学
    (2024, 'national', NULL, NULL, NULL, '临床医学', 299, 41, 41, 123, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '口腔医学', 299, 41, 41, 123, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '公共卫生', 299, 41, 41, 123, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '护理', 299, 41, 41, 123, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '药学', 299, 41, 41, 123, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '中药学', 289, 39, 39, 117, 0, 0, NULL, NOW()),

    -- 中医
    (2024, 'national', NULL, NULL, NULL, '中医', 289, 39, 39, 117, 0, 0, NULL, NOW()),

    -- 工商管理、公共管理、会计、旅游管理、图书情报、工程管理
    (2024, 'national', NULL, NULL, NULL, '工商管理', 170, 45, 90, 0, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '公共管理', 178, 45, 90, 0, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '会计', 197, 50, 100, 0, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '旅游管理', 170, 45, 90, 0, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '图书情报', 197, 50, 100, 0, 0, 0, NULL, NOW()),
    (2024, 'national', NULL, NULL, NULL, '工程管理', 178, 45, 90, 0, 0, 0, NULL, NOW()),

    -- 艺术
    (2024, 'national', NULL, NULL, NULL, '艺术', 362, 40, 40, 60, 60, 0, NULL, NOW());

-- ----------------------------------------------------------------------------
-- 2025年 A区 国家线（示例，实际数据请从官方核验）
-- ----------------------------------------------------------------------------
-- 注意：2025年国家线通常在2025年3月中下旬公布
-- 以下数据为示例，实际使用时需要替换为官方数据

INSERT INTO score_lines (
    year, line_type, university_id, department_id, major_id,
    major_category, total_score_line,
    politics_line, english_line, subject_one_line, subject_two_line,
    score_diff_to_national, source_id, created_at
) VALUES
    -- 学术学位（学硕）- 主要门类
    (2025, 'national', NULL, NULL, NULL, '哲学', 330, 46, 46, 69, 69, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '经济学', 348, 49, 49, 74, 74, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '法学', 328, 46, 46, 69, 69, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '教育学', 352, 52, 52, 156, 0, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '文学', 365, 55, 55, 83, 83, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '历史学', 338, 47, 47, 141, 0, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '理学', 282, 40, 40, 60, 60, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '工学', 268, 39, 39, 59, 59, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '农学', 253, 35, 35, 53, 53, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '医学', 302, 42, 42, 126, 0, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '管理学', 343, 49, 49, 74, 74, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '艺术学', 365, 41, 41, 62, 62, 0, NULL, NOW()),

    -- 专业学位（专硕）- 主要类别
    (2025, 'national', NULL, NULL, NULL, '电子信息', 263, 39, 39, 59, 59, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '机械', 263, 39, 39, 59, 59, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '材料与化工', 263, 39, 39, 59, 59, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '工商管理', 172, 46, 92, 0, 0, 0, NULL, NOW()),
    (2025, 'national', NULL, NULL, NULL, '会计', 200, 51, 102, 0, 0, 0, NULL, NOW());

-- ============================================================================
-- 使用说明
-- ============================================================================
--
-- 1. 执行本脚本前，请先备份数据库
-- 2. 执行命令：
--    docker compose --profile mysql exec -T mysql mysql -uzhiyuan_app -pzhiyuan123456 zhiyuan < sql/mysql/003_national_score_lines.sql
--
-- 3. 验证入库结果：
--    SELECT line_type, COUNT(*) FROM score_lines GROUP BY line_type;
--    预期结果：
--    - major: 6610 (原有专业线)
--    - national: 约 60-80 条 (新增国家线)
--
-- 4. 查看具体国家线：
--    SELECT year, major_category, total_score_line, politics_line, english_line
--    FROM score_lines
--    WHERE line_type = 'national' AND year = 2024
--    ORDER BY major_category;
--
-- 5. 测试分数线评估接口：
--    curl -X POST http://127.0.0.1:5000/api/score/evaluate \
--      -H "Content-Type: application/json" \
--      -d '{"target_year": 2024, "major_category": "工学", "total_score": 280,
--           "politics_score": 45, "english_score": 45,
--           "subject_one_score": 90, "subject_two_score": 90}'
--
-- ============================================================================

-- 查询验证脚本
-- SELECT
--     year,
--     line_type,
--     major_category,
--     total_score_line,
--     politics_line,
--     english_line,
--     subject_one_line,
--     subject_two_line
-- FROM score_lines
-- WHERE line_type = 'national'
-- ORDER BY year DESC, major_category;
