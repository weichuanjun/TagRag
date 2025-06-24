# Ngrok 配置说明

## 问题描述

当你通过ngrok访问前端时，无法选择知识库，这是因为前端配置的代理指向 `localhost:8000`，而ngrok的URL是 `https://86d5-182-169-68-54.ngrok-free.app`，造成了跨域问题。

## 解决方案

### 方案1: 直接访问本地前端（推荐）

既然前端已经在 `localhost:3000` 上运行，直接访问：

```
http://localhost:3000
```

### 方案2: 使用ngrok访问（已配置）

如果必须通过ngrok访问，请按以下步骤操作：

#### 1. 启动ngrok服务

```bash
# 在项目根目录下运行
ngrok start --config ngrok.yml
```

这将启动两个隧道：
- 前端隧道：代理到 `localhost:3000`
- 后端隧道：代理到 `localhost:8000`

#### 2. 访问前端

使用ngrok提供的前端URL访问，例如：
```
https://86d5-182-169-68-54.ngrok-free.app
```

#### 3. 前端自动配置

前端代码已经更新，会自动检测ngrok域名并使用相对路径访问API，这样ngrok可以正确代理请求到后端。

## 配置详情

### ngrok.yml 配置

```yaml
version: "2"
authtoken: 2xAHE6t2Z2Kh0nHglQHFdLhD1zc_6Zy8zkX3UWqiF6FxBEBYk
tunnels:
  backend-api:
    proto: http
    addr: 8000
  frontend-app:
    proto: http
    addr: 3000
```

### 前端自动检测逻辑

前端代码会自动检测当前域名：
- 如果包含 `ngrok` 或 `ngrok-free.app`，使用相对路径
- 否则使用 `http://localhost:8000`

## 验证配置

### 1. 检查服务状态

```bash
# 检查后端
lsof -i :8000

# 检查前端
lsof -i :3000

# 检查ngrok
ps aux | grep ngrok
```

### 2. 测试API连接

访问测试页面：
```
http://localhost:3000/test
# 或
https://your-ngrok-url/test
```

### 3. 查看浏览器控制台

按F12打开开发者工具，查看Console标签页：
- 应该看到 "API Base URL set to: " 的日志
- 对于ngrok访问，应该显示空字符串或相对路径

## 常见问题

### 问题1: 仍然无法选择知识库
**解决方案**:
1. 刷新页面
2. 检查浏览器控制台是否有错误
3. 确认ngrok正在运行

### 问题2: API请求失败
**解决方案**:
1. 确认后端服务正在运行
2. 检查ngrok隧道状态
3. 查看浏览器Network标签页的请求状态

### 问题3: 跨域错误
**解决方案**:
1. 确认使用ngrok的前端URL访问
2. 不要混合使用localhost和ngrok URL
3. 检查ngrok配置是否正确

## 推荐使用方式

**推荐直接使用本地访问**：
```
http://localhost:3000
```

这样可以避免跨域问题，并且响应速度更快。 