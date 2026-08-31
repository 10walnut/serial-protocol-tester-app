# Serial Protocol Tester / 串口协议测试器

[中文](#中文) | [English](#english)

独立的 PySide6 串口上位机与下位机模拟器。配套的通用 Agent Skill 位于 [serial-protocol-tester-skill](https://github.com/10walnut/serial-protocol-tester-skill)，用于把通信协议文档转换成软件可加载的 `serial_protocol.v1` JSON。

## 中文

主要功能：

- 上位机模式发送请求并解析设备应答。
- 下位机模式匹配外部请求并按协议自动应答。
- 默认中文界面，右上角按钮切换英文界面；协议正文保持 JSON 自身语言。
- 发送前输入日期、时间、传感器、标定值等变量，按 JSON 中的安全公式组帧并重算校验和。
- 同时显示最近一次 TX/RX 的字段位置、功能、原始字节、字节序、计算过程、结果和校验过程。
- 按帧头和长度处理串口分包、粘包；历史数据保留原始日志，但字段结构只解释一次。
- 支持物理 COM、pyserial URL、内部虚拟链路以及已安装的 com0com 虚拟串口对。

### 启动

双击 `start_serial_console.bat`，或运行：

```powershell
.\start_serial_console.ps1
```

首次启动会创建 `app\.venv` 并安装依赖。仅检查环境：

```powershell
.\start_serial_console.ps1 -CheckOnly
```

### 打包

```powershell
.\build_serial_console.ps1
```

构建脚本会隔离可能污染 Qt DLL 查找的外部 PATH，检查构建清单，并运行 `--self-test` 确认打包后的程序能够真实加载 QtCore 和创建主窗口。只有自检通过才会报告构建成功。输出位于 `dist\SerialProtocolTester.exe`。

目录模式：

```powershell
.\build_serial_console.ps1 -OneDir
```

### 协议校验

```powershell
python .\scripts\validate_protocol.py .\app\sample_protocol.json
```

## English

This is a standalone PySide6 host/device serial simulator. Its companion [serial-protocol-tester-skill](https://github.com/10walnut/serial-protocol-tester-skill) converts protocol documents into validated `serial_protocol.v1` JSON files.

The application supports formula-built transmit frames, simultaneous TX/RX byte explanations, checksum calculations, length-based stream framing, physical or virtual COM ports, pyserial URLs, and an internal simulation transport.

Run `start_serial_console.bat` to start it. Build the Windows executable with `build_serial_console.ps1`; the build is accepted only after the packaged Qt self-test succeeds.

## Repository layout

```text
app/       PySide6 application and protocol core
tests/     protocol and virtual-port tests
scripts/   command-line protocol validator
```

MIT licensed.
