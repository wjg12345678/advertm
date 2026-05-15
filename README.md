# AdvertM

AdvertM 是一个基于 FastAPI 的 Meta/Facebook 广告后端服务，主要用于提交广告创建任务、查询异步任务状态、预览或创建普通素材广告，以及校验和创建 Catalog/DPA 商品目录广告。

项目默认以 dry-run 方式运行，便于先验证请求结构、任务流程和本地落库结果；配置 Meta 授权并关闭 dry-run 后，普通素材广告会调用 Meta Graph API 创建处于 `PAUSED` 状态的 Campaign、Ad Set、Creative 和 Ad。

## 功能概览

- FastAPI HTTP API，自动提供 OpenAPI 文档。
- 统一响应结构：`code`、`message`、`data`。
- 异步任务提交和状态查询，任务持久化到 SQLite。
- 请求去重：相同 `task_type` 和相同参数 hash 的任务会复用已有任务。
- 普通素材广告创建：
  - 默认 dry-run，只返回预览，不调用 Meta API。
  - 支持 Campaign、Ad Set、Ad 层级参数。
  - 支持按名称复用已有 Campaign / Ad Set。
  - 支持同一 Ad Set 下广告名重复检测。
  - Meta 实际创建对象默认均为 `PAUSED`。
- 受众选项查询：
  - 支持查询 Saved Audience。
  - 支持按中文或英文关键词搜索兴趣。
- Catalog/DPA 商品目录广告：
  - 支持 payload 校验和标准化。
  - 支持按商品组创建 Product Set。
  - 支持 Facebook-only 或 Facebook + Instagram 投放位。
  - SDK 或授权不可用时可返回 mock 结果，方便联调。
- Base64 图片会保存到本地 `storage/images/{task_id}`。

## 技术栈

- Python 3.10+
- FastAPI
- Pydantic / pydantic-settings
- httpx
- SQLite
- facebook-business SDK，可选，仅真实创建 Catalog/DPA 广告时需要

## 项目结构

```text
app/
├── api/                    # FastAPI 路由
│   ├── ads.py              # 普通素材广告接口
│   ├── catalog.py          # Catalog/DPA 广告接口
│   ├── health.py           # 健康检查
│   └── tasks.py            # 异步任务接口
├── core/
│   ├── config.py           # 环境变量配置
│   └── response.py         # 统一响应结构
├── dao/
│   ├── database.py         # SQLite 初始化和连接
│   └── task_dao.py         # 任务读写和历史 Meta 对象查询
├── schemas/
│   ├── ad.py               # 广告请求模型
│   └── task.py             # 任务请求模型
├── services/
│   ├── ad_service.py       # 普通素材广告编排
│   ├── task_service.py     # 任务生命周期管理
│   ├── catalog/            # Catalog/DPA 创建逻辑
│   └── meta/               # Meta Graph API 封装和受众逻辑
├── utils/
│   ├── helpers.py
│   └── image_store.py
└── main.py                 # FastAPI 应用入口
```

## 重要运行说明

当前源码使用 `from app.xxx import ...` 作为包导入路径，因此运行时需要让源码目录以 `app` 包名存在。

推荐克隆方式：

```bash
cd /path/to/workspace
git clone https://github.com/wjg12345678/advertm.git app
cd app
```

如果你已经在本机当前项目目录 `/Users/mac/Desktop/app`，保持这个目录名即可。启动服务时建议从父目录执行：

```bash
cd /Users/mac/Desktop
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7790 --reload
```

如果目录不是 `app`，会出现 `ModuleNotFoundError: No module named 'app'`。这种情况下请将目录改名为 `app`，或在部署时保持父目录下存在 `app` 包目录。

## 安装依赖

项目当前没有独立的依赖清单文件，可以先按源码使用到的依赖安装：

```bash
cd /path/to/workspace/app
python3 -m venv .venv
source .venv/bin/activate

pip install fastapi "uvicorn[standard]" pydantic pydantic-settings httpx
```

如果需要真实创建 Catalog/DPA 广告，再安装 Meta SDK：

```bash
pip install facebook-business
```

## 环境变量

服务通过 `.env` 或系统环境变量读取配置。`.env` 文件不要提交到 Git。

```env
# application
APP_NAME="Facebook Ad Backend (Material + Catalog)"
APP_HOST=0.0.0.0
APP_PORT=7790
CORS_ORIGINS='["*"]'

# storage
STORAGE_DIR=storage
TASK_DB_PATH=storage/tasks.sqlite3

# material ad creation
FB_AD_DRY_RUN=true
META_API_VERSION=v21.0
META_ACCESS_TOKEN=
META_AD_ACCOUNT_ID=
META_DEFAULT_PAGE_ID=
META_DEFAULT_PIXEL_ID=
META_DEFAULT_CURRENCY_MULTIPLIER=100

# catalog ad creation
META_APP_ID=
META_APP_SECRET=
FB_TOKEN_MAP_PATH=
```

配置说明：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_NAME` | `Facebook Ad Backend (Material + Catalog)` | 服务名，健康检查和 OpenAPI 中使用 |
| `APP_HOST` | `0.0.0.0` | 建议启动命令显式传入 |
| `APP_PORT` | `7790` | 建议启动命令显式传入 |
| `CORS_ORIGINS` | `["*"]` | CORS 白名单，环境变量中建议使用 JSON 数组字符串 |
| `STORAGE_DIR` | `storage` | 图片和运行时文件目录 |
| `TASK_DB_PATH` | `storage/tasks.sqlite3` | SQLite 任务库路径 |
| `FB_AD_DRY_RUN` | `true` | 普通素材广告是否只预览不调用 Meta API |
| `META_API_VERSION` | `v21.0` | Meta Graph API 版本 |
| `META_ACCESS_TOKEN` | 空 | Meta API access token |
| `META_AD_ACCOUNT_ID` | 空 | 默认广告账户 ID，可写 `act_123` 或纯数字 |
| `META_DEFAULT_PAGE_ID` | 空 | 默认 Facebook Page ID |
| `META_DEFAULT_PIXEL_ID` | 空 | 默认 Pixel ID，部分请求仍可在 payload 中覆盖 |
| `META_DEFAULT_CURRENCY_MULTIPLIER` | `100` | 普通素材广告预算单位换算，例如美元到美分 |
| `META_APP_ID` | 空 | Catalog/DPA SDK 初始化所需 App ID |
| `META_APP_SECRET` | 空 | Catalog/DPA SDK 初始化所需 App Secret |
| `FB_TOKEN_MAP_PATH` | 空 | 多广告账户 token map JSON 文件路径 |

Catalog/DPA 可以使用 token map 管理多个广告账户：

```json
{
  "act_1234567890": {
    "app_id": "your_meta_app_id",
    "app_secret": "your_meta_app_secret",
    "access_token": "your_meta_access_token"
  }
}
```

如果设置了 `META_ACCESS_TOKEN`，Catalog/DPA 服务也可以用环境变量中的 `META_APP_ID`、`META_APP_SECRET`、`META_ACCESS_TOKEN` 作为兜底授权。

## 启动服务

从源码父目录启动：

```bash
cd /path/to/workspace
source app/.venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7790 --reload
```

启动后访问：

- API 文档：`http://127.0.0.1:7790/docs`
- 健康检查：`http://127.0.0.1:7790/health`
- 兼容健康检查：`http://127.0.0.1:7790/new_bi_api/health`

## API 响应格式

成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

失败响应：

```json
{
  "code": 400,
  "message": "参数校验失败",
  "data": []
}
```

## 健康检查

```bash
curl http://127.0.0.1:7790/health
```

示例响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "service": "Facebook Ad Backend (Material + Catalog)",
    "dry_run": true
  }
}
```

## 普通素材广告

### 创建广告任务

接口：

```http
POST /fb/ad/create
```

示例：

```bash
curl -X POST "http://127.0.0.1:7790/fb/ad/create" \
  -H "Content-Type: application/json" \
  -d '{
    "campaign": {
      "name": "2026-US-Lighting-Traffic",
      "site": "example.com",
      "ad_account": "act_1234567890",
      "date": "2026-05-15",
      "page_id": "123456789012345"
    },
    "ad_sets": [
      {
        "name": "US-Interior-Design-25-45",
        "pixel_id": "123456789012345",
        "budget": 10,
        "country": "US",
        "audience": {
          "type": "interest",
          "id": "6003139266461",
          "name": "Interior design"
        },
        "schedule": "2026-05-15",
        "ads": [
          {
            "name": "Fabric Ambient Wall Lamps",
            "link": "https://www.example.com/products/wall-lamp",
            "copy": "Transform your home with soft, calming illumination.",
            "title": "Ambient Wall Lamps",
            "description": "Layered ambient lighting for bedrooms and lounges.",
            "image_url": "https://www.example.com/images/wall-lamp.jpg"
          }
        ]
      }
    ]
  }'
```

返回：

```json
{
  "code": 200,
  "message": "任务提交成功",
  "data": {
    "task_id": "3f8e0f9f5c3f4c0da8c2c0f2e8b9a111"
  }
}
```

注意：

- `FB_AD_DRY_RUN=true` 时，只会保存任务并返回预览，不调用 Meta API。
- `FB_AD_DRY_RUN=false` 时，需要配置 `META_ACCESS_TOKEN`、`META_AD_ACCOUNT_ID`，并提供可解析的 Page ID。
- 真实创建时，Campaign、Ad Set、Ad 都以 `PAUSED` 状态创建，不会自动发布。
- 代码当前每次普通素材广告创建流程会处理第一个 ad set 和第一个 ad。
- `copy` 是请求字段名，内部会映射为广告正文。

### 查询受众选项

接口：

```http
GET /fb/ad/audience/options
```

示例：

```bash
curl "http://127.0.0.1:7790/fb/ad/audience/options?ad_account_id=act_1234567890&query=室内设计,灯具&limit=20"
```

返回的 `options` 中包含两类数据：

- `saved_audience`：广告账户中的保存受众。
- `interest`：Meta 兴趣搜索结果。

`query` 支持中文逗号、顿号、英文逗号和“或”作为分隔符。空查询会使用默认兴趣关键词：`Light fixture`、`Interior design`、`Home decor`、`Home improvement`。

## Catalog/DPA 商品目录广告

### 校验 payload

接口：

```http
POST /fb/catalog/validate
```

示例：

```bash
curl -X POST "http://127.0.0.1:7790/fb/catalog/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "ad_account_id": "act_1234567890",
    "instagram_user_id": "",
    "link": "https://www.example.com/",
    "campaign_name": "2026-US-DPA",
    "page_id": "123456789012345",
    "catalog_fid": "987654321098765",
    "adsets": [
      {
        "adset_name": "US-Interior-Design-25-45",
        "pixel_id": "123456789012345",
        "daily_budget_cents": 1000,
        "countries": ["US"],
        "age_min": 25,
        "age_max": 45,
        "custom_audience_ids": [],
        "interest_ids": ["6003139266461", "6003349442621"],
        "ads": [
          {
            "name": "Fabric Ambient Wall Lamps",
            "product_group_ids": ["1594231", "1594856", "1595142"],
            "message": "Transform your home with soft, calming illumination.",
            "description": "Layered ambient lighting for bedrooms and lounges."
          }
        ]
      }
    ],
    "mock_mode": true
  }'
```

校验成功会返回标准化后的 `normalized` 数据。标准化会做这些处理：

- 去掉字段首尾空格。
- 将国家代码转为大写。
- 将预算和年龄转换为整数。
- 清理空的 ad set / ad。
- 清理 ID 外层多余引号。

### 创建 Catalog/DPA 广告任务

接口：

```http
POST /fb/catalog/create
```

请求体与 `/fb/catalog/validate` 相同。

建议联调阶段设置：

```json
{
  "mock_mode": true
}
```

真实创建条件：

- 安装 `facebook-business`。
- 配置 `META_APP_ID`、`META_APP_SECRET`、`META_ACCESS_TOKEN`，或配置 `FB_TOKEN_MAP_PATH`。
- `mock_mode=false`。

当 SDK 不存在、token map 不存在或广告账户没有授权信息时，服务会返回 mock 创建结果，便于前端和调用方继续联调。

### 查看 Catalog 配置状态

接口：

```http
GET /fb/catalog/config
```

示例：

```bash
curl "http://127.0.0.1:7790/fb/catalog/config"
```

返回字段：

- `meta_sdk_available`：是否安装 `facebook-business`。
- `env_auth_available`：是否配置 `META_ACCESS_TOKEN`。
- `token_map_path`：当前 token map 路径。
- `available_accounts`：从 token map 中读取到的广告账户列表。

## 异步任务

### 提交通用任务

接口：

```http
POST /new_bi_api/task/submit
```

当前公开通用任务接口只允许：

```json
{
  "task_type": "fb_ad_create",
  "params": {}
}
```

其中 `params` 是普通素材广告的完整 payload。Catalog/DPA 请使用 `/fb/catalog/create`，该接口内部会提交 `fb_catalog_ad_create` 任务。

### 查询任务

接口：

```http
GET /new_bi_api/task/{task_id}
```

示例：

```bash
curl "http://127.0.0.1:7790/new_bi_api/task/3f8e0f9f5c3f4c0da8c2c0f2e8b9a111"
```

任务状态：

| 状态 | 说明 |
| --- | --- |
| `pending` | 已提交，等待后台任务执行 |
| `processing` | 后台任务执行中 |
| `success` | 执行成功，`result` 中包含结果 |
| `fail` | 执行失败，`error` 和 `result.traceback` 中包含错误信息 |

任务表字段包括：

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

## 数据和文件存储

默认运行时数据在 `storage/`：

```text
storage/
├── tasks.sqlite3
└── images/
    └── {task_id}/
```

- `tasks.sqlite3` 保存任务、请求参数和执行结果。
- `images/{task_id}` 保存请求中的 base64 图片。
- `image_url` 不会被下载，只会记录 URL。
- `storage/` 是运行时数据，通常不应该提交到 Git。

## 去重逻辑

提交任务时，服务会对请求参数做标准化并计算 SHA-256：

- 字典按 key 排序。
- 字符串去掉首尾空格。
- `image_base64` 不直接参与 hash，而是使用其 SHA-256 摘要。

如果同类型、同 hash 的任务已经处于 `pending`、`processing` 或 `success`，服务会直接返回已有 `task_id`，避免重复创建广告。

## 常见问题

### ModuleNotFoundError: No module named 'app'

当前源码包名固定为 `app`。请确保仓库目录名是 `app`，并从父目录运行：

```bash
cd /path/to/workspace
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 7790 --reload
```

### 普通素材广告没有真正创建

检查：

- `.env` 中 `FB_AD_DRY_RUN=false`。
- 已配置 `META_ACCESS_TOKEN`。
- 已配置 `META_AD_ACCOUNT_ID`。
- payload 或环境变量中有可用的 Page ID。
- access token 具备对应广告账户和 Page 权限。

### Catalog/DPA 返回 mock 结果

常见原因：

- 请求里设置了 `mock_mode=true`。
- 没有安装 `facebook-business`。
- 没有配置 `META_ACCESS_TOKEN`。
- `FB_TOKEN_MAP_PATH` 为空或文件不存在。
- token map 中没有当前 `ad_account_id`。

### CORS_ORIGINS 配置不生效

`CORS_ORIGINS` 是列表类型，建议使用 JSON 数组字符串：

```env
CORS_ORIGINS='["http://localhost:3000","https://admin.example.com"]'
```

### 真实创建后广告为什么没有投放

服务创建的 Campaign、Ad Set、Ad 默认都是 `PAUSED`。这是为了避免接口调用后直接消耗预算。需要在 Meta Ads Manager 审核确认后再手动启用，或根据业务需要调整代码中的状态。

## 本地检查

可以用下面命令做基础语法检查：

```bash
cd /path/to/workspace/app
python3 -m compileall .
```

如果本地已经安装依赖，也可以启动后访问 `/docs` 检查 OpenAPI 是否正常生成。

## Git 工作流

```bash
git status
git add README.md
git commit -m "Add project README"
git push origin main
```

## 安全注意

- 不要提交 `.env`、access token、app secret、token map。
- 生产环境建议限制 `CORS_ORIGINS`，不要长期使用 `["*"]`。
- `storage/tasks.sqlite3` 中可能保存完整请求参数和错误信息，生产环境请注意备份和权限控制。
- Meta access token 应定期轮换，并只授予必要权限。
