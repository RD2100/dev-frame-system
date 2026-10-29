# 接口测试与Mock示例

本示例展示如何使用 MeterSphere + Apifox 进行接口测试和Mock服务。

## MeterSphere 接口测试示例

### 1. 部署和导入

```bash
# Docker 部署 MeterSphere
docker run -d -p 8081:8081 \
  --name metersphere \
  metersphere/metersphere-allin-one:latest

# 访问 http://localhost:8081
# 默认账号: admin / metersphere
```

### 2. 导入API定义

```bash
# 通过Swagger导入
# MeterSphere → 项目设置 → 接口导入 → Swagger/OpenAPI
# 选择 swagger.json 文件

# 或通过API导入
curl -X POST "http://localhost:8081/api/test/import" \
  -H "X-Api-Key: ${MS_API_KEY}" \
  -F "file=@docs/swagger.json" \
  -F "type=swagger"
```

### 3. MeterSphere 测试场景 (JSON导出格式)

```json
{
  "scenarioName": "用户注册→登录→获取信息",
  "steps": [
    {
      "name": "用户注册",
      "request": {
        "method": "POST",
        "url": "/api/v1/auth/register",
        "headers": {"Content-Type": "application/json"},
        "body": {
          "phone": "{{phone}}",
          "password": "{{password}}",
          "nickname": "{{nickname}}"
        }
      },
      "extract": {
        "token": "$.data.token",
        "userId": "$.data.userId"
      },
      "assertions": [
        {"path": "$.code", "operator": "equals", "value": 200},
        {"path": "$.data.token", "operator": "notNull"}
      ]
    },
    {
      "name": "用户登录",
      "request": {
        "method": "POST",
        "url": "/api/v1/auth/login",
        "headers": {"Content-Type": "application/json"},
        "body": {
          "phone": "{{phone}}",
          "password": "{{password}}"
        }
      },
      "assertions": [
        {"path": "$.code", "operator": "equals", "value": 200}
      ]
    },
    {
      "name": "获取用户信息",
      "request": {
        "method": "GET",
        "url": "/api/v1/user/profile",
        "headers": {
          "Authorization": "Bearer {{token}}"
        }
      },
      "assertions": [
        {"path": "$.code", "operator": "equals", "value": 200},
        {"path": "$.data.nickname", "operator": "equals", "value": "{{nickname}}"}
      ]
    }
  ]
}
```

### 4. 通过API触发测试

```bash
# 触发测试计划
curl -X POST "http://localhost:8081/api/test/plan/run" \
  -H "X-Api-Key: ${MS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "your-test-plan-id"}'

# 或通过TestFrame统一入口
python -m cli.main run --project=app-api --profile=regression
```

## Apifox Mock 示例

### 1. 在Apifox中定义接口

1. 登录 https://apifox.com/
2. 创建项目 → 导入Swagger/OpenAPI 或 手动定义
3. 开启Mock服务 → 获取Mock URL

### 2. Mock配置示例

**智能Mock规则**：Apifox根据字段名自动生成逼真数据
- `name` → 随机中文姓名
- `phone` → 符合规则的手机号
- `email` → 格式正确的邮箱
- `avatar` → 随机头像URL

**自定义Mock规则**：
```javascript
// 在 Apifox 接口的"Mock"标签中设置
{
  "code": 200,
  "message": "success",
  "data|5-10": [{           // 生成5-10条数据
    "id": "@id",            // 随机ID
    "name": "@cname",       // 随机中文名
    "phone": /^1[3-9]\d{9}$/,  // 正则匹配
    "createTime": "@datetime",
    "status|1": [0, 1, 2],  // 概率分布
  }]
}
```

### 3. 前端使用Mock

```javascript
// 开发环境使用Apifox Mock
const API_BASE = process.env.NODE_ENV === 'development'
  ? 'https://mock.apifox.com/m1/1234567-default'
  : 'https://api.example.com';

// 请求示例
fetch(`${API_BASE}/api/v1/user/profile`, {
  headers: { 'Authorization': `Bearer ${token}` }
})
```

## 组合使用场景

### 场景1: 前后端并行开发

```
前端 ←→ Apifox Mock (开发环境)
后端 ←→ MeterSphere 接口测试 (自测)
   ↓
联调：切换到真实后端API
   ↓
MeterSphere 全量回归
```

### 场景2: CI/CD中的接口测试

```yaml
# GitHub Actions
- name: Deploy to Staging
  run: ./deploy-staging.sh

- name: Wait for service ready
  run: |
    for i in $(seq 1 30); do
      curl -s http://staging:8080/health && break
      sleep 2
    done

- name: Run API Tests via MeterSphere
  run: |
    python -m cli.main run --project=app-api --profile=regression --env=staging
```
