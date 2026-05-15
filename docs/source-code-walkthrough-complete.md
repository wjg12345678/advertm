# AdvertM 源码逐文件导读

这份文档用于把 AdvertM 学到能定位源码的程度。面试问到任务去重、dry-run、Meta API、Catalog/DPA 或图片处理时，优先用这份文档定位文件和函数。

## 1. 阅读路线

推荐顺序：

1. `main.py`
2. `api/ads.py`
3. `api/tasks.py`
4. `services/task_service.py`
5. `dao/task_dao.py`
6. `services/ad_service.py`
7. `services/meta/api.py`
8. `services/meta/targeting.py`
9. `utils/image_store.py`
10. `api/catalog.py`
11. `services/catalog/payload.py`
12. `services/catalog/creation.py`
13. `services/catalog/ad_service.py`

## 2. `main.py`

职责：

- 初始化 SQLite。
- 创建 FastAPI app。
- 配置 CORS。
- 注册 routers。
- 注册统一异常 handler。

关键函数：

- `create_app()`

关键点：

- `init_database()` 在 app 创建时执行。
- `HTTPException` 和 `RequestValidationError` 被转换为统一响应结构。

面试追问：

- 为什么初始化数据库放在 app 创建阶段？
- 生产环境 CORS 为什么不能长期 `["*"]`？

## 3. `core/config.py`

职责：

- 使用 pydantic-settings 读取 `.env` 和环境变量。
- 提供全局 `settings`。

关键配置：

- `fb_ad_dry_run`
- `meta_access_token`
- `meta_ad_account_id`
- `meta_default_page_id`
- `meta_default_currency_multiplier`
- `meta_app_id`
- `meta_app_secret`
- `fb_token_map_path`
- `task_db_path`
- `storage_dir`

面试追问：

- 为什么 token 不能写死？
- dry-run 默认值为什么是 true？

## 4. `core/response.py`

职责：

- 定义 `ApiResponse`。
- 提供 `success()` 和 `failure()`。

所有 API 都尽量返回：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

## 5. `api/ads.py`

接口：

- `POST /fb/ad/create`
- `GET /fb/ad/audience/options`

### `create_facebook_ad()`

流程：

1. 接收 `FacebookAdCreatePayload`。
2. 构造 `TaskSubmitRequest(task_type="fb_ad_create")`。
3. 调 `TaskService.submit_task()`。
4. 返回 task id。

### `get_audience_options()`

流程：

1. 接收 ad account、query、limit。
2. 调 `FacebookAdService.get_audience_options()`。
3. 返回 saved audience + interest 选项。

## 6. `api/tasks.py`

接口：

- `POST /new_bi_api/task/submit`
- `GET /new_bi_api/task/{task_id}`

### `submit_task()`

当前只允许 `task_type="fb_ad_create"`。Catalog 任务通过 `/fb/catalog/create` 提交。

### `get_task()`

根据 task_id 查询任务，不存在返回 404。

## 7. `api/catalog.py`

接口：

- `POST /fb/catalog/validate`
- `POST /fb/catalog/create`
- `GET /fb/catalog/config`

### `validate_catalog_ad()`

调用 `validate_payload()`，有错误返回 failure；没有错误返回 `normalize_payload()` 结果。

### `create_catalog_ad()`

构造 `TaskSubmitRequest(task_type="fb_catalog_ad_create")`，交给 TaskService。

### `catalog_config()`

检测 SDK 是否可用、环境 token 是否存在、token map 路径和可用账号。

## 8. `services/task_service.py`

这是任务系统核心。

### `submit_task()`

流程：

1. `to_dict()` 把 Pydantic model 转 dict。
2. `_payload_hash()` 计算 hash。
3. `TaskDao.find_reusable_task()` 查可复用任务。
4. 命中则返回旧 task id。
5. 未命中则生成 `uuid4().hex`。
6. `TaskDao.create_task()` 插入 pending。
7. `background_tasks.add_task(self._run_task_sync, task_id)`。
8. 返回 task id。

### `_run_task_sync()`

FastAPI BackgroundTasks 调同步 callable，所以这里用 `asyncio.run()` 驱动 async `_run_task()`。

### `_run_task()`

流程：

1. 查 task。
2. 标记 processing。
3. 如果是 `fb_catalog_ad_create`，调用 `create_catalog_ads()`。
4. 否则用 `FacebookAdCreatePayload` 校验 params，再调用 `facebook_ad_service.create_ads()`。
5. 成功 mark_success。
6. MetaAdCreationError mark_fail，并保存 partial result。
7. 普通异常 mark_fail，并保存 traceback。

### `_payload_hash()` 和 `_normalize_for_hash()`

用于请求去重。`image_base64` 会替换为自身 SHA-256。

## 9. `dao/database.py`

职责：

- 创建 SQLite 连接。
- 初始化 `tasks` 表。
- 创建复合索引。
- 对旧表做轻量 migration。

关键点：

- 每次 `get_connection()` 返回新连接。
- `row_factory = sqlite3.Row` 便于转 dict。
- `storage_dir` 不存在会自动创建。

## 10. `dao/task_dao.py`

任务 DAO。

### 基础任务操作

- `create_task()`
- `find_reusable_task()`
- `get_task()`
- `mark_processing()`
- `mark_success()`
- `mark_fail()`

### Meta 对象历史查询

- `find_meta_campaign_ref()`
- `find_meta_adset_ref()`
- `find_meta_ad_ref()`
- `_iter_meta_ref_tasks()`

这些函数通过历史任务的 params/result 查找曾经创建过的 Meta 对象，用于复用和去重。

追问：

- 为什么从历史任务找 campaign/adset？
- 为什么这不是强一致唯一约束？

## 11. `services/ad_service.py`

普通素材广告编排层。

### `create_ads()`

流程：

1. Pydantic payload 转 dict。
2. 计算图片目录 `storage/images/{task_id}`。
3. `persist_payload_images()` 保存 base64 图片。
4. 如果 dry-run，返回 preview。
5. 否则调用 `MetaMarketingApiService.create_ads()`。
6. 如果 MetaAdCreationError，补充 images 和 dry_run 后继续抛出。
7. 成功结果补充 images 和 dry_run。

### `_build_dry_run_result()`

返回预览信息，不调用 Meta。

## 12. `services/meta/api.py`

Meta Graph API 封装。

### `create_ads()`

真实普通素材广告创建主流程：

1. `_ensure_configured()`。
2. 取 campaign、首个 ad_set、首个 ad。
3. `_resolve_ad_account_id()`。
4. `_resolve_page_id()`。
5. `_get_or_create_campaign()`。
6. `_get_or_create_adset()`。
7. `find_meta_ad_ref()` 和 `_find_existing_ad_in_adset()` 防重复。
8. `_create_creative()`。
9. `_create_ad()`。
10. 返回 draft_created。

异常时抛 `MetaAdCreationError`，携带 partial_result。

### Campaign 相关

- `_get_or_create_campaign()`
- `_find_campaign_by_name()`
- `_create_campaign()`

创建时：

- objective: `OUTCOME_TRAFFIC`
- status: `PAUSED`
- buying_type: `AUCTION`

### Ad Set 相关

- `_get_or_create_adset()`
- `_find_adset_by_name()`
- `_create_adset()`

创建时：

- billing event: `IMPRESSIONS`
- optimization goal: `LINK_CLICKS`
- bid strategy: `LOWEST_COST_WITHOUT_CAP`
- destination type: `WEBSITE`
- status: `PAUSED`

### Ad/Creative 相关

- `_find_existing_ad_in_adset()`
- `_create_creative()`
- `_create_ad()`

Creative 使用 link_data object_story_spec，CTA 为 `LEARN_MORE`。

### HTTP helper

- `_post()` 自动附带 access token，检查错误。

### 配置 helper

- `_ensure_configured()`
- `_resolve_ad_account_id()`
- `_resolve_page_id()`
- `_digits()`

## 13. `services/meta/targeting.py`

受众和 targeting。

### `get_audience_options()`

流程：

1. 解析广告账户 ID。
2. `_parse_keywords()` 解析搜索词。
3. `_get_saved_audiences()` 查保存受众。
4. `_search_interests()` 查兴趣。
5. 合并返回 options。

### `build_targeting()`

支持：

- 空 audience：只返回 geo。
- `interest`：构造 flexible_spec。
- `saved_audience`：读取 saved audience targeting，并覆盖 geo。
- `audience_group`：合并 saved audience 和 interests。

## 14. `utils/image_store.py`

职责：

- 遍历 payload 中每个 ad。
- 保存 `image_base64`。
- 记录 `image_url`。
- 支持 data URL。
- 根据 MIME 生成扩展名。
- 文件名包含内容 hash。

关键函数：

- `persist_payload_images()`
- `_save_base64_image()`
- `_extension_for_mime()`

## 15. `schemas/ad.py`

请求模型。

普通素材广告：

- `CampaignPayload`
- `AdSetPayload`
- `AdPayload`
- `FacebookAdCreatePayload`

Catalog/DPA：

- `CatalogAdPayload`
- `CatalogAdSetPayload`
- `CatalogAdCreatePayload`

关键点：

- `AdPayload.ad_copy` 用 alias `"copy"`。
- Catalog schema 使用 `extra="ignore"`，允许前端传入额外字段。
- Catalog 顶层有 OpenAPI example。

## 16. `services/catalog/payload.py`

Catalog payload 校验和标准化。

核心函数：

- `validate_payload()`
- `validate_ads_list()`
- `normalize_payload()`
- `make_mock_result()`

校验点：

- 必填字段。
- adsets/ads 类型。
- budget 正整数。
- 年龄范围。
- countries 类型。
- audience ids 类型。
- link 必须 http/https。

标准化点：

- trim。
- countries uppercase。
- budget/age 转 int。
- ID 去外层引号。
- 过滤空 adset/ad。

## 17. `services/catalog/creation.py`

职责：

- 检测 facebook-business SDK。
- 判断是否 mock。
- 调 `MetaAdService.create_ads()`。
- 捕获 token map 文件缺失和账号缺失，兜底 mock。

追问：

- 为什么 SDK 不可用时返回 mock？
- 生产环境是否应该 mock？

## 18. `services/catalog/ad_service.py`

真实 Catalog/DPA 创建。

关键函数：

- `_load_site_data()`：加载 token map。
- `_init_account()`：初始化 FacebookAdsApi 和 AdAccount。
- `create_product_catalog()`：创建 Product Set，处理 10803 已存在异常。
- `create_catalog_campaign()`：创建销售目标 campaign。
- `create_catalog_adset()`：创建 DPA ad set。
- `create_catalog_ad()`：创建 catalog creative 和 ad。
- `create_ads()`：总编排。

面试重点：

- Product Set 根据 product_group_ids 创建。
- 有 instagram_user_id 时投 Facebook + Instagram。
- 所有对象默认 paused。

## 19. 面试定位表

| 问题 | 文件 | 函数 |
| --- | --- | --- |
| app 怎么初始化 | `main.py` | `create_app` |
| 任务怎么提交 | `api/ads.py` / `api/tasks.py` | `create_facebook_ad` / `submit_task` |
| 任务去重怎么做 | `services/task_service.py` | `submit_task`、`_payload_hash` |
| 任务怎么落库 | `dao/task_dao.py` | `create_task`、`mark_success`、`mark_fail` |
| dry-run 在哪里 | `services/ad_service.py` | `create_ads`、`_build_dry_run_result` |
| Meta 真实创建流程 | `services/meta/api.py` | `create_ads` |
| Campaign 复用 | `services/meta/api.py` | `_get_or_create_campaign` |
| AdSet 复用 | `services/meta/api.py` | `_get_or_create_adset` |
| 广告重复检测 | `services/meta/api.py` | `_find_existing_ad_in_adset` |
| 受众查询 | `services/meta/targeting.py` | `get_audience_options` |
| 图片落盘 | `utils/image_store.py` | `persist_payload_images` |
| Catalog 校验 | `services/catalog/payload.py` | `validate_payload` |
| Catalog 创建 | `services/catalog/ad_service.py` | `create_ads` |

## 20. 最后复盘清单

面试前确认自己能回答：

- 为什么广告创建要任务化。
- BackgroundTasks 的边界是什么。
- payload hash 如何保证重复请求复用。
- 为什么 image_base64 要先 hash。
- dry-run 为什么默认开启。
- Meta 创建链路为什么默认 PAUSED。
- Campaign/AdSet 复用怎么做。
- partial failure 为什么重要。
- Catalog/DPA 和普通素材广告有什么区别。
- SQLite 多实例有什么问题。
- 生产中如何替换成真正任务队列。
