# Python脚本运行器

这是一个基于PyQt6开发的Python脚本运行器，提供了友好的图形界面来运行和管理Python脚本。

## 功能特点

- 选择并运行Python脚本
- 配置Python解释器路径
- 管理依赖路径和包路径
- 设置环境变量
- 支持UTF-8编码
- 超时控制
- 实时输出显示
- 系统托盘支持

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

1. 运行程序：
```bash
python pyRunner/pyRunner.py
```

2. 在界面中：
   - 选择Python解释器路径
   - 选择要运行的Python脚本
   - 添加需要的依赖路径
   - 设置环境变量（可选）
   - 设置超时时间（可选）
   - 点击"运行"按钮执行脚本

## 注意事项

- 程序默认使用UTF-8编码
- 支持Windows系统托盘功能
- 可以设置脚本运行超时时间
- 支持实时查看脚本输出