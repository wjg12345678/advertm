# AdvertM 项目学习指南

这份文档用于把 AdvertM 学成一个能写进简历、能讲清业务链路、能回答工程追问的后端项目。它不是简单调用 Meta API 的 demo，而是围绕“广告创建任务”做了请求校验、异步任务、任务去重、SQLite 持久化、dry-run 预览、Meta Graph API 编排、Catalog/DPA 商品目录广告、受众查询和本地图片落盘。

## 1. 项目定位

AdvertM 是一个基于 FastAPI 的 Meta/Facebook 广告后端服务，核心能力包括：

- 提交通用广告创建任务。
- 查询异步任务状态。
- 普通素材广告 dry-run 预览。
- 关闭 dry-run 后调用 Meta Graph API 创建 Campaign、Ad Set、Creative、Ad。
- 支持按名称复用 Campaign / Ad Set。
- 支持同一 Ad Set 下广告名重复检测。
- 保存任务参数、结果、错误和 traceback 到 SQLite。
- 基于 payload hash 对相同任务做去重。
- 查询 Saved Audience 和兴趣受众。
- Catalog/DPA 商品目录广告 payload 校验、标准化和创建。
- SDK 或授权不可用时返回 mock 结果，便于前后端联调。
- Base64 图片保存到本地 `storage/images/{task_id}`。

面试时可以这样介绍：

> AdvertM 是我实现的 Meta/Facebook 广告创建后端服务。它用 FastAPI 提供广告创建、任务查询、受众查询和 Catalog/DPA 接口；任务层通过 SQLite 持久化状态，并用标准化 payload 的 SHA-256 hash 做请求去重；普通素材广告支持 dry-run 预览和真实 Meta Graph API 创建；Catalog/DPA 支持 payload 校验、Product Set 创建和 SDK 不可用时的 mock 兜底。项目重点不是单次 API 调用，而是把广告创建任务做成可追踪、可复用、可排错的后端流程。

## 2. 技术栈

- Python 3.10+
- FastAPI
- Pydantic / pydantic-settings
- SQLite
- httpx
- Meta Graph API
- facebook-business SDK，可选
- Uvicorn

## 3. 架构概览

```text
Client / Admin Frontend
  |
  v
FastAPI Routes
  |
  +--> /fb/ad/create
  +--> /fb/ad/audience/options
  +--> /fb/catalog/validate
  +--> /fb/catalog/create
  +--> /new_bi_api/task/submit
  +--> /new_bi_api/task/{task_id}
  |
  v
TaskService
  |
  +--> TaskDao / SQLite
  +--> FacebookAdService
  |     |
  |     +--> MetaMarketingApiService
  |     +--> TargetingBuilder
  |     +--> ImageStore
  |
  +--> catalog.creation.create_ads
        |
        +--> MetaAdService / facebook-business SDK
        +--> mock result fallback
```

## 4. 仓库结构

```text
api/
  ads.py                      普通素材广告和受众接口
  catalog.py                  Catalog/DPA 校验、创建和配置状态接口
  health.py                   健康检查
  tasks.py                    通用任务提交和查询接口

core/
  config.py                   pydantic-settings 环境变量配置
  response.py                 统一响应结构

dao/
  database.py                 SQLite 初始化和连接
  task_dao.py                 任务 CRUD、任务去重、历史 Meta 对象查询

schemas/
  ad.py                       普通素材广告和 Catalog/DPA 请求模型
  task.py                     通用任务请求模型

services/
  task_service.py             任务生命周期、去重、后台执行、失败落库
  ad_service.py               普通素材广告编排
  meta/
    api.py                    Meta Graph API 创建 Campaign/AdSet/Creative/Ad
    targeting.py              受众解析、兴趣搜索、targeting 构建
    constants.py              常量和 MetaAdCreationError
  catalog/
    payload.py                Catalog payload 校验、标准化、mock result
    creation.py               SDK 可用性检测和 mock 兜底
    ad_service.py             facebook-business SDK 创建 Catalog/DPA

utils/
  helpers.py                  Pydantic model 转 dict、JSON dump
  image_store.py              Base64 图片落盘

main.py                       FastAPI app 入口
```

## 5. 重要运行方式

当前源码使用 `from app.xxx import ...`，因此运行时父目录下需要有 `app` 包。推荐部署时把仓库目录命名为 `app`：

```bash
cd /path/to/workspace
git clone https://github.com/wjg12345678/advertm.git app
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7790 --reload
```

如果目录名不是 `app`，会遇到 `ModuleNotFoundError: No module named 'app'`。这是项目当前包名约束，面试时要知道原因。

## 6. 统一响应结构

`core/response.py` 定义：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

路由层通过 `success()` 和 `failure()` 返回统一结构。`main.py` 中还注册了：

- `HTTPException` handler
- `RequestValidationError` handler

这样框架异常也会被转换成统一响应格式。

## 7. 任务系统

AdvertM 的核心不是同步创建广告，而是任务化：

1. 客户端提交广告创建请求。
2. `TaskService.submit_task()` 标准化参数并计算 hash。
3. 如果同类型、同 hash 的任务已存在且状态可复用，直接返回已有 task id。
4. 否则创建新任务，状态为 `pending`。
5. FastAPI `BackgroundTasks` 后台执行 `_run_task_sync()`。
6. `_run_task()` 把任务改为 `processing`。
7. 执行业务创建逻辑。
8. 成功则 `success`，失败则 `fail` 并保存错误和 traceback。

任务状态：

- `pending`
- `processing`
- `success`
- `fail`

## 8. 请求去重

去重逻辑在 `TaskService._payload_hash()`。

标准化规则：

- dict 递归标准化。
- list 保持顺序递归标准化。
- string 去掉首尾空格。
- `image_base64` 不直接参与 hash，而是先计算 SHA-256 摘要。
- JSON dump 使用 `sort_keys=True`。

这样能避免：

- 同样请求重复创建广告。
- base64 大字段让 hash 原始串过长。
- 字典 key 顺序不同导致 hash 不一致。

边界：

- list 顺序仍然影响 hash。
- 去重只复用 `pending/processing/success`，失败任务不会复用。
- 这不是完整业务幂等表，但适合广告创建任务去重。

## 9. SQLite 任务持久化

`dao/database.py` 初始化：

- `tasks` 表。
- `idx_tasks_type_hash_status` 索引。
- 轻量 migration：如果旧表没有 `payload_hash`，自动 `ALTER TABLE`。

`tasks` 字段：

- `task_id`
- `task_type`
- `status`
- `payload_hash`
- `params`
- `result`
- `error`
- `created_at`
- `updated_at`
- `finished_at`

面试重点：

- SQLite 适合单机轻量任务队列和本地开发。
- 多实例部署时 SQLite 不合适，应该换成 PostgreSQL/MySQL + 任务队列。

## 10. 普通素材广告 dry-run

默认 `FB_AD_DRY_RUN=true`。

`FacebookAdService.create_ads()`：

1. 把 Pydantic payload 转成 dict。
2. 保存 base64 图片。
3. 如果 dry-run，返回 `_build_dry_run_result()`。
4. 不调用 Meta API。

dry-run 返回：

- task id
- campaign name
- ad set count
- ad count
- image records
- preview payload
- next step 提示

价值：

- 前后端可以先联调请求结构。
- 不会误创建真实广告。
- 面试中可以说这是外部系统集成的安全默认值。

## 11. 真实普通素材广告创建

关闭 dry-run 后，`MetaMarketingApiService.create_ads()` 执行：

1. 校验 Meta 配置。
2. 取第一个 ad set 和第一个 ad。
3. 解析广告账户 ID 和 Page ID。
4. 查找或创建 Campaign。
5. 查找或创建 Ad Set。
6. 检查同 Ad Set 下是否已有同名 Ad。
7. 创建 Creative。
8. 创建 Ad。
9. 所有对象默认 `PAUSED`。

注意当前边界：

- 普通素材广告当前只处理第一个 ad set 和第一个 ad。
- 真实创建涉及外部 API，部分成功后失败可能产生半成品对象。
- `MetaAdCreationError` 会携带 partial result，便于落库排查。

## 12. Campaign / Ad Set 复用

复用逻辑分两层：

1. 先查本地历史任务结果。
2. 再查 Meta API。
3. 都没有才创建。

本地查询在 `TaskDao`：

- `find_meta_campaign_ref()`
- `find_meta_adset_ref()`
- `find_meta_ad_ref()`

好处：

- 减少重复创建。
- 加快后续请求。
- 即使 Meta 查询较慢，也能先利用本地历史结果。

## 13. 重复广告检测

在创建 Ad 前，服务会检查同一 account + adset 下是否已有同名广告：

- 先查本地历史任务。
- 再查 Meta API。
- 如果存在，返回 `duplicate_prevented`，不再创建新 ad。

面试重点：

- 这是业务层的防重复，不是数据库唯一索引。
- 外部系统和本地历史都要考虑。

## 14. 受众查询和 targeting

`TargetingBuilder` 负责：

- 查询 saved audiences。
- 搜索 Meta interests。
- 解析中文/英文关键词。
- 把中文兴趣名映射成英文。
- 组装 targeting spec。

支持 audience 类型：

- `interest`
- `saved_audience`
- `audience_group`

`audience_group` 可以把 saved audience 和多个 interest 组合。

## 15. 图片处理

`utils/image_store.py`：

- 支持普通 base64。
- 支持 data URL。
- 根据 MIME 推断扩展名。
- 用图片内容 SHA-256 前 12 位作为文件名一部分。
- 保存到 `storage/images/{task_id}`。

`image_url` 不下载，只记录 URL。

面试追问：

- 为什么 base64 不直接参与 payload hash？
- 为什么文件名要带内容 hash？

## 16. Catalog/DPA payload 校验

`services/catalog/payload.py` 做：

- 必填字段检查。
- adsets 必须是 list。
- ads 必须是 list。
- budget 必须是正整数。
- 年龄必须大于等于 13。
- age_min 不能大于 age_max。
- countries/custom_audience_ids/interest_ids 类型检查。
- link 必须 http/https。
- 空 adset / 空 ad 可以跳过。

标准化：

- 去首尾空格。
- countries 转大写。
- budget/age 转 int。
- 清理 ID 外层引号。
- 过滤空 ad。

## 17. Catalog/DPA 创建

`services/catalog/creation.py`：

- 检测 `facebook-business` SDK 是否安装。
- 如果 `mock_mode=true` 或 SDK 不可用，返回 mock result。
- 如果 SDK 可用，调用 `MetaAdService.create_ads()`。
- token map 缺失或账号授权缺失时也兜底 mock。

`MetaAdService` 真实创建：

1. 初始化广告账户。
2. 创建 Catalog Campaign。
3. 创建 Catalog Ad Set。
4. 为每个 ad 的 product_group_ids 创建 Product Set。
5. 创建 Catalog Creative。
6. 创建 Ad。

投放位：

- 没有 instagram_user_id：Facebook only。
- 有 instagram_user_id：Facebook + Instagram。

## 18. 配置和安全

重要环境变量：

- `FB_AD_DRY_RUN`
- `META_ACCESS_TOKEN`
- `META_AD_ACCOUNT_ID`
- `META_DEFAULT_PAGE_ID`
- `META_DEFAULT_PIXEL_ID`
- `META_APP_ID`
- `META_APP_SECRET`
- `FB_TOKEN_MAP_PATH`
- `TASK_DB_PATH`
- `STORAGE_DIR`

安全边界：

- 不要提交 `.env`。
- 不要提交 token map。
- `storage/tasks.sqlite3` 可能包含完整请求和错误信息，不应公开。
- 生产环境不要长期 `CORS_ORIGINS=["*"]`。
- token 要最小权限和定期轮换。

## 19. 生产化边界

必须主动承认：

- 当前使用 FastAPI `BackgroundTasks`，适合轻量后台任务，不适合长时间或大规模任务队列。
- SQLite 不适合多实例并发写和横向扩展。
- 没有登录鉴权、租户隔离和权限系统。
- 没有完整审计、告警和 Prometheus 指标。
- Meta API 部分成功后失败只能记录 partial result，还没有自动补偿。
- 普通素材广告当前只处理第一个 ad set 和第一个 ad。
- Catalog/DPA mock 兜底适合联调，但生产中要明确失败还是 mock。
- 没有系统化自动测试。

## 20. 学习路线

第一阶段：跑通和理解接口。

1. 从父目录启动 `python3 -m uvicorn app.main:app`。
2. 访问 `/docs`。
3. dry-run 提交 `/fb/ad/create`。
4. 查询 `/new_bi_api/task/{task_id}`。
5. 调 `/fb/catalog/validate`。

第二阶段：读任务链路。

1. `api/ads.py`
2. `api/tasks.py`
3. `services/task_service.py`
4. `dao/task_dao.py`
5. `dao/database.py`

第三阶段：读 Meta 创建链路。

1. `services/ad_service.py`
2. `services/meta/api.py`
3. `services/meta/targeting.py`
4. `utils/image_store.py`

第四阶段：读 Catalog/DPA。

1. `api/catalog.py`
2. `schemas/ad.py` 中 Catalog schemas。
3. `services/catalog/payload.py`
4. `services/catalog/creation.py`
5. `services/catalog/ad_service.py`

## 21. 简历写法

推荐 3 条：

- 基于 FastAPI 实现 Meta/Facebook 广告创建后端，支持普通素材广告 dry-run 预览、真实 Graph API 创建、受众选项查询、Catalog/DPA payload 校验和商品目录广告创建。
- 设计 SQLite 持久化的异步任务系统，支持任务状态流转、请求参数落库、结果/错误/traceback 保存，并通过标准化 payload SHA-256 hash 复用重复任务。
- 封装 Meta Marketing API 编排逻辑，支持 Campaign/Ad Set 本地历史与远端查询复用、同 Ad Set 下广告名重复检测、base64 图片本地落盘和 partial failure 结果保留。

## 22. 面试一句话

> AdvertM 的重点是把 Meta 广告创建从一次性 API 调用升级成可追踪的任务系统：请求校验、dry-run、防重复、任务落库、后台执行、Meta 对象复用、失败 partial result、Catalog/DPA mock 兜底和生产安全边界都考虑到了。
