# 双图 v1.0.11

> 两张图片合成为一张 APNG 动图：列表显示图 A，点开原图后播放图 B。

## 简介

现场合成标准 APNG 动图（含 `acTL`、`fcTL` 数据块），全彩无损、自适应压缩至约 1MB，经 OneBot11 原图通道直发，避免平台转码破坏动图结构。

本插件基于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 开发。AstrBot 是一个松耦合、异步、支持多消息平台部署，具有易用的插件系统和完善的大语言模型（LLM）接入功能的聊天机器人及开发框架，使用文档见 [docs.astrbot.app](https://docs.astrbot.app)。

- 插件 ID：`astrbot_plugin_xb2img`
- 当前版本：`v1.0.11`
- 运行要求：AstrBot `>=3.4.0`，平台 `aiocqhttp`
- 仓库：https://github.com/imsuperone/xb2img

## 功能

- 预览与播放：列表显示图 A，点开原图后播放图 B。
- 无损画质：全彩 RGB/RGBA 帧序列，无降色深花屏。
- 自适应压缩：1080px 起最多 6 轮降档，成品约 1MB。
- 并发排队：最多 5 个任务同时处理，防止高频触发。
- 临时清理：临时文件用后即清，处理提示自动撤回。

## 安装

1. 执行 `git clone https://github.com/imsuperone/xb2img.git data/plugins/astrbot_plugin_xb2img`；
2. 执行 `pip install -r data/plugins/astrbot_plugin_xb2img/requirements.txt`；
3. 重启 AstrBot 并在插件列表中启用「双图」。

## 指令

| 指令 | 说明 |
| :--- | :--- |
| `/xb2img <图A> <图B>` | 合成图片（本地路径、HTTP 直链、或直接附两张图片） |
| `/xb2img --apng <图A> <图B>` | 强制以 `.apng` 后缀发出（字节一致，仅扩展名不同） |

## 说明

- 依赖 `Python >= 3.10`、`Pillow >= 10.0.0`。
- 接收端需支持 APNG 播放（Windows QQ NT、现代浏览器与移动端均可）。
- 单张输入建议 20MB 以内，超出自动拦截。
