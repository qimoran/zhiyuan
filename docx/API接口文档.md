# 考研择校推荐系统 API 接口文档

## 文档信息

| 项目 | 内容 |
|------|------|
| 文档版本 | V1.0 |
| 编写日期 | 2026-06-16 |
| 适用版本 | S08 基础 API + S09 分数线评估 |
| 基础 URL | `http://127.0.0.1:5000` |

---

## 通用说明

### 统一响应格式

所有接口返回格式一致：

```json
{
  "code": 0,                      // 0: 成功，非 0: 失败
  "message": "success",           // 响应消息
  "trace_id": "202606161626...",  // 请求追踪 ID
  "data": {}                      // 响应数据
}
```

### 错误响应

```json
{
  "code": 40001,
  "message": "参数校验失败：university_id 必须是正整数",
  "trace_id": "202606161626...",
  "data": null
}
```

### 分页参数

支持分页的接口通用参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `limit` | int | 否 | 50 | 返回条数，最大 200 |
| `offset` | int | 否 | 0 | 跳过条数 |

分页响应格式：

```json
{
  "items": [...],
  "total": 100,
  "limit": 50,
  "offset": 0,
  "has_more": true
}
```

---

## 接口列表

### 1. 系统健康检查

**接口地址**：`GET /api/health`

**功能描述**：返回系统运行状态和数据库连通性，用于监控和运维。

**请求参数**：无

**响应示例**：

```json
{
  "code": 0,
  "message": "success",
  "trace_id": "202606161626...",
  "data": {
    "status": "ok",
    "database": "ok",
    "detail": {
      "universities": 21,
      "majors": 5652,
      "enrollment_plans": 10035,
      "score_lines": 6610,
      "source_documents": 21
    }
  }
}
```

**响应字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 系统状态（固定返回 "ok"） |
| `database` | string | 数据库状态（"ok" / "unavailable"） |
| `detail.universities` | int | 招生单位数量 |
| `detail.majors` | int | 专业数量 |
| `detail.enrollment_plans` | int | 招生计划数量 |
| `detail.score_lines` | int | 分数线数量 |
| `detail.source_documents` | int | 来源资料数量 |

---

### 2. 招生单位列表

**接口地址**：`GET /api/university/list`

**功能描述**：查询重庆地区研招单位候选库，支持分页、筛选和关键词搜索。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `limit` | int | 否 | 返回条数，默认 50，最大 200 |
| `offset` | int | 否 | 跳过条数，默认 0 |
| `coverage_priority` | string | 否 | 优先级筛选（P0/P1/P2/P3） |
| `school_type` | string | 否 | 学校类型（综合类/理工类/医药类/师范类/艺术类等） |
| `school_org_type` | string | 否 | 机构类型（高等院校/科研院所） |
| `official_verified_status` | string | 否 | 官网核验状态（pending/verified/mismatch） |
| `keyword` | string | 否 | 关键词搜索（学校名称模糊匹配） |

**coverage_priority 说明**：

- `P0`：985/211/双一流重点高校
- `P1`：211/双一流高校
- `P2`：普通院校
- `P3`：科研机构

**请求示例**：

```bash
# 查询所有学校（默认分页）
GET /api/university/list

# 查询 P0 优先级学校
GET /api/university/list?coverage_priority=P0

# 关键词搜索
GET /api/university/list?keyword=重庆大学

# 分页查询
GET /api/university/list?limit=10&offset=0
```

**响应示例**：

```json
{
  "code": 0,
  "message": "success",
  "trace_id": "202606161626...",
  "data": {
    "items": [
      {
        "id": 1,
        "candidate_school_id": 252,
        "university_name": "重庆大学",
        "province": "重庆",
        "city": "重庆市",
        "province_area": "A区",
        "school_type": "综合类",
        "school_org_type": "高等院校",
        "school_level": "985 / 211 / 双一流 / 自划线",
        "coverage_priority": "P0",
        "official_verified_status": "pending",
        "recruit_number_reference": 5985,
        "major_number_reference": 86,
        "candidate_source_url": "https://www.kaoyan.cn/school-list/50-0-0",
        "remark": "掌上考研候选库初始化；软科/第三方排名参考：34"
      }
    ],
    "total": 21,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 3. 专业列表

**接口地址**：`GET /api/major/list`

**功能描述**：查询研究生招生专业目录，支持按学校、年份、专业门类、学位类型、学习方式等多维度筛选。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `limit` | int | 否 | 返回条数，默认 50，最大 200 |
| `offset` | int | 否 | 跳过条数，默认 0 |
| `university_id` | int | 否 | 学校 ID（数据库主键） |
| `school_id` | int | 否 | 候选学校 ID（掌上考研 school_id） |
| `year` | int | 否 | 招生年份（2024/2025/2026）<br>**注意**：指定 year 会只返回该年份有招生计划的专业 |
| `major_category` | string | 否 | 专业门类 |
| `major_code` | string | 否 | 专业代码（6 位，如 081200） |
| `degree_type` | string | 否 | 学位类型（academic/professional） |
| `study_mode` | string | 否 | 学习方式（full_time/part_time） |
| `keyword` | string | 否 | 关键词搜索（专业名称或研究方向模糊匹配） |

**专业门类枚举**：

哲学、经济学、法学、教育学、文学、历史学、理学、工学、农学、医学、军事学、管理学、艺术学、交叉学科

**学位类型枚举**：

- `academic`：学术学位（学硕）
- `professional`：专业学位（专硕）

**学习方式枚举**：

- `full_time`：全日制
- `part_time`：非全日制

**请求示例**：

```bash
# 查询重庆大学的所有专业
GET /api/major/list?school_id=252

# 查询 2026 年电子信息类全日制专硕
GET /api/major/list?year=2026&major_category=电子信息&degree_type=professional&study_mode=full_time

# 关键词搜索计算机相关专业
GET /api/major/list?keyword=计算机

# 分页查询
GET /api/major/list?limit=20&offset=0
```

**响应示例**：

```json
{
  "code": 0,
  "message": "success",
  "trace_id": "202606161626...",
  "data": {
    "items": [
      {
        "id": 104,
        "university_id": 1,
        "candidate_school_id": 252,
        "university_name": "重庆大学",
        "department_id": 1,
        "department_name": "人文社会科学高等研究院",
        "major_code": "010100",
        "major_name": "哲学",
        "major_category": "哲学",
        "degree_type": "academic",
        "study_mode": "full_time",
        "research_direction": "（01）中国哲学",
        "exam_subjects": "①(101)思想政治理论 ②(201)英语（一） ③(656)哲学综合 ④(880)写作",
        "updated_at": "2026-06-16T15:53:46"
      }
    ],
    "total": 594,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

---

### 4. 来源资料列表

**接口地址**：`GET /api/source/list`

**功能描述**：查询数据来源资料索引，包括掌上考研候选数据、学校官网 PDF、Excel 等原始资料的登记记录。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `limit` | int | 否 | 返回条数，默认 50，最大 200 |
| `offset` | int | 否 | 跳过条数，默认 0 |
| `university_id` | int | 否 | 学校 ID（数据库主键） |
| `school_id` | int | 否 | 候选学校 ID（掌上考研 school_id） |
| `year` | int | 否 | 资料年份（2024/2025/2026） |
| `document_type` | string | 否 | 资料类型 |
| `process_status` | string | 否 | 处理状态 |

**document_type 枚举**：

- `school_list`：学校候选库（掌上考研）
- `plan_list`：招生计划（掌上考研）
- `plan_detail`：专业详情（掌上考研）
- `score_line`：分数线（掌上考研）
- `level_rate`：学科评估（掌上考研）
- `official_plan`：招生专业目录（官网 PDF/Excel）
- `official_score`：复试线公告（官网 PDF/Excel）
- `official_admission`：拟录取名单（官网 PDF/Excel）

**process_status 枚举**：

- `pending`：待处理
- `loaded`：已入库
- `verified`：已核验
- `error`：处理失败

**请求示例**：

```bash
# 查询重庆大学的所有来源资料
GET /api/source/list?school_id=252

# 查询掌上考研候选库来源
GET /api/source/list?document_type=school_list

# 查询已入库的资料
GET /api/source/list?process_status=loaded

# 查询 2026 年官网招生目录
GET /api/source/list?year=2026&document_type=official_plan
```

**响应示例**：

```json
{
  "code": 0,
  "message": "success",
  "trace_id": "202606161626...",
  "data": {
    "items": [
      {
        "id": 1,
        "university_id": 1,
        "candidate_school_id": 252,
        "university_name": "重庆大学",
        "year": null,
        "document_type": "school_list",
        "document_title": "掌上考研 V2 学校候选库",
        "source_url": "https://www.kaoyan.cn/school-list/50-0-0",
        "local_path": null,
        "published_date": null,
        "collector": "kaoyan_v2_crawler",
        "collected_at": "2026-06-16T14:58:00",
        "process_status": "loaded",
        "official_verified": false,
        "remark": "掌上考研 V2 API schoolList 批次 20260616_full_v2"
      }
    ],
    "total": 21,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

---

### 5. 分数线评估（S09）

**接口地址**：`POST /api/score/evaluate`

**功能描述**：根据用户初试成绩评估相对国家线、院校线、专业线的状况，判断总分和单科风险等级。

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `target_year` | int | 是 | 目标年份（2024/2025/2026） |
| `major_category` | string | 是 | 专业门类 |
| `major_name` | string | 否 | 专业名称（用于精确匹配专业线） |
| `university_id` | int | 否 | 学校 ID（用于查询院校线） |
| `total_score` | int | 是 | 总分（0-500） |
| `politics_score` | int | 是 | 政治/综合科目分数（0-150） |
| `english_score` | int | 是 | 英语分数（0-150） |
| `subject_one_score` | int | 是 | 业务课一分数（0-150） |
| `subject_two_score` | int | 是 | 业务课二分数（0-150） |

**请求示例**：

```bash
POST /api/score/evaluate
Content-Type: application/json

{
  "target_year": 2026,
  "major_category": "电子信息",
  "major_name": "计算机技术",
  "total_score": 355,
  "politics_score": 68,
  "english_score": 72,
  "subject_one_score": 105,
  "subject_two_score": 110
}
```

**响应示例**：

```json
{
  "code": 0,
  "message": "success",
  "trace_id": "202606161626...",
  "data": {
    "total_score_status": "safe",
    "single_subject_status": "safe",
    "line_type": "major",
    "line_detail": {
      "total_score_line": 310,
      "politics_line": 50,
      "english_line": 50,
      "subject_one_line": 75,
      "subject_two_line": 75
    },
    "diff": {
      "total_diff": 45,
      "politics_diff": 18,
      "english_diff": 22,
      "subject_one_diff": 30,
      "subject_two_diff": 35
    },
    "warnings": [],
    "suggestions": [
      "总分和单科均超过分数线，建议冲刺该专业"
    ]
  }
}
```

**响应字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_score_status` | string | 总分状态（unsafe/warning/safe） |
| `single_subject_status` | string | 单科状态（unsafe/warning/safe） |
| `line_type` | string | 使用的分数线类型（national/university/major） |
| `line_detail` | object | 分数线详情 |
| `diff` | object | 分数差（用户分数 - 分数线） |
| `warnings` | array | 风险提示列表 |
| `suggestions` | array | 建议列表 |

**status 枚举说明**：

- `unsafe`：不达线，风险高
- `warning`：压线或刚过线，风险中等
- `safe`：超过分数线较多，风险低

---

## 错误码说明

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 40001 | 参数校验失败 |
| 40002 | 数据不存在 |
| 50000 | 系统异常 |

---

## 测试工具

### 使用 curl 测试

```bash
# 健康检查
curl http://127.0.0.1:5000/api/health

# 招生单位列表
curl "http://127.0.0.1:5000/api/university/list?limit=5"

# 专业列表（重庆大学）
curl "http://127.0.0.1:5000/api/major/list?school_id=252&limit=5"

# 分数线评估
curl -X POST http://127.0.0.1:5000/api/score/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "target_year": 2026,
    "major_category": "电子信息",
    "total_score": 355,
    "politics_score": 68,
    "english_score": 72,
    "subject_one_score": 105,
    "subject_two_score": 110
  }'
```

### 使用 PowerShell 测试

```powershell
# 健康检查
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/health" -Method Get

# 招生单位列表
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/university/list?limit=5" -Method Get

# 专业列表（重庆大学）
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/major/list?school_id=252&limit=5" -Method Get

# 分数线评估
$body = @{
    target_year = 2026
    major_category = "电子信息"
    total_score = 355
    politics_score = 68
    english_score = 72
    subject_one_score = 105
    subject_two_score = 110
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/score/evaluate" -Method Post -ContentType "application/json" -Body $body
```

---

## 更新日志

| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 | 2026-06-16 | 初版发布，包含 S08 基础 API 和 S09 分数线评估接口 |

---

## 联系方式

如有问题或建议，请联系项目组。
