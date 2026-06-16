#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从 score_diff_to_national 反推国家线。

通过掌上考研提供的"专业线与国家线的差值"，反推国家线的总分和单科分数。
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.database import fetch_all


def derive_national_lines():
    """从 score_diff_to_national 反推国家线。"""

    # 查询所有有 diff 的分数线
    rows = fetch_all(
        """
        SELECT
            year,
            major_category,
            total_score_line,
            politics_line,
            english_line,
            subject_one_line,
            subject_two_line,
            score_diff_to_national
        FROM score_lines
        WHERE score_diff_to_national IS NOT NULL
          AND score_diff_to_national != 0
        ORDER BY year DESC, major_category
        """
    )

    print(f"查询到 {len(rows)} 条有 diff 的分数线数据\n")

    # 按 year + major_category 聚合
    groups = defaultdict(list)
    for row in rows:
        key = (row['year'], row['major_category'])
        national_line = row['total_score_line'] - row['score_diff_to_national']
        groups[key].append({
            'national_total': national_line,
            'politics': row['politics_line'],
            'english': row['english_line'],
            'subject_one': row['subject_one_line'],
            'subject_two': row['subject_two_line']
        })

    # 计算每个专业门类的国家线
    results = []
    for (year, major_category), samples in sorted(groups.items()):
        if len(samples) < 3:  # 样本太少，跳过
            continue

        # 计算总分线
        total_lines = [s['national_total'] for s in samples]
        avg_total = round(mean(total_lines))
        std_total = round(stdev(total_lines), 2) if len(total_lines) > 1 else 0

        # 标准差太大说明推导不一致，跳过
        if std_total > 10:
            continue

        # 计算单科线（可能有 NULL）
        politics_lines = [s['politics'] for s in samples if s['politics'] is not None]
        english_lines = [s['english'] for s in samples if s['english'] is not None]
        subject_one_lines = [s['subject_one'] for s in samples if s['subject_one'] is not None]
        subject_two_lines = [s['subject_two'] for s in samples if s['subject_two'] is not None]

        avg_politics = round(mean(politics_lines)) if politics_lines else None
        avg_english = round(mean(english_lines)) if english_lines else None
        avg_subject_one = round(mean(subject_one_lines)) if subject_one_lines else None
        avg_subject_two = round(mean(subject_two_lines)) if subject_two_lines else None

        results.append({
            'year': year,
            'major_category': major_category,
            'total_score_line': avg_total,
            'politics_line': avg_politics,
            'english_line': avg_english,
            'subject_one_line': avg_subject_one,
            'subject_two_line': avg_subject_two,
            'sample_count': len(samples),
            'std_dev': std_total
        })

    return results


def print_results(results: list[dict]):
    """打印推导结果。"""
    print("=" * 120)
    print(f"{'年份':<8} {'专业门类':<25} {'总分线':<8} {'政治':<6} {'英语':<6} {'专业课一':<10} {'专业课二':<10} {'样本数':<8} {'标准差':<8}")
    print("=" * 120)

    for r in results:
        print(
            f"{r['year']:<8} "
            f"{r['major_category']:<25} "
            f"{r['total_score_line']:<8} "
            f"{r['politics_line'] or '-':<6} "
            f"{r['english_line'] or '-':<6} "
            f"{r['subject_one_line'] or '-':<10} "
            f"{r['subject_two_line'] or '-':<10} "
            f"{r['sample_count']:<8} "
            f"{r['std_dev']:<8.2f}"
        )

    print("=" * 120)


def export_to_sql(results: list[dict], output_file: Path):
    """导出为 SQL 脚本。"""
    with output_file.open('w', encoding='utf-8') as f:
        f.write("-- ============================================================================\n")
        f.write("-- 从 score_diff_to_national 反推的国家线数据\n")
        f.write("-- ============================================================================\n")
        f.write("--\n")
        f.write("-- 生成时间：自动生成\n")
        f.write(f"-- 数据来源：掌上考研 V2 score_diff_to_national 字段\n")
        f.write(f"-- 推导方法：国家线 = 专业线 - score_diff_to_national\n")
        f.write(f"-- 推导结果：{len(results)} 条国家线\n")
        f.write("--\n")
        f.write("-- ⚠️ 重要提示：\n")
        f.write("-- 1. 本数据通过统计推导得出，请与官方国家线对比验证\n")
        f.write("-- 2. 建议从中国研究生招生信息网核验准确性\n")
        f.write("-- 3. 标准差较大的专业门类可能推导不准确\n")
        f.write("--\n")
        f.write("-- ============================================================================\n\n")

        for r in results:
            politics = r['politics_line'] if r['politics_line'] is not None else 'NULL'
            english = r['english_line'] if r['english_line'] is not None else 'NULL'
            subject_one = r['subject_one_line'] if r['subject_one_line'] is not None else 'NULL'
            subject_two = r['subject_two_line'] if r['subject_two_line'] is not None else 'NULL'

            f.write(
                f"-- {r['year']} {r['major_category']} (样本数: {r['sample_count']}, 标准差: {r['std_dev']:.2f})\n"
                f"INSERT INTO score_lines (\n"
                f"    year, line_type, university_id, department_id, major_id,\n"
                f"    major_category, total_score_line,\n"
                f"    politics_line, english_line, subject_one_line, subject_two_line,\n"
                f"    score_diff_to_national, created_at\n"
                f") VALUES (\n"
                f"    {r['year']}, 'national', NULL, NULL, NULL,\n"
                f"    '{r['major_category']}', {r['total_score_line']},\n"
                f"    {politics}, {english}, {subject_one}, {subject_two},\n"
                f"    0, NOW()\n"
                f");\n\n"
            )

    print(f"\n✅ SQL 脚本已导出到: {output_file}")


def main():
    """主函数。"""
    print("开始从 score_diff_to_national 反推国家线...\n")

    results = derive_national_lines()

    print(f"\n成功推导出 {len(results)} 条国家线\n")

    print_results(results)

    # 导出为 SQL
    output_file = Path(__file__).parent.parent / 'sql' / 'mysql' / '004_derived_national_lines.sql'
    export_to_sql(results, output_file)

    # 按年份统计
    print("\n按年份统计：")
    year_counts = defaultdict(int)
    for r in results:
        year_counts[r['year']] += 1

    for year, count in sorted(year_counts.items()):
        print(f"  {year} 年: {count} 个专业门类")

    print("\n请将以上结果与官方国家线对比验证！")
    print("官方渠道：")
    print("  - 中国研究生招生信息网：https://yz.chsi.com.cn/")
    print("  - 中国教育在线：https://yz.eol.cn/")


if __name__ == '__main__':
    main()
