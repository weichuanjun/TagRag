import os
import ast
import json
import re
from typing import List, Dict, Set, Any, Optional

class CodeAnalyzer:
    """代码分析器类，用于分析代码库并识别字段引用"""
    
    def __init__(self, output_directory: str):
        self.output_directory = output_directory
        os.makedirs(output_directory, exist_ok=True)
        
        # 存储字段引用关系
        self.field_references = {}
        
        # 索引文件路径
        self.index_path = os.path.join(output_directory, "code_index.json")
        
        # 加载现有索引
        self._load_index()
    
    def _load_index(self):
        """加载现有代码索引"""
        if os.path.exists(self.index_path):
            with open(self.index_path, 'r', encoding='utf-8') as f:
                self.field_references = json.load(f)
        else:
            self.field_references = {}
    
    def _save_index(self):
        """保存代码索引"""
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(self.field_references, f, ensure_ascii=False, indent=2)
    
    async def analyze_code(self, code_path: str):
        """分析代码目录并建立字段引用索引"""
        try:
            supported_extensions = [
                '.py', '.js', '.ts', '.tsx', '.jsx', 
                '.java', '.cpp', '.c', '.h', '.cs', 
                '.go', '.rb', '.php'
            ]
            
            # 清空现有索引
            self.field_references = {}
            
            # 递归扫描代码文件
            for root, _, files in os.walk(code_path):
                for file in files:
                    file_extension = os.path.splitext(file)[1].lower()
                    if file_extension in supported_extensions:
                        file_path = os.path.join(root, file)
                        self._analyze_file(file_path)
            
            # 保存索引
            self._save_index()
            
            return {
                "status": "success",
                "message": f"已分析代码库 {code_path}，找到 {len(self.field_references)} 个字段引用"
            }
            
        except Exception as e:
            print(f"分析代码时出错: {str(e)}")
            raise e
    
    def _analyze_file(self, file_path: str):
        """分析单个文件中的字段引用"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 根据文件类型使用不同的分析方法
            file_extension = os.path.splitext(file_path)[1].lower()
            
            if file_extension == '.py':
                self._analyze_python_file(file_path, content)
            elif file_extension in ['.js', '.ts', '.jsx', '.tsx']:
                self._analyze_js_file(file_path, content)
            elif file_extension in ['.java']:
                self._analyze_java_file(file_path, content)
            elif file_extension in ['.cpp', '.c', '.h']:
                self._analyze_c_file(file_path, content)
            else:
                # 通用分析方法（基于正则表达式）
                self._analyze_generic_file(file_path, content)
                
        except Exception as e:
            print(f"分析文件 {file_path} 时出错: {str(e)}")
    
    def _analyze_python_file(self, file_path: str, content: str):
        """分析Python文件中的字段引用"""
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    field_name = node.attr
                    if field_name not in self.field_references:
                        self.field_references[field_name] = []
                    
                    # 获取行号
                    line_num = getattr(node, 'lineno', 0)
                    reference = f"{file_path}:{line_num}"
                    
                    if reference not in self.field_references[field_name]:
                        self.field_references[field_name].append(reference)
                    
                elif isinstance(node, ast.Name):
                    field_name = node.id
                    if field_name not in self.field_references:
                        self.field_references[field_name] = []
                    
                    # 获取行号
                    line_num = getattr(node, 'lineno', 0)
                    reference = f"{file_path}:{line_num}"
                    
                    if reference not in self.field_references[field_name]:
                        self.field_references[field_name].append(reference)
        
        except SyntaxError:
            # 如果Python解析器无法解析文件，使用通用方法
            self._analyze_generic_file(file_path, content)
    
    def _analyze_js_file(self, file_path: str, content: str):
        """分析JavaScript/TypeScript文件中的字段引用"""
        # 属性访问模式: obj.property
        property_pattern = re.compile(r'(\w+)\.(\w+)')
        # 变量声明模式: var/let/const name = value
        var_pattern = re.compile(r'(var|let|const)\s+(\w+)')
        # 函数声明模式: function name()
        func_pattern = re.compile(r'function\s+(\w+)')
        # 类字段模式: this.field
        this_pattern = re.compile(r'this\.(\w+)')
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # 分析属性访问
            for match in property_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析变量声明
            for match in var_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析函数声明
            for match in func_pattern.finditer(line):
                field_name = match.group(1)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析类字段
            for match in this_pattern.finditer(line):
                field_name = match.group(1)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
    
    def _analyze_java_file(self, file_path: str, content: str):
        """分析Java文件中的字段引用"""
        # 字段声明模式: private/public/protected type name;
        field_pattern = re.compile(r'(private|public|protected)\s+\w+\s+(\w+)')
        # 方法声明模式: type name()
        method_pattern = re.compile(r'(private|public|protected)\s+\w+\s+(\w+)\s*\(')
        # 属性访问模式: obj.property
        property_pattern = re.compile(r'(\w+)\.(\w+)')
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # 分析字段声明
            for match in field_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析方法声明
            for match in method_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析属性访问
            for match in property_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
    
    def _analyze_c_file(self, file_path: str, content: str):
        """分析C/C++文件中的字段引用"""
        # 结构体字段模式: struct.field
        struct_field_pattern = re.compile(r'(\w+)\.(\w+)')
        # 指针字段模式: ptr->field
        pointer_field_pattern = re.compile(r'(\w+)->(\w+)')
        # 变量声明模式: type name;
        var_pattern = re.compile(r'(\w+)\s+(\w+)\s*;')
        # 函数声明模式: type name()
        func_pattern = re.compile(r'(\w+)\s+(\w+)\s*\(')
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # 分析结构体字段
            for match in struct_field_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析指针字段
            for match in pointer_field_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析变量声明
            for match in var_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
            
            # 分析函数声明
            for match in func_pattern.finditer(line):
                field_name = match.group(2)
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
    
    def _analyze_generic_file(self, file_path: str, content: str):
        """通用文件分析方法（基于正则表达式）"""
        # 标识符模式
        identifier_pattern = re.compile(r'\b(\w+)\b')
        
        lines = content.split('\n')
        for i, line in enumerate(lines):
            for match in identifier_pattern.finditer(line):
                field_name = match.group(1)
                
                # 忽略关键字和纯数字
                if (field_name.isdigit() or 
                    len(field_name) <= 1 or  # 忽略单字符标识符
                    field_name in ['if', 'else', 'for', 'while', 'return', 'true', 'false']):
                    continue
                
                if field_name not in self.field_references:
                    self.field_references[field_name] = []
                
                reference = f"{file_path}:{i+1}"
                if reference not in self.field_references[field_name]:
                    self.field_references[field_name].append(reference)
    
    async def get_field_impact(self, field_name: str) -> List[Dict[str, Any]]:
        """获取修改特定字段可能产生的影响"""
        results = []
        
        # 精确匹配
        if field_name in self.field_references:
            for reference in self.field_references[field_name]:
                file_path, line_num = reference.split(':')
                results.append({
                    "file_path": file_path,
                    "line_number": int(line_num),
                    "match_type": "exact"
                })
        
        # 部分匹配（字段名是查询的一部分）
        partial_matches = []
        for key in self.field_references:
            if field_name in key and key != field_name:
                for reference in self.field_references[key]:
                    file_path, line_num = reference.split(':')
                    partial_matches.append({
                        "file_path": file_path,
                        "line_number": int(line_num),
                        "field_name": key,
                        "match_type": "partial"
                    })
        
        # 添加部分匹配（最多10个）
        results.extend(partial_matches[:10])
        
        return results
    
    async def get_all_fields(self) -> List[str]:
        """获取所有字段名称列表"""
        return list(self.field_references.keys()) 