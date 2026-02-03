# 鑷姩鑾峰彇APK鍔熻兘浣跨敤鎸囧崡

## 鍔熻兘姒傝堪

`auto_get_apk` 鍔熻兘鍏佽绯荤粺鑷姩浠庢寚瀹氱殑婧愯幏鍙栨渶鏂扮殑APK鍖咃紝鑰屾棤闇€鎵嬪姩鎸囧畾APK鏂囦欢璺緞鎴朥RL銆?

## 鍚敤鍔熻兘

### 1. 淇敼閰嶇疆鏂囦欢

缂栬緫 `conf/project.json`锛屼负鐩爣鐗堟湰鍚敤鑷姩鑾峰彇锛?

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

### 2. 閰嶇疆APK婧?

鏍规嵁鎮ㄧ殑APK瀛樺偍鏂瑰紡閫夋嫨鍚堥€傜殑婧愮被鍨嬶細

#### HTTP/HTTPS涓嬭浇

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

#### Jenkins鏋勫缓浜х墿

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

#### FTP鏈嶅姟鍣?

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

#### 鏈湴鏂囦欢绯荤粺

```json
{
  "apk_source": {
    "type": "local",
    "path": "/path/to/your/app.apk"
  }
}
```

## 浣跨敤鏂规硶

鍚敤 `auto_get_apk` 鍚庯紝褰撹繍琛屾祴璇曟椂锛?

```bash
# 浼犵粺Monkey娴嬭瘯
python main.py -v your_version -s device_sn

# 绋冲畾鎬ф祴璇?
python main.py --stability -s device_sn
```

绯荤粺浼氳嚜鍔細
1. 妫€鏌ラ厤缃枃浠朵腑鐨?`auto_get_apk` 璁剧疆
2. 鏍规嵁 `apk_source` 閰嶇疆涓嬭浇鏈€鏂癆PK
3. 灏咥PK淇濆瓨鍒?`apks/your_version/` 鐩綍
4. 浣跨敤涓嬭浇鐨凙PK杩涜娴嬭瘯

## 宸ヤ綔娴佺▼

```
妫€鏌ラ厤缃?鈫?纭畾鐗堟湰 鈫?楠岃瘉auto_get_apk 鈫?鑾峰彇APK婧愰厤缃?鈫?涓嬭浇APK 鈫?楠岃瘉鏂囦欢 鈫?缁х画娴嬭瘯娴佺▼
```

## 娉ㄦ剰浜嬮」

### 缃戠粶瑕佹眰
- HTTP/FTP婧愰渶瑕佺綉缁滆繛鎺?
- Jenkins婧愰渶瑕丄PI璁块棶鏉冮檺
- 鏈湴婧愰渶瑕佹枃浠剁郴缁熻闂潈闄?

### 璁よ瘉閰嶇疆
- HTTP鍩烘湰璁よ瘉锛氫娇鐢?`auth` 瀵硅薄
- Jenkins API浠ょ墝锛氫娇鐢ˋPI token浣滀负瀵嗙爜
- FTP璁よ瘉锛氭敮鎸佺敤鎴峰悕瀵嗙爜璁よ瘉

### 鏂囦欢绠＄悊
- APK鑷姩淇濆瓨鍒?`apks/{version}/` 鐩綍
- 鐩稿悓鐗堟湰鐨勬柊APK浼氳鐩栨棫鏂囦欢
- 涓嬭浇澶辫触鏃朵細娓呯悊涓存椂鏂囦欢

### 閿欒澶勭悊
- 缃戠粶杩炴帴澶辫触鏃朵細閲嶈瘯
- 涓嬭浇涓柇鏃朵細娓呯悊閮ㄥ垎鏂囦欢
- 璁よ瘉澶辫触鏃朵細璁板綍璇︾粏閿欒淇℃伅

## 鏁呴殰鎺掗櫎

### 甯歌闂

1. **涓嬭浇澶辫触**
   - 妫€鏌ョ綉缁滆繛鎺?
   - 楠岃瘉URL鏄惁鍙闂?
   - 纭璁よ瘉淇℃伅姝ｇ‘

2. **鏂囦欢鎹熷潖**
   - 妫€鏌ユ湇鍔″櫒绔枃浠跺畬鏁存€?
   - 楠岃瘉涓嬭浇杩囩▼涓槸鍚︽湁涓柇

3. **鏉冮檺闂**
   - HTTP婧愶細妫€鏌ヨ璇佸嚟鎹?
   - FTP婧愶細纭FTP鏈嶅姟鍣ㄦ潈闄?
   - 鏈湴婧愶細妫€鏌ユ枃浠惰闂潈闄?

### 璋冭瘯妯″紡

鍚敤璇︾粏鏃ュ織鏌ョ湅涓嬭浇杩囩▼锛?

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 绀轰緥閰嶇疆

### 浼佷笟鐜绀轰緥

```json
{
  "production": {
    "name": "鐢熶骇鐜娴嬭瘯",
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
    "name": "棰勫彂甯冪幆澧冩祴璇?,
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

### 寮€婧愰」鐩ず渚?

```json
{
  "github_release": {
    "name": "GitHub Release鐗堟湰",
    "auto_get_apk": true,
    "apk_source": {
      "type": "http",
      "url": "https://github.com/owner/repo/releases/latest/download/app-release.apk"
    }
  }
}
```
