
# PromptAPI

一个简单易用的大语言模型API配置管理系统，帮助您快速创建、管理和测试基于提示词工程的API接口。

## 功能特点

- 🚀 **动态API配置**：无需编写代码，通过Web界面快速创建和管理API
- 💬 **提示词工程**：自定义系统提示词，精确控制AI响应
- 🔍 **在线测试**：内置测试工具，实时验证API效果
- 📊 **调用统计**：详细的API调用日志和统计信息
- 🔄 **灵活部署**：支持多种LLM模型和部署方式

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

创建`.env`文件并配置以下变量：

```
OPENAI_API_URL=您的API地址
OPENAI_API_KEY=您的API密钥
MONGODB_URL=MongoDB连接字符串
```

### 启动服务

```bash
python app.py
```

访问 http://localhost:5000 开始使用。

## 使用指南

1. **系统配置**：设置API密钥和模型参数
2. **创建接口**：定义API路径和系统提示词
3. **测试接口**：使用内置测试工具验证效果
4. **集成应用**：通过HTTP请求调用您的API

## 示例

### 创建文本分类API

1. 添加新配置，设置路径为`/api/classify`
2. 编写系统提示词：
   ```
   你是一个文本分类助手。请将用户输入分类为以下类别之一：科技、体育、娱乐、政治、教育。
   请以JSON格式返回，包含category字段和confidence字段。
   ```
3. 保存并测试

### 调用API

```python
import requests

response = requests.post(
    "http://localhost:5000/api/classify",
    json={"text": "苹果发布了最新款iPhone"}
)

print(response.json())
# 输出: {"category": "科技", "confidence": 0.95, "original_text": "苹果发布了最新款iPhone"}
```

## 贡献指南

欢迎提交Issue和Pull Request！

## 许可证

MIT
```
