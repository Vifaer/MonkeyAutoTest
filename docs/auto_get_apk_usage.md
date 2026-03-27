# 自动获取APK功能使用指南

## 功能描述

`auto_get_apk` 功能允许系统自动从指定的源获取最新的APK包，而无需手动指定APK文件路径或URL。

## 启用功能

### 1. 修改配置文件

编辑 `conf/project.json`，为目标版本启用自动获取：

```json
{
  "your_version": {
    "name": "Your App Name",
    "auto_get_apk": true,
    "apk_source": {
      "type": "http",
      "url": "http://your-server.com/latest.apk"
    }
  }
}
```

### 2. 配置APK源

根据您的APK存储方式选择合适的数据源类型：

#### HTTP/HTTPS下载

```json
{
  "apk_source": {
    "type": "http",
    "url": "http://example.com/app-latest.apk",
    "auth": {
      "username": "your_username",
      "password": "your_password"
    }
  }
}
```

#### Jenkins构建产物

```json
{
  "apk_source": {
    "type": "jenkins",
    "url": "http://jenkins.company.com/job/app-job/lastSuccessfulBuild/artifact/app/build/outputs/apk/debug/app-debug.apk",
    "auth": {
      "username": "jenkins_username",
      "password": "jenkins_api_token"
    }
  }
}
```

#### FTP服务器

```json
{
  "apk_source": {
    "type": "ftp",
    "host": "ftp.company.com",
    "port": 21,
    "path": "/releases/mobile",
    "filename": "app-latest.apk",
    "username": "ftp_user",
    "password": "ftp_password"
  }
}
```

#### 本地文件系统

```json
{
  "apk_source": {
    "type": "local",
    "path": "/path/to/your/app.apk"
  }
}
```

## 使用方法

启用 `auto_get_apk` 后，当运行测试时：

```bash
# 传统Monkey测试
python main.py -v your_version -s device_sn

# 稳定性测试
python main.py --stability -s device_sn
```

系统会自动：
1. 检查配置文件中的 `auto_get_apk` 设置
2. 根据 `apk_source` 配置下载最新APK
3. 将APK保存到 `apks/your_version/` 目录
4. 使用下载的APK进行测试

## 工作流程

```
检查配置 → 确定版本 → 验证auto_get_apk → 获取APK源配置 → 下载APK → 验证文件 → 继续测试流程
```

## 注意事项

### 网络要求
- HTTP/FTP源需要网络连接
- Jenkins源需要API访问权限
- 本地源需要文件系统访问权限

### 认证配置
- HTTP基本认证：使用 `auth` 对象
- Jenkins API令牌：使用API token作为密码
- FTP认证：支持用户名密码认证

### 文件管理
- APK自动保存到 `apks/{version}/` 目录
- 相同版本的新APK会覆盖旧文件
- 下载失败时会清理临时文件

### 错误处理
- 网络连接失败会重试
- 下载中断时会清理部分文件
- 认证失败时会记录详细错误信息

## 故障排除

### 常见问题

1. **下载失败**
   - 检查网络连接
   - 验证URL是否可访问
   - 确认认证信息正确

2. **文件损坏**
   - 检查服务端文件完整性
   - 验证下载过程是否有中断

3. **权限问题**
   - HTTP源：检查认证凭证
   - FTP源：确认FTP服务器权限
   - 本地源：检查文件访问权限

### 调试模式

启用详细日志查看下载过程：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 示例配置

### 企业环境示例

```json
{
  "production": {
    "name": "生产环境测试",
    "auto_get_apk": true,
    "apk_source": {
      "type": "jenkins",
      "url": "http://ci.company.com/job/mobile-app/lastSuccessfulBuild/artifact/app/build/outputs/apk/release/app-release.apk",
      "auth": {
        "username": "ci_user",
        "password": "secure_api_token"
      }
    }
  },
  "staging": {
    "name": "预发布环境测试",
    "auto_get_apk": true,
    "apk_source": {
      "type": "ftp",
      "host": "artifacts.company.com",
      "path": "/staging/mobile",
      "filename": "app-staging.apk",
      "username": "deploy_user",
      "password": "deploy_password"
    }
  }
}
```

### 开源项目示例

```json
{
  "github_release": {
    "name": "GitHub Release版本",
    "auto_get_apk": true,
    "apk_source": {
      "type": "http",
      "url": "https://github.com/owner/repo/releases/latest/download/app-release.apk"
    }
  }
}
```
