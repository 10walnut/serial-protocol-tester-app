# Serial Protocol Assistant 视频推荐逐字稿

建议时长：2 分 40 秒至 3 分钟。录制分辨率建议使用 1920×1080，鼠标移动保持平稳，涉及输入时可提前准备协议 JSON 和一组演示数据。

## 录制准备

- 打开 Serial Protocol Assistant，但先不要加载协议。
- 准备一份由 Skill 生成的 `serial_protocol.v1` JSON，例如 AT32L021 下位机协议。
- 演示阶段优先选择“上位机 + 内部虚拟链路”，避免真实硬件状态影响录制。
- 提前确认 ERTC 对时、实时数据、停止实时数据等命令可以正常演示。
- 录制时放大鼠标指针，敏感串口号、设备编号或路径可提前隐藏。

## 中文逐字稿

| 时间 | 桌面录屏操作 | 旁白逐字稿 |
| --- | --- | --- |
| 00:00–00:15 | 显示原厂协议文档，再切换到软件主界面。 | 做串口开发时，最费时间的往往不是收发几个字节，而是把原厂协议整理成测试命令、计算公式和解析界面。今天分享一款开源工具，Serial Protocol Assistant 串口协议助手。 |
| 00:15–00:35 | 点击“加载协议”，选择准备好的 JSON；镜头停留在自动生成的命令列表。 | 配套的协议转换 Skill 可以读取 Word、PDF、Markdown、Excel 命令表、抓包和示例帧，生成标准协议 JSON。把文件加载到软件后，命令、说明、波特率、应答规则和字段解析会直接出现在界面中。 |
| 00:35–01:00 | 展示角色、通信通道、波特率；切换“上位机”“下位机”和“内部虚拟链路”，最后回到上位机内部虚拟链路。 | 软件可以作为上位机连接真实下位机，也可以切换成下位机，通过虚拟 COM 口测试自己开发的上位机。没有硬件时，还能使用内部虚拟链路先验证协议按钮、组帧和应答逻辑。 |
| 01:00–01:30 | 双击“ERTC 对时”；逐项修改年月日时分秒；点击“生成并发送”。 | 对于日期、时间、地址、阈值、标定值或传感器数据，Skill 会按照原厂协议生成可修改的自定义变量。发送前可以手动输入，也可以使用加减按钮调整。点击生成并发送后，软件会按照字节位置、大小端、比例和偏移公式自动组帧，并重新计算长度和校验和。 |
| 01:30–01:55 | 选中最新 TX、RX 记录；展示下方逐字节解释和计算结果。 | 每次发送和接收都会保留原始 HEX、命令名称和时间。下面的数据解释会告诉你每个字节代表什么、原始值是多少、如何换算，以及校验是否通过。这样不仅能看到结果，还能追溯数据是怎么计算出来的。 |
| 01:55–02:20 | 发送“开启实时传输”，展示 ACK 后持续出现的周期数据；再发送停止命令。 | 一条请求还可以先返回确认帧，再延迟发送后续数据，或者按照一百毫秒的间隔持续输出实时帧。停止命令会结束对应的数据流，适合测试传感器上报、历史记录和连续采样协议。 |
| 02:20–02:42 | 在通讯记录中依次指向预期命令、TX、RX 和解析区域；可切换到虚拟串口窗口。 | 调试时，把协议预期、实际发送和实际接收放在一起比较，就能更快判断问题出在上位机组帧、下位机响应、协议定义，还是波特率、接线和虚拟串口链路。 |
| 02:42–03:00 | 回到完整主界面，显示 GitHub 项目页或 README。 | 协议验证完成以后，这个软件也可以继续作为简单的功能上位机使用。项目已经开源，Windows 可以直接下载运行，Skill 和应用的地址都放在视频说明中，欢迎试用并提交实际协议进行验证。 |

## English Script

| Time | Desktop recording action | Verbatim narration |
| --- | --- | --- |
| 00:00–00:15 | Show a vendor protocol document, then switch to the main application window. | In serial development, sending a few bytes is rarely the hardest part. The real cost is turning a vendor specification into test commands, formulas, and a usable decoding interface. This is Serial Protocol Assistant, an open-source tool built for that workflow. |
| 00:15–00:35 | Select **Load Protocol**, open the prepared JSON, and pause on the generated command list. | The companion protocol Skill can read Word, PDF, Markdown, spreadsheet command tables, packet captures, and sample frames. It produces standard protocol JSON. Once loaded, the app immediately shows the commands, descriptions, baud rate, response rules, and field definitions. |
| 00:35–01:00 | Show the role, transport, and baud controls. Switch between Host, Device, and Internal Virtual Link, then return to Host with the internal link. | The application can act as a host connected to real hardware, or emulate a device through a virtual COM pair while you test another host program. If hardware is not available, the internal virtual link can verify command buttons, frame generation, and response behavior first. |
| 01:00–01:30 | Open the ERTC time-sync command, change the date and time fields, then select **Generate and Send**. | Dates, times, addresses, thresholds, calibration values, and sensor samples do not have to remain fixed example bytes. The Skill creates editable variables from the vendor protocol. Before sending, you can type a value or use the step controls. The app then applies byte positions, endianness, scaling, and offset formulas, and recalculates the frame length and checksum. |
| 01:30–01:55 | Select the latest TX and RX records and show the byte-level explanation panel. | Every transmission and response keeps its raw hexadecimal data, command name, and timestamp. The explanation panel shows what each byte means, its raw value, how the displayed result was calculated, and whether validation passed. You can inspect both the result and the calculation behind it. |
| 01:55–02:20 | Send the realtime-start command, show the acknowledgement followed by periodic frames, then send the stop command. | A request can return an immediate acknowledgement and then schedule delayed or periodic replies. For example, a realtime stream can publish a frame every one hundred milliseconds until a stop command cancels it. This is useful for sensors, history records, and continuous sampling protocols. |
| 02:20–02:42 | Point to the expected command, TX, RX, and decoded fields. Briefly show the virtual-port dialog. | By comparing the documented frame, actual TX, actual RX, and decoded fields, you can quickly separate a host framing problem from a device response problem, an incorrect protocol definition, or a baud-rate, wiring, driver, or virtual-port issue. |
| 02:42–03:00 | Return to the full application, then show the GitHub repository or README. | After validation, the same application can remain in use as a lightweight functional host. The Windows build and the cross-client protocol Skill are both open source. Their links are in the video description, ready for you to test with a real protocol. |

## 视频说明链接

- App: https://github.com/10walnut/serial-protocol-tester-app
- Skill: https://github.com/10walnut/serial-protocol-tester-skill
- Windows 下载: https://github.com/10walnut/serial-protocol-tester-app/releases/latest
