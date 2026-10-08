# 双图（astrbot_plugin_xb2img）

AstrBot 图片合成插件：现场将两张图片合成为一张 APNG 动图——聊天列表静止显示预览图 A，点击加载原图后展示图 B。

本插件基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) —— 开源的一站式 Agent 聊天机器人平台，支持主流 IM 平台与多种大模型接入，内置 WebUI 与插件扩展体系。使用文档见 [docs.astrbot.app](https://docs.astrbot.app)。

- 项目主页：https://github.com/imsuperone/xb2img
- 插件 ID：`astrbot_plugin_xb2img`
- 当前版本：`v1.0.8`（要求 AstrBot `>=3.4.0`，平台 `aiocqhttp`）

## 功能特性

- 两副面孔：聊天列表静止显示预览图 A，用户点击加载查看原图后播放展示图 B。
- 标准 APNG 帧序列组织，全彩 RGB/RGBA 保留，无降色深导致的斑驳花屏。
- 自适应梯级压缩：1080px 起按面积比估算降档（最低 128px，最多 6 轮），成品控制在约 1MB。
- 并发排队防护：全局最多 5 个任务并发排队，防止多人高频触发压垮性能。
- 临时文件用后即清，无残留。
- 处理耗时自动提示，生成完毕自动撤回提示并发送原图，保持聊天窗口整洁。
- 底层 OneBot11 原图消息通道直发，避免平台压缩转码破坏动图结构。

## 安装

1. 放入 AstrBot 插件目录：
   ```bash
   git clone https://github.com/imsuperone/xb2img.git data/plugins/astrbot_plugin_xb2img
   ```
2. 安装依赖并重启 AstrBot，插件自动加载：
   ```bash
   pip install -r data/plugins/astrbot_plugin_xb2img/requirements.txt
   ```
3. 在 AstrBot 后台的插件列表中启用「双图」即可开始使用。

## 聊天指令

| 指令 | 说明 |
| :--- | :--- |
| `/xb2img <图A> <图B>` | 合成图片，默认输出 PNG 格式文件（列表看 A，点开看 B） |
| `/xb2img ./a.jpg ./b.jpg` | 支持本地图片文件绝对路径或相对路径 |
| `/xb2img https://.../a.jpg https://.../b.jpg` | 支持网络图片 HTTP/HTTPS 直链自动下载并合成 |
| `/xb2img` 并在消息中附带两张图片 | 交互式发图：直接在指令后面贴上两张图片一起发送 |
| `/xb2img --apng <图A> <图B>` | 强制以 `.apng` 后缀发出（文件字节一致，仅扩展名不同） |

## 实现原理

- **本质单文件动图**：不在协议层分发两个独立资源，而是现场合成一张标准 APNG 动图（PNG 的动图扩展标准，包含 `acTL`、`fcTL` 等数据块）。
- **帧差分展示**：第 1 帧放入预览图 A（QQ 列表缩略模式仅渲染首帧）；第 2 帧及以后放入展示图 B（点击进入大图浏览后动画播放）。
- **直发与格式兼容**：通过底层图片消息原图形式发出，避免二次转码破坏动图结构；Windows QQ NT 等主流客户端均可正常体验。

## 依赖

- `Python >= 3.10`
- `Pillow >= 10.0.0`

## 备注

- 接收端必须支持 APNG 动图播放（Windows QQ NT、各大现代浏览器及主流移动端）。
- 输入单张图片体积建议控制在 20MB 以内，超出将自动拦截以防内存占用过高。
- 合成过程会自动将过大图片等比缩放并压缩至约 1MB，兼顾传输速度与画质。

## 更新日志

见 [CHANGELOG.md](./CHANGELOG.md)。
