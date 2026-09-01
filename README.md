# Serial Protocol Tester / 串口协议测试器

[中文](#中文) | [English](#english)

独立的 PySide6 串口上位机与下位机模拟器。配套的通用 Agent Skill 位于 [serial-protocol-tester-skill](https://github.com/10walnut/serial-protocol-tester-skill)，用于把通信协议文档转换成软件可加载的 `serial_protocol.v1` JSON。

## 中文

主要功能：

- 上位机模式发送请求并解析设备应答。
- 下位机模式匹配外部请求并按协议自动应答。
- 默认中文界面，右上角按钮切换英文界面；协议正文保持 JSON 自身语言。
- 发送前输入日期、时间、传感器、标定值等变量，按 JSON 中的安全公式组帧并重算校验和。
- 数值参数使用独立的 `− / +` 按钮调整；JSON 可用 `step` 指定单次增减量。
- 同时显示最近一次 TX/RX 的字段位置、功能、原始字节、字节序、计算过程、结果和校验过程。
- 单击任意通讯历史行，可以重新解析该行保存的原始 TX/RX 数据，而不只查看最后一条。
- 按帧头和长度处理串口分包、粘包；历史数据保留原始日志，但字段结构只解释一次。
- 支持物理 COM、pyserial URL、内部虚拟链路以及已安装的 com0com 虚拟串口对。

虚拟串口依赖 Windows 内核驱动。创建前软件会检查 PnP 驱动错误和未完成的 `COM#` 设备；只有实际检测到两个目标 COM 端口后才提示成功。错误代码 52 表示 Windows 无法验证驱动数字签名，此时需要卸载不兼容版本、安装与当前 Windows 匹配的已签名驱动并重启，软件不会自动启用测试签名模式。

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

构建脚本会隔离可能污染 Qt DLL 查找的外部 PATH，检查构建清单，并运行 `--self-test` 确认打包后的程序能够真实加载 QtCore 和创建主窗口。只有自检通过才会报告构建成功。输出位于 `dist\SerialProtocolTester.exe`；如果旧 EXE 正在运行而被 Windows 锁定，构建不会强制结束用户进程，而会生成带时间戳的新 EXE。

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

The application supports formula-built transmit frames, selectable traffic-history decoding, checksum calculations, length-based stream framing, physical or virtual COM ports, pyserial URLs, and an internal simulation transport. Numeric variables use explicit decrement/increment buttons, with optional JSON `step` values.

Virtual COM creation checks Windows PnP health and confirms that both requested ports actually exist. Driver signature error 52 is reported and blocks repeated creation of invalid devices; the application does not enable Windows test-signing mode.

Run `start_serial_console.bat` to start it. Build the Windows executable with `build_serial_console.ps1`; the build is accepted only after the packaged Qt self-test succeeds.

## Repository layout

```text
app/       PySide6 application and protocol core
tests/     protocol and virtual-port tests
scripts/   command-line protocol validator
```

MIT licensed.
