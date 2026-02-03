# 妯″潡鍖栫ǔ瀹氭€ф祴璇曞疄鐜版柟妗?

## 姒傝堪

鍩轰簬杞﹁浇绔晶搴旂敤绋冲畾鎬ф祴璇曟柟妗堢殑闇€姹傦紝鏈」鐩凡鎴愬姛瀹炵幇鎬ц兘娴嬭瘯鍜岀ǔ瀹氭€ф祴璇曠殑妯″潡鍖栨灦鏋勶紝鏀寔鐙珛杩愯鍚勪釜娴嬭瘯妯″潡锛屽悓鏃朵繚鎸佸悜鍚庡吋瀹规€с€?

## 鏍稿績鍔熻兘瀹炵幇

### 1. 娴嬭瘯妯″潡鍒掑垎

椤圭洰灏嗙ǔ瀹氭€ф祴璇曞垝鍒嗕负浠ヤ笅鐙珛妯″潡锛?

#### 绯荤粺鍋ュ．鎬ф祴璇?(System Robustness)
- **鍔熻兘**锛氶暱鏃堕棿Monkey鍘嬪姏娴嬭瘯锛屾娴婥RASH鍜孉NR
- **鏍囪瘑绗?*锛歚system_robustness`
- **鍛戒护琛?*锛歚--robustness-only`

#### 寮傚父鎭㈠娴嬭瘯 (Exception Recovery)
- **鍔熻兘**锛氱綉缁滃紓甯搞€佹暟鎹紓甯稿満鏅祴璇?
- **鏍囪瘑绗?*锛歚exception_recovery`
- **鍛戒护琛?*锛歚--recovery-only`

#### 鍝嶅簲鎬ц兘娴嬭瘯 (Response Performance)
- **鍔熻兘**锛氬喎鍚姩鏃堕棿銆佷笅鍙戔啋灞曠ず寤惰繜娴嬭瘯
- **鏍囪瘑绗?*锛歚performance_response`
- **鍛戒护琛?*锛歚--response-only`

#### 璧勬簮娑堣€楁祴璇?(Resource Consumption)
- **鍔熻兘**锛欳PU銆佸唴瀛樹娇鐢ㄧ巼鐩戞帶
- **鏍囪瘑绗?*锛歚performance_resource`
- **鍛戒护琛?*锛歚--resource-only`

#### 瀹屾暣鎬ц兘娴嬭瘯 (Performance All)
- **鍔熻兘**锛氬寘鍚墍鏈夋€ц兘鎸囨爣娴嬭瘯
- **鏍囪瘑绗?*锛歚performance_all`
- **鍛戒护琛?*锛歚--performance-only`

### 2. 浠ｇ爜鏋舵瀯閲嶆瀯

#### 鏂板绫诲拰鏋氫妇

```python
class TestModule(Enum):
    """娴嬭瘯妯″潡鏋氫妇"""
    SYSTEM_ROBUSTNESS = "system_robustness"
    EXCEPTION_RECOVERY = "exception_recovery"
    PERFORMANCE_RESPONSE = "performance_response"
    PERFORMANCE_RESOURCE = "performance_resource"
    PERFORMANCE_ALL = "performance_all"

class ModularStabilityTest:
    """妯″潡鍖栫ǔ瀹氭€ф祴璇曟鏋?""
    # 鏀寔鐙珛杩愯鍚勪釜娴嬭瘯妯″潡
```

#### 鍏抽敭鏂规硶

- `run_selected_tests()`: 鏍规嵁鍚敤妯″潡杩愯鐩稿簲娴嬭瘯
- `_check_module_dependencies()`: 妫€鏌ユā鍧楅棿渚濊禆鍏崇郴
- `validate_module_configuration()`: 楠岃瘉妯″潡閰嶇疆鏈夋晥鎬?

### 3. 鍛戒护琛屽弬鏁版墿灞?

#### 鏂板鍙傛暟

```bash
# 妯″潡鍖栨祴璇曟ā寮?
--modular                    # 鍚敤妯″潡鍖栨祴璇?
--robustness-only           # 浠呯郴缁熷仴澹€ф祴璇?
--recovery-only             # 浠呭紓甯告仮澶嶆祴璇?
--performance-only          # 浠呭畬鏁存€ц兘娴嬭瘯
--response-only             # 浠呭搷搴旀€ц兘娴嬭瘯
--resource-only             # 浠呰祫婧愭秷鑰楁祴璇?
```

#### 浣跨敤绀轰緥

```bash
# 浠呰繍琛屽搷搴旀€ц兘娴嬭瘯
python main.py --stability -s device_sn --response-only

# 澶氭ā鍧楃粍鍚堣繍琛?
python main.py --stability -s device_sn --modular --robustness-only --response-only

# 瀹屾暣娴嬭瘯濂椾欢锛堥粯璁よ涓轰繚鎸佷笉鍙橈級
python main.py --stability -s device_sn
```

### 4. 閰嶇疆鏂囦欢鏀寔

#### project.json 鎵╁睍

```json
{
  "response_only_test": {
    "name": "浠呭搷搴旀€ц兘娴嬭瘯",
    "auto_get_apk": false,
    "modular_config": {
      "enabled_modules": ["performance_response"],
      "module_dependencies": {
        "performance_response": []
      }
    },
    "stability_config": {
      "performance": {
        "sample_interval": 30,
        "monitor_duration": 1800,
        "cold_start_threshold": 3.0,
        "response_delay_threshold": 1.5
      }
    }
  }
}
```

### 5. GUI鐣岄潰鏇存柊

#### 鏂板鍔熻兘

- **娴嬭瘯妯″紡閫夋嫨**锛氬畬鏁存祴璇曞浠?vs 妯″潡鍖栨祴璇?
- **妯″潡澶嶉€夋**锛氱敤鎴峰彲閫夋嫨鎬у惎鐢ㄥ悇涓祴璇曟ā鍧?
- **浜掓枼澶勭悊**锛氳嚜鍔ㄥ鐞嗘€ц兘娴嬭瘯妯″潡鐨勪簰鏂ュ叧绯?
- **閰嶇疆楠岃瘉**锛氱晫闈㈢骇鍒殑妯″潡閰嶇疆楠岃瘉

#### 鐣岄潰甯冨眬

```
娴嬭瘯妯″紡锛歔瀹屾暣娴嬭瘯濂椾欢] [妯″潡鍖栨祴璇昡

妯″潡閫夋嫨锛?
鈻?绯荤粺鍋ュ．鎬ф祴璇?(闀挎椂闂村帇鍔涙祴璇?
鈻?寮傚父鎭㈠娴嬭瘯 (缃戠粶寮傚父銆佹暟鎹紓甯?
鈻?瀹屾暣鎬ц兘娴嬭瘯 (鍝嶅簲+璧勬簮)
鈻?浠呭搷搴旀€ц兘娴嬭瘯 (鍐峰惎鍔ㄣ€佷笅鍙戔啋灞曠ず)
鈻?浠呰祫婧愭秷鑰楁祴璇?(CPU銆佸唴瀛?
```

## 鎶€鏈疄鐜扮粏鑺?

### 妯″潡渚濊禆鍏崇郴

#### 褰撳墠渚濊禆瑙勫垯

- **绯荤粺鍋ュ．鎬?*锛氭棤渚濊禆
- **寮傚父鎭㈠**锛氬彲鑳介渶瑕丮ock Server锛堝彲閫夛級
- **鎬ц兘鍝嶅簲**锛氭棤渚濊禆
- **鎬ц兘璧勬簮**锛氭棤渚濊禆
- **鎬ц兘鍏ㄦ祴璇?*锛氭棤渚濊禆

#### 浜掓枼瑙勫垯

- `performance_all` 涓?`performance_response`/`performance_resource` 浜掓枼
- 鍚敤瀹屾暣鎬ц兘娴嬭瘯鏃讹紝鑷姩绂佺敤鎬ц兘瀛愭ā鍧?

### 鍚戝悗鍏煎鎬?

#### 淇濇寔鐜版湁鍔熻兘

- 鍘熸湁瀹屾暣娴嬭瘯濂椾欢鍔熻兘瀹屽叏淇濇寔
- 鐜版湁鍛戒护琛屽弬鏁扮户缁湁鏁?
- 鍘熸湁閰嶇疆鏂囦欢鏍煎紡鍏煎

#### 娓愯繘寮忓崌绾?

- 鏂板姛鑳介€氳繃鍙€夊弬鏁板惎鐢?
- 榛樿琛屼负涓庡師鏈夌増鏈竴鑷?
- 閰嶇疆鏂囦欢鏀寔鏂版棫鏍煎紡娣峰悎浣跨敤

### 閿欒澶勭悊鍜屽閿?

#### 閰嶇疆楠岃瘉

- 妯″潡閰嶇疆鏈夋晥鎬ф鏌?
- 渚濊禆鍏崇郴鑷姩瑙ｆ瀽
- 浜掓枼妯″潡鍐茬獊妫€娴?
- 鍙嬪ソ鐨勯敊璇彁绀轰俊鎭?

#### 杩愯鏃跺閿?

- 鍗曚釜妯″潡澶辫触涓嶅奖鍝嶅叾浠栨ā鍧?
- 璇︾粏鐨勯敊璇棩蹇楄褰?
- 浼橀泤鐨勯檷绾у鐞?

## 娴嬭瘯楠岃瘉鏂规

### 鍔熻兘娴嬭瘯瑕嗙洊

#### 鍗曞厓娴嬭瘯

- 妯″潡閰嶇疆楠岃瘉娴嬭瘯
- 渚濊禆鍏崇郴妫€鏌ユ祴璇?
- 鍛戒护琛屽弬鏁拌В鏋愭祴璇?
- 閰嶇疆鏂囦欢鍔犺浇娴嬭瘯

#### 闆嗘垚娴嬭瘯

- 鍗曟ā鍧楃嫭绔嬭繍琛屾祴璇?
- 澶氭ā鍧楃粍鍚堣繍琛屾祴璇?
- 瀹屾暣娴嬭瘯濂椾欢鍏煎鎬ф祴璇?
- GUI鐣岄潰鍔熻兘娴嬭瘯

### 楠岃瘉鑴氭湰

椤圭洰鎻愪緵瀹屾暣鐨勬祴璇曢獙璇佽剼鏈?`tests/ (pytest鐢ㄤ緥) 鎴?main.py --stability --modular`锛屽寘鍚細

- 妯″潡閰嶇疆楠岃瘉
- 渚濊禆鍏崇郴妫€鏌?
- 鍛戒护琛屽弬鏁板鐞?
- 閰嶇疆鏂囦欢鏀寔
- 鑷姩鎶ュ憡鐢熸垚

## 浣跨敤鎸囧崡

### 蹇€熷紑濮?

1. **閫夋嫨娴嬭瘯妯″紡**
   ```bash
   # 鍗曟ā鍧楁祴璇?
   python main.py --stability -s device --response-only

   # GUI鐣岄潰
   python gui_main.py  # 鍦℅UI涓€夋嫨妯″潡
   ```

2. **閰嶇疆椤圭洰**
   ```json
   {
     "my_test": {
       "modular_config": {
         "enabled_modules": ["performance_response"]
       }
     }
   }
   ```

3. **杩愯娴嬭瘯**
   ```bash
   python main.py -v my_test -s device
   ```

### 鏈€浣冲疄璺?

#### 娴嬭瘯绛栫暐

- **蹇€熼獙璇?*锛氫娇鐢ㄥ崟妯″潡娴嬭瘯蹇€熷畾浣嶉棶棰?
- **鍏ㄩ潰璇勪及**锛氬畾鏈熻繍琛屽畬鏁存祴璇曞浠?
- **涓撻」妫€鏌?*锛氶拡瀵圭壒瀹氬姛鑳戒娇鐢ㄥ搴旀ā鍧?

#### 閰嶇疆绠＄悊

- 涓轰笉鍚屾祴璇曞満鏅垱寤轰笓鐢ㄩ厤缃?
- 浣跨敤鐗堟湰鎺у埗绠＄悊閰嶇疆鏂囦欢
- 瀹氭湡review鍜屾洿鏂版祴璇曢槇鍊?

## 浜や粯鐗╂竻鍗?

### 鏍稿績浠ｇ爜鏂囦欢

- `utils/stability_test.py` - 妯″潡鍖栨祴璇曟鏋?
- `main.py` - 鎵╁睍鐨勫懡浠よ鍙傛暟澶勭悊
- `gui_main.py` - GUI鐣岄潰鏇存柊
- `conf/project.json` - 鎵╁睍鐨勯厤缃枃浠?

### 娴嬭瘯鍜屾枃妗?

- `tests/ (pytest鐢ㄤ緥) 鎴?main.py --stability --modular` - 鍔熻兘楠岃瘉鑴氭湰
- `docs/modular_stability_implementation.md` - 瀹炵幇鏂囨。
- `modular_test_validation_report.md` - 楠岃瘉鎶ュ憡

### 鎵撳寘鍜岄儴缃?

- `build_exe.py` - 鎵撳寘鑴氭湰
- `build_exe.bat` - Windows鎵瑰鐞嗚剼鏈?
- 鏇存柊鍚庣殑`README.md` - 浣跨敤璇存槑

## 楠屾敹鏍囧噯

### 鍔熻兘瀹屾暣鎬?鉁?

- [x] 鏀寔5涓嫭绔嬫祴璇曟ā鍧?
- [x] 鍛戒护琛屽弬鏁板畬鏁村疄鐜?
- [x] GUI鐣岄潰鍔熻兘瀹屾暣
- [x] 閰嶇疆鏂囦欢鏀寔瀹屽杽
- [x] 渚濊禆鍏崇郴姝ｇ‘澶勭悊

### 鍏煎鎬у拰绋冲畾鎬?鉁?

- [x] 鍚戝悗鍏煎鎬т繚璇?
- [x] 閿欒澶勭悊鍜屽閿欐満鍒?
- [x] 娴嬭瘯楠岃瘉瑕嗙洊鍏ㄩ潰
- [x] 鏂囨。鍜屼娇鐢ㄦ寚鍗楀畬鏁?

### 鎬ц兘鍜屾晥鐜?鉁?

- [x] 妯″潡瑙ｈ€﹀交搴?
- [x] 璧勬簮鍒╃敤浼樺寲
- [x] 鎵ц鏁堢巼鎻愬崌
- [x] 鍙墿灞曟€ц壇濂?

---

## 鎬荤粨

妯″潡鍖栫ǔ瀹氭€ф祴璇曞姛鑳藉凡鍏ㄩ潰瀹炵幇锛屼负杞﹁浇绔晶搴旂敤娴嬭瘯鎻愪緵浜嗙伒娲汇€佸彲瀹氬埗鐨勬祴璇曡В鍐虫柟妗堛€傜敤鎴峰彲浠ユ牴鎹叿浣撻渶姹傞€夋嫨鍚堥€傜殑娴嬭瘯妯″潡锛屾棦鑳借繘琛屽揩閫熶笓椤规祴璇曪紝涔熻兘鎵ц瀹屾暣鐨勭ǔ瀹氭€ц瘎浼般€?

璇ュ疄鐜板畬鍏ㄦ弧瓒冲師濮嬮渶姹傛枃妗ｇ殑瑕佹眰锛屽苟鍦ㄦ鍩虹涓婃彁渚涗簡棰濆鐨勬槗鐢ㄦ€у拰鎵╁睍鎬у姛鑳姐€
