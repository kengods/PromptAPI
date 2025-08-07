from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
import json
import os
import openai
import re
from datetime import datetime
from typing import Dict, Any
from pymongo import MongoClient
from bson import ObjectId
import traceback

app = Flask(__name__)

# 配置CORS，允许所有域名访问
CORS(app, resources={
    r"/api/*": {"origins": "*"},
    r"/YiDiJiuYi/*": {"origins": "*"}
})

# 配置文件路径
CONFIG_FILE = 'api_configs.json'
SYSTEM_CONFIG_FILE = 'system_config.json'

class MongoLogger:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.client = None
        self.db = None
        self.collection = None
        self.connect()
    
    def connect(self):
        """连接MongoDB"""
        try:
            config = self.config_manager.get_config()
            if not config.get('log_enabled', True):
                return
            
            mongodb_url = config.get('mongodb_url', 'mongodb://localhost:27017')
            database_name = config.get('mongodb_database', 'api_logs')
            collection_name = config.get('mongodb_collection', 'call_logs')
            
            self.client = MongoClient(mongodb_url, serverSelectionTimeoutMS=5000)
            # 测试连接
            self.client.server_info()
            self.db = self.client[database_name]
            self.collection = self.db[collection_name]
            print(f"MongoDB连接成功: {mongodb_url}/{database_name}")
        except Exception as e:
            print(f"MongoDB连接失败: {str(e)}")
            self.client = None
            self.db = None
            self.collection = None
    
    def reconnect(self):
        """重新连接MongoDB"""
        if self.client:
            self.client.close()
        self.connect()
    
    def log_api_call(self, config_name, request_data, response_data, success=True, error_message=None, execution_time=None):
        """记录API调用日志"""
        try:
            config = self.config_manager.get_config()
            if not config.get('log_enabled', True) or self.collection is None:
                return
            
            log_entry = {
                'timestamp': datetime.now(),
                'config_name': config_name,
                'request_data': request_data,
                'response_data': response_data,
                'success': success,
                'error_message': error_message,
                'execution_time_ms': execution_time,
                'ip_address': request.remote_addr,
                'user_agent': request.headers.get('User-Agent', ''),
                'request_id': str(ObjectId())
            }
            
            self.collection.insert_one(log_entry)
        except Exception as e:
            print(f"日志记录失败: {str(e)}")
    
    def get_logs(self, limit=100, skip=0, config_name=None, start_date=None, end_date=None):
        """获取日志记录"""
        try:
            if self.collection is None:
                return []
            
            query = {}
            if config_name:
                query['config_name'] = config_name
            if start_date or end_date:
                query['timestamp'] = {}
                if start_date:
                    query['timestamp']['$gte'] = start_date
                if end_date:
                    query['timestamp']['$lte'] = end_date
            
            cursor = self.collection.find(query).sort('timestamp', -1).skip(skip).limit(limit)
            logs = list(cursor)
            
            # 转换ObjectId为字符串
            for log in logs:
                log['_id'] = str(log['_id'])
                if 'timestamp' in log:
                    log['timestamp'] = log['timestamp'].isoformat()
            
            return logs
        except Exception as e:
            print(f"获取日志失败: {str(e)}")
            return []
    
    def get_stats(self):
        """获取统计信息"""
        try:
            if self.collection is None:
                return {}
            
            total_calls = self.collection.count_documents({})
            success_calls = self.collection.count_documents({'success': True})
            error_calls = self.collection.count_documents({'success': False})
            
            # 按配置名称统计
            config_stats = list(self.collection.aggregate([
                {'$group': {
                    '_id': '$config_name',
                    'count': {'$sum': 1},
                    'success_count': {'$sum': {'$cond': ['$success', 1, 0]}},
                    'error_count': {'$sum': {'$cond': ['$success', 0, 1]}}
                }}
            ]))
            
            return {
                'total_calls': total_calls,
                'success_calls': success_calls,
                'error_calls': error_calls,
                'success_rate': round((success_calls / total_calls * 100) if total_calls > 0 else 0, 2),
                'config_stats': config_stats
            }
        except Exception as e:
            print(f"获取统计信息失败: {str(e)}")
            return {}

class SystemConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config()
        self.apply_config()
    
    # 在文件顶部添加
    from dotenv import load_dotenv
    load_dotenv()
    
    # 然后修改 load_config 方法
    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "openai_api_url": os.getenv("OPENAI_API_URL", "https://api.example.com/v1"),
            "openai_api_key": os.getenv("OPENAI_API_KEY", "your-api-key-here"),
            "model_name": os.getenv("MODEL_NAME", "qwen-max"),
            "temperature": float(os.getenv("TEMPERATURE", "0.1")),
            "mongodb_url": os.getenv("MONGODB_URL", "mongodb://username:password@localhost:27017"),
            "mongodb_database": os.getenv("MONGODB_DATABASE", "api_logs"),
            "mongodb_collection": os.getenv("MONGODB_COLLECTION", "call_logs"),
            "log_enabled": os.getenv("LOG_ENABLED", "True").lower() == "true",
            "updated_at": datetime.now().isoformat()
        }
    
    def save_config(self):
        self.config['updated_at'] = datetime.now().isoformat()
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        self.apply_config()
    
    def update_config(self, new_config):
        self.config.update(new_config)
        self.save_config()
    
    def get_config(self):
        return self.config
    
    def apply_config(self):
        """应用配置到OpenAI"""
        openai.api_base = self.config.get('openai_api_url')
        openai.api_key = self.config.get('openai_api_key')

class ConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.configs = self.load_configs()
    
    def load_configs(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_configs(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.configs, f, ensure_ascii=False, indent=2)
    
    def add_config(self, name, config):
        config['created_at'] = datetime.now().isoformat()
        config['updated_at'] = datetime.now().isoformat()
        self.configs[name] = config
        self.save_configs()
    
    def update_config(self, name, config):
        if name in self.configs:
            config['created_at'] = self.configs[name].get('created_at', datetime.now().isoformat())
            config['updated_at'] = datetime.now().isoformat()
            self.configs[name] = config
            self.save_configs()
    
    def delete_config(self, name):
        if name in self.configs:
            del self.configs[name]
            self.save_configs()
    
    def get_config(self, name):
        return self.configs.get(name)
    
    def get_all_configs(self):
        return self.configs

config_manager = ConfigManager(CONFIG_FILE)
system_config_manager = SystemConfigManager(SYSTEM_CONFIG_FILE)
mongo_logger = MongoLogger(system_config_manager)

def call_openai_api(system_prompt, user_input):
    """调用OpenAI API"""
    try:
        config = system_config_manager.get_config()
        response = openai.ChatCompletion.create(
            model=config.get('model_name', 'qwen-max'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            temperature=config.get('temperature', 0.1)
        )
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"API调用失败: {str(e)}")

def extract_json_from_response(content):
    """从响应中提取JSON"""
    json_match = re.search(r'\{[\s\S]*?\}', content)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return None

# 主页
@app.route('/')
def index():
    return render_template('index.html', 
                         configs=config_manager.get_all_configs(),
                         system_config=system_config_manager.get_config())

# 系统配置页面
@app.route('/system-config')
def system_config_page():
    return render_template('system_config.html', config=system_config_manager.get_config())

# 更新系统配置
@app.route('/system-config/update', methods=['POST'])
def update_system_config():
    try:
        data = request.json
        system_config_manager.update_config(data)
        # 重新连接MongoDB
        mongo_logger.reconnect()
        return jsonify({'success': True, 'message': '系统配置更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

# 配置管理页面
@app.route('/config')
def config_page():
    return render_template('config.html', configs=config_manager.get_all_configs())

# 添加配置
@app.route('/config/add', methods=['GET', 'POST'])
def add_config():
    if request.method == 'POST':
        data = request.json
        name = data.get('name')
        if name and name not in config_manager.get_all_configs():
            config_manager.add_config(name, data)
            return jsonify({'success': True, 'message': '配置添加成功'})
        return jsonify({'success': False, 'message': '配置名称已存在或为空'})
    return render_template('add_config.html')

# 编辑配置
@app.route('/config/edit/<name>', methods=['GET', 'POST'])
def edit_config(name):
    if request.method == 'POST':
        data = request.json
        config_manager.update_config(name, data)
        return jsonify({'success': True, 'message': '配置更新成功'})
    
    config = config_manager.get_config(name)
    if not config:
        return redirect(url_for('config_page'))
    return render_template('edit_config.html', config=config, name=name)

# 删除配置
@app.route('/config/delete/<name>', methods=['POST'])
def delete_config(name):
    config_manager.delete_config(name)
    return jsonify({'success': True, 'message': '配置删除成功'})

# 测试页面
@app.route('/test')
def test_page():
    return render_template('test.html', configs=config_manager.get_all_configs())

# 动态API端点 - 支持原有路径格式
@app.route('/YiDiJiuYi/<path:endpoint>', methods=['POST'])
def legacy_api(endpoint):
    # 根据endpoint找到对应的配置
    target_path = f"/YiDiJiuYi/{endpoint}"
    config_name = None
    
    for name, config in config_manager.get_all_configs().items():
        if config.get('path') == target_path:
            config_name = name
            break
    
    if not config_name:
        return jsonify({'error': '接口不存在'}), 404
    
    return dynamic_api(config_name)

# 保留新的动态API端点（通过配置名称访问）
@app.route('/api/<config_name>', methods=['POST'])
def dynamic_api(config_name):
    start_time = datetime.now()
    config = config_manager.get_config(config_name)
    if not config or not config.get('enabled', True):
        return jsonify({'error': '接口不存在或已禁用'}), 404
    
    request_data = None
    response_data = None
    success = False
    error_message = None
    
    try:
        data = request.json
        request_data = data
        user_input = data.get('text', '')
        
        if not user_input:
            error_message = '输入文本不能为空'
            response_data = {'error': error_message}
            return jsonify(response_data), 400
        
        # 调用OpenAI API
        response_content = call_openai_api(config['system_prompt'], user_input)
        
        # 尝试解析JSON响应
        parsed_response = extract_json_from_response(response_content)
        
        if parsed_response:
            # 添加原始文本
            parsed_response['original_text'] = user_input
            response_data = parsed_response
        else:
            # 如果无法解析JSON，返回原始响应
            response_data = {
                'response': response_content,
                'original_text': user_input
            }
        
        success = True
        return jsonify(response_data)
    
    except Exception as e:
        error_message = str(e)
        response_data = {'error': error_message}
        return jsonify(response_data), 500
    
    finally:
        # 记录日志
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds() * 1000
        mongo_logger.log_api_call(
            config_name=config_name,
            request_data=request_data,
            response_data=response_data,
            success=success,
            error_message=error_message,
            execution_time=execution_time
        )

# 日志管理页面
@app.route('/logs')
def logs_page():
    return render_template('logs.html')

# 获取日志API
@app.route('/api/logs')
def get_logs():
    try:
        limit = int(request.args.get('limit', 100))
        skip = int(request.args.get('skip', 0))
        config_name = request.args.get('config_name')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # 转换日期
        if start_date:
            start_date = datetime.fromisoformat(start_date)
        if end_date:
            end_date = datetime.fromisoformat(end_date)
        
        logs = mongo_logger.get_logs(limit, skip, config_name, start_date, end_date)
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 获取统计信息API
@app.route('/api/logs/stats')
def get_log_stats():
    try:
        stats = mongo_logger.get_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 测试MongoDB连接
@app.route('/api/test-mongodb')
def test_mongodb():
    try:
        mongo_logger.reconnect()
        if mongo_logger.collection is not None:
            return jsonify({'success': True, 'message': 'MongoDB连接成功'})
        else:
            return jsonify({'success': False, 'message': 'MongoDB连接失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 获取所有配置的API
@app.route('/api/configs')
def get_configs():
    return jsonify(config_manager.get_all_configs())

# 获取系统配置的API
@app.route('/api/system-config')
def get_system_config():
    return jsonify(system_config_manager.get_config())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)