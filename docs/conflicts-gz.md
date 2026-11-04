# 归属冲突与待定项（S1-6 产出）

- 快照 p1a-20261103；生成 2026-11-04T22:35:20+08:00
- 关系 256 条；按省 {'广东省': 91, '(未定)': 165}
- 按市（前 12）{'(未定)': 165, '广州市': 79, '佛山市': 12}
- 标记 {'stops_unmatched': 159, 'no_resolved_stops': 6}
- 上海关系内站点：市内 0，市外 0（其中界外且未定 0）

## 一、跨省关系

无。

## 二、跨市关系（同一关系跨地级市）

| 关系 | 名称 | 各市站数 |
| --- | --- | --- |
| `2646091` | 地铁 广佛线：沥滘 → 新城东 | {'广州市': 10, '佛山市': 15} |
| `7520751` | 地铁 7号线：美的大道 → 燕山 | {'佛山市': 7, '广州市': 20} |
| `7520752` | 地铁 7号线：燕山 → 美的大道 | {'广州市': 20, '佛山市': 7} |
| `7944797` | 地铁 广佛线：新城东 → 沥滘 | {'佛山市': 15, '广州市': 10} |
| `13604443` | 地铁 2号线：广州南站 → 南庄 | {'广州市': 1, '佛山市': 16} |
| `13604444` | 地铁 2号线：南庄 → 广州南站 | {'佛山市': 16, '广州市': 1} |

## 三、未定城市的关系

共 159 条。

| 关系 | 名称 | 制式 | 省 | 站数 | 未命中 | flags |
| --- | --- | --- | --- | --- | --- | --- |
| `2926506` | 輕鐵751綫 Light Rail 751 (天逸 Tin Yat → 友愛 Yau Oi) | lrt | None | 22 | 22 | stops_unmatched:22 |
| `2929802` | 輕鐵751P綫 Light Rail 751P (天逸 Tin Yat → 天水圍 Tin Shui Wai) | lrt | None | 9 | 9 | stops_unmatched:9 |
| `2941692` | 輕鐵705綫 Light Rail 705 (天水圍循環綫 Tin Shui Wai Circular) | lrt | None | 15 | 15 | stops_unmatched:15 |
| `2941790` | Light Rail 706 輕鐵706綫 (天水圍循環綫 Tin Shui Wai Circular) | lrt | None | 15 | 15 | stops_unmatched:15 |
| `2942633` | 輕鐵761P綫 Light Rail 761P (元朗 Yuen Long → 天逸 Tin Yat) | lrt | None | 14 | 14 | stops_unmatched:14 |
| `3515354` | 輕鐵505綫 Light Rail 505 (兆康 Siu Hong → 三聖 Sam Shing) | lrt | None | 14 | 14 | stops_unmatched:14 |
| `3679916` | 輕鐵507綫 Light Rail 507 (屯門碼頭 Tuen Mun Ferry Pier → 田景 Tin King) | lrt | None | 16 | 16 | stops_unmatched:16 |
| `3680161` | 輕鐵610綫 Light Rail 610 (屯門碼頭 Tuen Mun Ferry Pier → 元朗 Yuen Long) | lrt | None | 26 | 26 | stops_unmatched:26 |
| `3680323` | 輕鐵614綫 Light Rail 614 (元朗 Yuen Long → 屯門碼頭 Tuen Mun Ferry Pier) | lrt | None | 24 | 24 | stops_unmatched:24 |
| `3680520` | Light Rail 615 (元朗 Yuen Long → 屯門碼頭 Tuen Mun Ferry Pier) | lrt | None | 26 | 26 | stops_unmatched:26 |
| `5955256` | 輕鐵614P綫 Light Rail 614P (兆康 Siu Hong → 屯門碼頭 Tuen Mun Ferry Pier) | lrt | None | 12 | 12 | stops_unmatched:12 |
| `5955257` | 輕鐵614P綫 Light Rail 614P (屯門碼頭 Tuen Mun Ferry Pier → 兆康 Siu Hong) | lrt | None | 13 | 13 | stops_unmatched:13 |
| `5955258` | 輕鐵615P綫 Light Rail 615P (兆康 Siu Hong → 屯門碼頭 Tuen Mun Ferry Pier) | lrt | None | 16 | 16 | stops_unmatched:16 |
| `5955259` | 輕鐵615P綫 Light Rail 615P (屯門碼頭 Tuen Mun Ferry Pier → 兆康 Siu Hong) | lrt | None | 16 | 16 | stops_unmatched:16 |
| `6481282` | 輕鐵505綫 Light Rail 505 (三聖 Sam Shing → 兆康 Siu Hong) | lrt | None | 16 | 16 | stops_unmatched:16 |
| `6481316` | 輕鐵507綫 Light Rail 507 (田景 Tin King → 屯門碼頭 Tuen Mun Ferry Pier) | lrt | None | 16 | 16 | stops_unmatched:16 |
| `6481420` | 輕鐵610綫 Light Rail 610 (元朗 Yuen Long → 屯門碼頭 Tuen Mun Ferry Pier) | lrt | None | 26 | 26 | stops_unmatched:26 |
| `6481434` | 輕鐵615綫 Light Rail 615 (屯門碼頭 Tuen Mun Ferry Pier → 元朗 Yuen Long) | lrt | None | 26 | 26 | stops_unmatched:26 |
| `6485194` | 輕鐵614綫 Light Rail 614 (屯門碼頭 Tuen Mun Ferry Pier → 元朗 Yuen Long) | lrt | None | 24 | 24 | stops_unmatched:24 |
| `6485218` | 輕鐵751綫 Light Rail 751 (友愛 Yau Oi → 天逸 Tin Yat) | lrt | None | 23 | 23 | stops_unmatched:23 |
| `6485219` | 輕鐵751P綫 Light Rail 751P (天水圍 Tin Shui Wai → 天逸 Tin Yat) | lrt | None | 9 | 9 | stops_unmatched:9 |
| `6485221` | 輕鐵761P綫 Light Rail 761P (天逸 Tin Yat → 元朗 Yuen Long) | lrt | None | 14 | 14 | stops_unmatched:14 |
| `10402162` | 氹仔線 Linha da Taipa（氹仔碼頭 Terminal Marítimo da Taipa → 媽閣 Barra） | lrt | None | 13 | 13 | stops_unmatched:13 |
| `10402173` | 氹仔線 Linha da Taipa（媽閣 Barra → 氹仔碼頭 Terminal Marítimo da Taipa） | lrt | None | 13 | 13 | stops_unmatched:13 |
| `12619403` | 輕鐵751P綫 Light Rail 751P (天逸 Tin Yat → 兆康 Siu Hong) | lrt | None | 15 | 15 | stops_unmatched:15 |
| `14244774` | 香港國際機場旅客捷運系統 Hong Kong International Airport Automated People Mover | lrt | None | 3 | 3 | stops_unmatched:3 |
| `14244775` | 香港國際機場旅客捷運系統 Hong Kong International Airport Automated People Mover | lrt | None | 3 | 3 | stops_unmatched:3 |
| `14244776` | APM T1: Midfield Concourse => West Hall | apm | None | 2 | 2 | stops_unmatched:2 |
| `14244777` | APM T1: West Hall => Midfield Concourse | apm | None | 2 | 2 | stops_unmatched:2 |
| `14244778` | APM T1: Midfield Concourse => East Hall | apm | None | 3 | 3 | stops_unmatched:3 |
| `14244779` | APM T1: East Hall => Midfield Concourse | apm | None | 3 | 3 | stops_unmatched:3 |
| `14594829` | 深圳有轨电车：清湖 → 新澜 | lrt | None | 15 | 15 | stops_unmatched:15 |
| `14594830` | 深圳有轨电车：新澜 → 清湖 | lrt | None | 14 | 14 | stops_unmatched:14 |
| `14594831` | 深圳有轨电车：清湖 → 下围 | lrt | None | 12 | 12 | stops_unmatched:12 |
| `14594832` | 深圳有轨电车：下围 → 清湖 | lrt | None | 12 | 12 | stops_unmatched:12 |
| `17814455` | 华为松山湖有轨电车1号线 | lrt | None | 7 | 7 | stops_unmatched:7 |
| `17814719` | 华为松山湖有轨电车3号线 | lrt | None | 15 | 15 | stops_unmatched:15 |
| `17814720` | 华为松山湖有轨电车2号线 | lrt | None | 13 | 13 | stops_unmatched:13 |
| `18238277` | 澳門輕軌石排灣線 Linha de Seac Pai Van（石排灣 Seac Pai Van → 協和醫院 Hospital Union） | lrt | None | 2 | 2 | stops_unmatched:2 |
| `18238278` | 澳門輕軌石排灣線 Linha de Seac Pai Van（協和醫院 Hospital Union → 石排灣 Seac Pai Van） | lrt | None | 2 | 2 | stops_unmatched:2 |
| `18361945` | 橫琴線 Linha de Hengqin (橫琴 Hengqin → 蓮花 Lótus) | lrt | None | 2 | 2 | stops_unmatched:2 |
| `18361946` | 橫琴線 Linha de Hengqin （蓮花 Lótus → 橫琴 Hengqin） | lrt | None | 2 | 2 | stops_unmatched:2 |
| `13042022` |  | monorail | None | 3 | 3 | stops_unmatched:3 |
| `15061611` | 轻轨 坪山云巴1号线: 比亚迪北 -> 坪山高铁站 | monorail | None | 11 | 11 | stops_unmatched:11 |
| `15061612` | 轻轨 坪山云巴1号线: 坪山高铁站 -> 比亚迪北 | monorail | None | 11 | 11 | stops_unmatched:11 |
| `18610083` | 清远长隆磁浮旅游专线: 长隆森林王国 → 清远长隆 | monorail | None | 3 | 3 | stops_unmatched:3 |
| `18610084` | 清远长隆磁浮旅游专线: 清远长隆 → 长隆森林王国 | monorail | None | 3 | 3 | stops_unmatched:3 |
| `269669` | 港鐵荃灣綫 MTR Tsuen Wan Line (南行 Southbound) | metro | None | 16 | 16 | stops_unmatched:16 |
| `269672` | 港鐵將軍澳綫 MTR Tseung Kwan O Line | metro | None | 7 | 7 | stops_unmatched:7 |
| `272125` | 港鐵觀塘綫 MTR Kwun Tong Line | metro | None | 17 | 17 | stops_unmatched:17 |
| `2287554` | 地铁 1号线：罗湖 → 机场东 | metro | None | 30 | 30 | stops_unmatched:30 |
| `2287559` | 地铁 3号线: 福保 → 坪地六联 | metro | None | 38 | 38 | stops_unmatched:38 |
| `2287563` | 地铁 4号线：福田口岸 -> 牛湖 | metro | None | 23 | 23 | stops_unmatched:23 |
| `2752374` | 地铁 2号线：湾厦 → 莲塘 | metro | None | 27 | 27 | stops_unmatched:27 |
| `2752389` | 地铁 5号线：赤湾 → 大剧院 | metro | None | 37 | 37 | stops_unmatched:37 |
| `4248589` | 港鐵東鐵綫 MTR East Rail Line | metro | None | 14 | 14 | stops_unmatched:14 |
| `4248590` | 港鐵東鐵綫 MTR East Rail Line | metro | None | 14 | 14 | stops_unmatched:14 |
| `4248591` | 港鐵東鐵綫 MTR East Rail Line | metro | None | 14 | 14 | stops_unmatched:14 |
| `4248592` | 港鐵東鐵綫 MTR East Rail Line | metro | None | 14 | 14 | stops_unmatched:14 |
| `4250432` | 港鐵東鐵綫 MTR East Rail Line | metro | None | 14 | 14 | stops_unmatched:14 |

## 四、无已解析站的关系

- `9736634` APM T2: to concourse：no_resolved_stops
- `13386796` ：no_resolved_stops
- `17581553` APM T2: from concourse：no_resolved_stops
- `13163410` 深圳地铁：no_resolved_stops
- `18523160` 广州地铁22号线（番禺广场方向）：no_resolved_stops
- `18523161` 广州地铁22号线（白云机场方向）：no_resolved_stops

## 五、口径

- 市：`admin_level=5` 地级市面（上海用 `admin_level=4` 上海市面）点面判定，并用 `contains_xy` 批量算。
- 省：城市命中即得省；城市未命中时退回省面（上海/浙江 L4，江苏 = 13 地级市并集）。
- 江苏省 L4 关系缺 11 个与山东/安徽的共边 way（未下载那两省），自拼只有 309.4 km²，故改用并集。
- 未闭合的市面不参与判定（避免假内假外），这类城市在「未定城市」里列出。
- 上海 P0 只需上海市定案；苏浙其他城市已随 L5 自动得到，供 P1 使用。
