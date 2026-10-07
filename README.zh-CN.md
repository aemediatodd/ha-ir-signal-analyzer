# XIAO Smart IR Mate 全量监听与信号分析

[![在 HACS 中打开](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aemediatodd&repository=ha-ir-signal-analyzer&category=integration)

本方案让 XIAO Smart IR Mate 持续监听红外信号，并把每一次接收保存到
Home Assistant Recorder 历史。即使连续按下同一个按键，接收时间也会变化，
因此每次接收都会形成独立历史记录。

## 会创建的实体

- `sensor.ir_signal_last_received`：每次接收的时间。属性含来源、原始脉冲、
  指纹、脉冲数、解码状态和全部解析字段。
- `sensor.ir_signal_protocol`：当前识别出的协议。
- `sensor.ir_signal_command`：命令或数据值。
- `sensor.ir_signal_data`：状态值直接显示 IR 数据。NEC 显示协议和完整编码，
  未识别信号显示 raw 时序；超过 255 字符时状态截断，完整 raw 保存在属性中。
- `sensor.ir_signal_analysis`：显示本地学习码库或 IRDB 的最佳解析结果，属性中
  包含厂商、设备类型、功能、候选项、未知字段和可用于重放的数据。
- `sensor.ir_signal_unparsed_signal`：单独保留最近一次无法匹配或存在多个候选的
  信号，方便后续继续分析。
- `sensor.ir_signal_ir_database_status`：显示当前数据来源、缓存数量、错误信息和
  本地学习码库状态。
- `sensor.ir_signal_irdb_snapshot_updated`：显示当前离线 IRDB 快照的更新时间。
- `button.ir_signal_refresh_irdb_snapshot`：手动下载并校验最新 IRDB 快照，同时
  重新加载本地学习码库，并重新解析最近一次收到的信号。
- `select.ir_signal_decoder`：选择 `auto`、`nec` 或 `raw`，选择后会立即按
  指定方式重新解析最近一次信号。

`auto` 当前识别 NEC。未知协议不会丢弃，完整原始脉冲仍会记录，可在以后
增加解码器后二次分析。

## 1. 分别刷入两份 ESPHome 固件

- 长期监听机：`esphome/xiao-ir-mate-listener.yaml`，节点名为
  `xiao-ir-listener`，只启用 GPIO4 接收。
- 专用发送机：`esphome/xiao-ir-mate-transmitter.yaml`，节点名为
  `xiao-ir-transmitter`，只启用 GPIO3 发射。

把两份 YAML 分别放入 ESPHome Device Builder，并在 `secrets.yaml` 提供：

```yaml
wifi_ssid: "你的 Wi-Fi 名称"
wifi_password: "你的 Wi-Fi 密码"
api_encryption_key: "32 字节 Base64 API 密钥"
ota_password: "OTA 密码"
```

分别校验、编译并刷入对应设备，然后在 Home Assistant 添加这两个 ESPHome
设备。只需在监听机的 ESPHome 配置页点 **配置**，启用
**允许设备执行 Home Assistant 操作**。否则设备不能发送
`esphome.ir_received` 事件。

监听机对每个 `on_raw` 信号上报完整的正负微秒脉冲；发送机只提供官方
`IR Proxy Transmitter` 实体和两个发送动作，不会上报接收事件：

- `esphome.xiao_ir_transmitter_send_raw`
- `esphome.xiao_ir_transmitter_send_nec`

## 2. 安装 Home Assistant 集成

推荐通过 HACS 安装：

1. 打开 **HACS > 集成**。
2. 右上角菜单选择 **自定义存储库**。
3. 填入 `https://github.com/aemediatodd/ha-ir-signal-analyzer`，类别选择
   **集成**；也可以点击文档顶部的 HACS 按钮。
4. 搜索并下载 **IR Signal Analyzer**。
5. 重启 Home Assistant。
6. 进入 **设置 > 设备与服务 > 添加集成**，添加
   **IR Signal Analyzer**。

手动安装时，将目录：

```text
custom_components/ir_signal_analyzer
```

复制到 Home Assistant：

```text
/config/custom_components/ir_signal_analyzer
```

复制后重启 Home Assistant，再添加 **IR Signal Analyzer**。

来源过滤器填写 `xiao-ir-listener`，确保只记录长期监听机。留空也能工作，
但若以后增加其他监听节点，它们的事件会合并进入同一历史实体。

## 3. 验证和查看历史

在 **开发者工具 > 事件** 中监听 `esphome.ir_received`，按下遥控器按钮。
事件应包含 `source`、`raw` 和 `pulse_count`。随后实体会立即更新。

在 Home Assistant 的历史面板选择 `sensor.ir_signal_last_received` 即可看到
每次接收。Recorder 会连同该次状态的属性一起存储；不要在 Recorder 配置中
排除此实体。实体属性里的 `raw` 是可供以后再次解码的原始记录，
`decoded` 是当前解码结果。

可在仪表板加入：

```yaml
type: entities
title: IR 信号分析器
entities:
  - entity: sensor.ir_signal_last_received
  - entity: sensor.ir_signal_data
  - entity: sensor.ir_signal_signal_analysis
  - entity: sensor.ir_signal_unparsed_signal
  - entity: sensor.ir_signal_ir_database_status
  - entity: sensor.ir_signal_irdb_snapshot_updated
  - entity: button.ir_signal_refresh_irdb_snapshot
  - entity: sensor.ir_signal_protocol
  - entity: sensor.ir_signal_command
  - entity: select.ir_signal_decoder
```

## IRDB 匹配、离线快照和本地学习码库

集成启动时先读取已经保存的快照，避免 HA 被网络下载阻塞，然后在后台尝试
更新。需要强制更新时，按下 **Refresh IRDB snapshot** 按钮。下载内容通过
校验后保存到 `/config/ir_signal_analyzer/irdb.zip`；GitHub 暂时不可访问时会
继续使用最后一份有效快照。**IRDB snapshot updated** 实体显示的就是当前
可用快照的保存时间。

IRDB 的结果只能作为候选，不能保证唯一识别，因为 NEC 地址并非厂商全局唯一。
若多个产品使用相同编码，分析实体会显示 `ambiguous` 并列出候选项。你确认设备
后，可创建 `/config/ir_signal_analyzer/codebook.json`，以信号指纹保存本地结果：

```json
{
  "824e21a380d457f1": {
    "label": "客厅电视 / 电源",
    "manufacturer": "Hisense",
    "device_type": "TV",
    "model": "75E5N",
    "function": "POWER",
    "location": "客厅"
  }
}
```

修改后按一次快照更新按钮即可重新加载。匹配优先级为：本地学习码库、当前在线
下载的 IRDB 快照、离线备份。本版暂不适配 Samsung 和 Sony 波形解码，但仍会
完整记录 raw 信号，供重放或以后增加解码器。

## 4. 用发送机重放监听到的信号

以下 Home Assistant 动作会读取历史实体当前保存的最后一条原始波形，并让
专用发送机以 38 kHz 重放：

```yaml
action: esphome.xiao_ir_transmitter_send_raw
data:
  code: >-
    {{ (state_attr('sensor.ir_signal_last_received', 'raw') or '').split(',')
       | map('int') | list }}
  carrier_frequency: 38000
```

若实体 ID 被 Home Assistant 自动加了后缀，请替换示例中的实体 ID。

NEC 可使用解析结果中的 `esphome_address` 和 `esphome_command` 发送。这两个
字段是 ESPHome 所需的完整 16 位值，包含标准 NEC 的反码字节：

```yaml
action: esphome.xiao_ir_transmitter_send_nec
data:
  address: >-
    {{ state_attr('sensor.ir_signal_last_received', 'decoded')['esphome_address'] }}
  command: >-
    {{ state_attr('sensor.ir_signal_last_received', 'decoded')['esphome_command'] }}
```

非 NEC 或不确定协议时使用 `send_raw`，它能保留原信号的完整时序。

## 双设备摆放建议

把 `xiao-ir-transmitter` 放在受控电器附近并对准电器；把
`xiao-ir-listener` 放在能看到房间遥控器的位置。

同一台设备的接收头可能会收到自己刚发出的红外光，软件无法可靠判断它来自
自身还是另一只遥控器。独立监听器应面向房间，但避开主发射器的直射，这样最
适合在发送机工作时继续观察和记录其他遥控器信号。由于发送机固件不启用
接收器，因此不会产生第二份重复监听记录。

## 硬件边界

XIAO IR Mate 的解调接收头主要针对 38 kHz，因此“全部信号”是指它的接收频率
和灵敏度范围内的信号，不能覆盖所有载波频率。超长空调报文也可能超过
ESP32-C3 的 RMT 容量；若原始波形明显被截断，建议用 ESP32-S3 加外置 38 kHz
接收头作为专用监听器。

参考：[官方 XIAO 配置](https://github.com/esphome/infrared-proxies/blob/main/xiao-ir-mate/xiao-ir-mate.yaml)、
[Remote Receiver](https://esphome.io/components/remote_receiver/)、
[Home Assistant Event](https://esphome.io/components/api/#homeassistantevent-action)、
[IRDB](https://github.com/probonopd/irdb)。IRDB 归属和许可说明见
[IRDB_ATTRIBUTION.md](IRDB_ATTRIBUTION.md)。
