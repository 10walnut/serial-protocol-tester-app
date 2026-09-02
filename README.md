# Serial Protocol Tester / 串口协议测试器

[中文](#中文) | [English](#english) | [协议转换 Skill](https://github.com/10walnut/serial-protocol-tester-skill)

用 PySide6 编写的串口上位机与下位机模拟器。它加载标准 `serial_protocol.v1` JSON，通过按钮发送命令、自动应答、连续上报数据，并逐字节解释 TX/RX 原文、字段作用、大小端、换算公式与校验过程。

## 中文

### 主要功能

- 上位机模式：向真实设备、虚拟设备或内部模拟链路发送请求并解析应答。
- 下位机模式：匹配外部上位机请求，先发送确认帧，再按 JSON 配置发送延迟帧或周期帧。
- 多段应答：`response` 表示立即确认，`follow_up_replies` 表示后续一次性或周期数据，`stop_streams` 负责停止指定数据流。
- 变量组帧：日期、时间、地址、标定值、传感器值等由输入框提供，软件按受限公式写入帧并重新计算校验和。
- 默认简体中文，右上角可选择简体中文、English、हिन्दी、Español、العربية、Français、বাংলা、Português、Русский、اردو；协议名称和注释仍使用 JSON 自身的单一语言。
- 通讯历史可回选，任意 TX/RX 行都能重新显示该帧的逐字节解释。
- 支持帧头、长度字段、分包和粘包；重复历史记录保留原始数据，但复用一套字段说明。
- 支持物理 COM、pyserial URL、内部虚拟链路和 com0com 虚拟串口对。
- 波特率从协议或命令预加载，可从常用值下拉选择，也可手动输入 50-4000000；手动值会覆盖后续命令预设并立即应用到已打开的串口。
- 高频接收使用帧队列分批派发；实时重复帧完整保留原始记录，但字段解析面板最多每 200 ms 刷新一次，避免 100 ms 数据流持续重建表格。
- 通讯历史保留最近 2000 条并分块清理。点选旧记录会暂停自动跟随，重新选择最后一行即可恢复跟随实时数据。
- 关于窗口包含版本、作者、项目地址、检查更新、Skill 下载与使用教程，以及并列显示的微信/支付宝赞赏码。

### 下载与启动

从 [GitHub Releases](https://github.com/10walnut/serial-protocol-tester-app/releases) 下载 `SerialProtocolTester.exe`。EXE 默认请求管理员权限，以便创建和检查 Windows 虚拟串口；普通串口收发本身不依赖管理员权限。

从源码启动：

```powershell
git clone https://github.com/10walnut/serial-protocol-tester-app.git
cd serial-protocol-tester-app
.\start_serial_console.ps1
```

也可以双击 `start_serial_console.bat`。脚本首次运行会创建 `app\.venv` 并安装依赖，随后以管理员权限启动界面。仅检查环境而不启动：

```powershell
.\start_serial_console.ps1 -CheckOnly
```

### 使用协议 JSON

1. 使用配套 [serial-protocol-tester-skill](https://github.com/10walnut/serial-protocol-tester-skill) 把协议文档转换为 JSON，或先打开自带 `app/sample_protocol.json`。
2. 点击“加载协议”，检查命令原文、注释、波特率和返回原文。
3. 选择上位机或下位机角色，选择内部虚拟链路或串口。
4. 打开连接，双击命令或点击主操作按钮。
5. 如果帧有变量，填写参数后点击“生成并发送”。
6. 在右侧选择任意历史行，检查每个字节的功能、原始值、计算过程和结果。

豆包安装 Skill：从 Skill 项目下载 ZIP，进入“技能新建”→“上传技能”，直接上传包含 `SKILL.md` 的完整 Skill ZIP 压缩包。软件“关于”窗口的“Skill 下载与使用”页也提供下载按钮、项目教程和对应提示词示例。

### 收到请求但没有自动回复

自动回复只在“下位机”角色执行。用另一个串口助手测试时，本软件选择“下位机 + 串口”，打开虚拟串口对的一端；串口助手打开另一端并以 HEX 模式发送完整请求帧。软件匹配 `commands[].request` 后发送 `response`，再按配置发送 `follow_up_replies`。

若当前选择“上位机”，软件仍会显示并解析收到的数据，但不会把请求当作设备命令自动应答；状态栏会提示切换为下位机。下位机收到数据仍不回复时，请依次检查：JSON 中命令是否启用 `auto_reply`、两端串口参数是否一致、发送内容是否包含完整帧及正确校验、协议中的长度和帧头规则是否与实际数据一致。

### 多段应答与 100 ms 实时数据

以下配置表示收到启动命令后先发 `response`，100 ms 后发送第一帧实时数据，之后每 100 ms 继续发送，直到收到 `stop_streams` 包含 `realtime` 的命令：

```json
{
  "response": {"encoding": "hex", "data": "AA 55 81 01 00"},
  "follow_up_replies": [
    {
      "frame_ref": "realtime_data",
      "delay_ms": 100,
      "interval_ms": 100,
      "repeat_count": 0,
      "stream_id": "realtime",
      "prompt_variables": true
    }
  ],
  "auto_reply": true
}
```

被引用的 `frames[].simulation` 定义实际发送模板、输入变量、公式和校验。`prompt_variables: true` 会在数据流启动前弹出输入窗口；设为 `false` 或省略时，每帧使用变量默认值。

### 创建可用的 COM10 ↔ COM11

Windows 用户态软件不能独立创建 COM 设备，本功能调用已安装的 com0com 内核驱动。推荐从 com0com 官方 SourceForge 下载 [3.0.0.0 i386/x64 signed package](https://sourceforge.net/projects/com0com/files/com0com/3.0.0.0/com0com-3.0.0.0-i386-and-x64-signed.zip/download)。该驱动发布时间较早；在启用 Secure Boot 的部分 Windows 10/11 系统上仍可能出现代码 52，软件不会关闭驱动签名验证或自动修改 Secure Boot。

1. 如果设备管理器只在 `com0com - serial port emulators` 下显示 COM10/COM11，而“端口（COM 和 LPT）”中没有它们，请先在 com0com Setup 中删除这对旧端口。
2. 重新安装已签名版本并重启 Windows；设备异常时先在设备管理器确认没有黄色警告。
3. 以管理员身份打开本软件，点击“虚拟串口”，选择 `setupc.exe`。
4. 设置本软件端口 COM10、外部软件端口 COM11，然后点击“创建端口对”。
5. 软件使用 `PortName=COM#,RealPortName=COM10/COM11` 调用 Ports 类安装器。只有两个端口都被 Windows 串口枚举并出现在“端口（COM 和 LPT）”后才提示成功。
6. 本软件选择“下位机 + 串口 + COM10”；待测试上位机或串口助手打开 COM11。两端波特率、数据位、校验位和停止位保持一致。

若提示旧虚拟端口不可用，说明 `setupc list` 中仍存在直接 `PortName=COM10`/`COM11` 的旧配置。删除旧端口对后再创建，不要在其上重复叠加新端口。

### 打包与测试

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
.\build_serial_console.ps1
```

打包脚本会从 PNG 自动生成包含 16、20、24、32、40、48、64、128、256 像素图层的 Windows ICO，再把外壳图标和管理员自提升启动逻辑嵌入 EXE；同时隔离 Qt DLL 搜索路径并运行打包后 `--self-test`。输出为 `dist\SerialProtocolTester.exe`。目录模式使用：

```powershell
.\build_serial_console.ps1 -OneDir
```

### 致谢与第三方组件

虚拟串口能力依赖 [com0com](https://sourceforge.net/projects/com0com/) 项目。感谢 Vyacheslav Frolov 及贡献者提供 GPL 开源的 Windows null-modem 驱动。创建命令依据其 [官方 ReadMe](https://github.com/datamancer/com0com/blob/master/com0com/ReadMe.txt) 中的 Ports 类和 `RealPortName` 说明。本仓库不重新分发第三方内核驱动，避免用户拿到过期或无法核验来源的二进制文件。

本应用由 `十个核桃 / 10walnut` 维护，应用代码使用 MIT License。

## English

Serial Protocol Tester is a standalone PySide6 host/device simulator that executes validated `serial_protocol.v1` JSON files. It supports immediate acknowledgements, delayed and periodic follow-up frames, editable formula variables, checksum rebuilding, stream framing, history-row re-decoding, and byte-level TX/RX explanations.

Download the Windows executable from [GitHub Releases](https://github.com/10walnut/serial-protocol-tester-app/releases). The packaged app requests administrator rights by default for virtual-port creation and diagnostics. To run from source, execute `start_serial_console.ps1`; build with `build_serial_console.ps1`.

For two-application testing, install the official [com0com 3.0.0.0 signed package](https://sourceforge.net/projects/com0com/files/com0com/3.0.0.0/com0com-3.0.0.0-i386-and-x64-signed.zip/download), remove legacy direct `PortName=COM10` pairs, and recreate COM10/COM11 from the application's Virtual Ports dialog. Success requires both names to appear under Windows **Ports (COM & LPT)** and in pyserial enumeration. Some Secure Boot configurations can still reject this older driver with Code 52; the application never disables Windows signature enforcement.

Load a JSON file, choose Host or Device, open an internal or serial transport, and run a command. The interface offers Simplified Chinese, English, Hindi, Spanish, Arabic, French, Bengali, Portuguese, Russian, and Urdu. Baud rate is preloaded from the protocol but remains editable through a common-value dropdown or direct input. High-rate receive traffic is queued and dispatched in bounded batches; repeated live-frame details refresh at most every 200 ms while raw traffic remains available in a rolling 2,000-row history. Selecting an older row pauses live auto-follow. In Device mode, an incoming matching request sends `response` first, `follow_up_replies` schedules additional frames, and `stop_streams` cancels them. Host mode records incoming requests but intentionally does not auto-reply.

For Doubao, download the complete Skill ZIP, open **Create Skill > Upload Skill**, and upload the ZIP containing `SKILL.md` directly. The application's About dialog includes working download and guide buttons for this flow.

The companion [Serial Protocol Tester Skill](https://github.com/10walnut/serial-protocol-tester-skill) converts protocol documents for Codex, Claude Code, WorkBuddy, Harness, Doubao, and other agents. Thanks to the [com0com project](https://sourceforge.net/projects/com0com/) and its contributors; the driver is GPL software and is linked rather than redistributed here. Application code is MIT licensed.
