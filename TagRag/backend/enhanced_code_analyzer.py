import os
import ast
import re
import hashlib
import json
from typing import Dict, List, Any, Tuple, Set, Optional
import logging
from datetime import datetime

from sqlalchemy.orm import Session
from models import CodeRepository, CodeFile, CodeComponent, ComponentDependency
from langchain.schema import Document  # 添加Document导入

logger = logging.getLogger(__name__)

class EnhancedCodeAnalyzer:
    """增强版代码分析器，支持多语言分析和结构化索引"""
    
    # 支持的编程语言映射表
    SUPPORTED_LANGUAGES = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".go": "go"
    }
    
    def __init__(self, db_session: Session):
        """初始化代码分析器
        
        Args:
            db_session: SQLAlchemy会话对象，用于数据库操作
        """
        self.db_session = db_session
        self.current_repo = None
    
    async def analyze_repository(self, repo_path: str, repo_name: Optional[str] = None, knowledge_base_id: Optional[int] = None) -> int:
        """分析整个代码仓库
        
        Args:
            repo_path: 代码仓库路径
            repo_name: 仓库名称，默认使用目录名
            knowledge_base_id: 关联的知识库ID
            
        Returns:
            int: 仓库ID
            
        Raises:
            ValueError: 如果仓库路径不存在
        """
        if not os.path.exists(repo_path):
            raise ValueError(f"仓库路径不存在: {repo_path}")
            
        repo_name = repo_name or os.path.basename(os.path.normpath(repo_path))
        logger.info(f"开始分析仓库: {repo_name} 路径: {repo_path}")
        
        # 查找或创建仓库记录
        repo = self.db_session.query(CodeRepository).filter_by(
            path=repo_path
        ).first()
        
        if not repo:
            repo = CodeRepository(
                name=repo_name, 
                path=repo_path,
                knowledge_base_id=knowledge_base_id,
                last_analyzed=datetime.utcnow()
            )
            self.db_session.add(repo)
            self.db_session.commit()
        else:
            # 更新分析时间和知识库ID
            repo.last_analyzed = datetime.utcnow()
            if knowledge_base_id is not None:
                repo.knowledge_base_id = knowledge_base_id
                self.db_session.commit()
        
        self.current_repo = repo
        
        # 统计扫描文件数量
        file_count = 0
        component_count = 0
        
        # 扫描所有代码文件
        for root, _, files in os.walk(repo_path):
            for file in files:
                file_path = os.path.join(root, file)
                extension = os.path.splitext(file)[1].lower()
                
                # 只处理支持的语言
                if extension in self.SUPPORTED_LANGUAGES:
                    relative_path = os.path.relpath(file_path, repo_path)
                    try:
                        file_obj = await self._analyze_file(file_path, relative_path)
                        if file_obj:
                            file_count += 1
                            component_count += len(file_obj.components)
                    except Exception as e:
                        logger.error(f"分析文件 {file_path} 时出错: {str(e)}")
        
        logger.info(f"仓库分析完成. 分析了 {file_count} 个文件, {component_count} 个组件")
        
        # 分析组件间依赖关系
        await self._analyze_dependencies()
        
        # 计算组件重要性
        await self._calculate_importance_scores()
        
        self.db_session.commit()
        return repo.id
    
    async def _analyze_file(self, file_path: str, relative_path: str) -> Optional[CodeFile]:
        """分析单个文件，提取组件信息
        
        Args:
            file_path: 完整文件路径
            relative_path: 相对于仓库的路径
            
        Returns:
            CodeFile: 文件对象
        """
        # 计算文件哈希
        try:
            file_hash = self._calculate_file_hash(file_path)
        except:
            logger.warning(f"无法读取文件: {file_path}")
            return None
        
        # 查找文件记录
        code_file = self.db_session.query(CodeFile).filter_by(
            repository_id=self.current_repo.id,
            file_path=relative_path
        ).first()
        
        # 文件存在且未修改，则跳过
        if code_file and code_file.hash == file_hash:
            logger.debug(f"文件未变化，跳过: {relative_path}")
            return code_file
            
        # 获取文件内容和语言类型
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except:
            logger.warning(f"无法读取文件内容: {file_path}")
            return None
        
        extension = os.path.splitext(file_path)[1].lower()
        language = self.SUPPORTED_LANGUAGES.get(extension)
        
        # 创建或更新文件记录
        if not code_file:
            code_file = CodeFile(
                repository_id=self.current_repo.id,
                file_path=relative_path,
                language=language,
                hash=file_hash,
                last_modified=datetime.utcnow()
            )
            self.db_session.add(code_file)
        else:
            # 文件已修改，清除旧的组件
            for component in code_file.components:
                self.db_session.delete(component)
            code_file.hash = file_hash
            code_file.language = language
            code_file.last_modified = datetime.utcnow()
        
        self.db_session.commit()
        
        # 根据语言类型选择分析方法
        if language == "python":
            await self._analyze_python_file(code_file, content)
        elif language in ["javascript", "typescript"]:
            await self._analyze_js_file(code_file, content)
        elif language == "java":
            await self._analyze_java_file(code_file, content)
        elif language in ["c", "cpp"]:
            await self._analyze_c_file(code_file, content)
        elif language == "go":
            await self._analyze_go_file(code_file, content)
        else:
            # 通用方法
            await self._analyze_generic_file(code_file, content)
            
        return code_file
        
    async def _analyze_python_file(self, code_file: CodeFile, content: str):
        """分析Python文件，提取函数和类
        
        Args:
            code_file: 文件对象
            content: 文件内容
        """
        try:
            tree = ast.parse(content)
            
            # 获取文件行
            content_lines = content.split('\n')
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # 获取函数代码
                    start_line = node.lineno - 1  # 转为0索引
                    end_line = getattr(node, 'end_lineno', start_line + 10) - 1
                    end_line = min(end_line, len(content_lines) - 1)
                    func_code = '\n'.join(content_lines[start_line:end_line+1])
                    
                    # 提取函数签名
                    args = []
                    for arg in node.args.args:
                        args.append(getattr(arg, 'arg', ''))
                    signature = f"def {node.name}({', '.join(args)})"
                    
                    # 提取文档字符串
                    docstring = ast.get_docstring(node) or ""
                    
                    # 计算复杂度
                    complexity = self._calculate_python_complexity(node)
                    
                    # 创建组件记录
                    component = CodeComponent(
                        repository_id=self.current_repo.id,
                        file_id=code_file.id,
                        name=node.name,
                        type="function",
                        start_line=node.lineno,
                        end_line=getattr(node, 'end_lineno', node.lineno + 10),
                        code=func_code,
                        signature=signature,
                        complexity=complexity,
                        component_metadata={
                            "args": args,
                            "docstring": docstring,
                            "returns": self._get_python_return_hints(node)
                        }
                    )
                    self.db_session.add(component)
                
                elif isinstance(node, ast.ClassDef):
                    # 获取类代码
                    start_line = node.lineno - 1
                    end_line = getattr(node, 'end_lineno', start_line + 20) - 1
                    end_line = min(end_line, len(content_lines) - 1)
                    class_code = '\n'.join(content_lines[start_line:end_line+1])
                    
                    # 提取基类
                    bases = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            bases.append(base.id)
                    
                    # 提取文档字符串
                    docstring = ast.get_docstring(node) or ""
                    
                    # 创建类组件
                    class_component = CodeComponent(
                        repository_id=self.current_repo.id,
                        file_id=code_file.id,
                        name=node.name,
                        type="class",
                        start_line=node.lineno,
                        end_line=getattr(node, 'end_lineno', node.lineno + 20),
                        code=class_code,
                        signature=f"class {node.name}({', '.join(bases)})",
                        complexity=2.0,  # 类默认比函数复杂
                        component_metadata={
                            "bases": bases,
                            "docstring": docstring
                        }
                    )
                    self.db_session.add(class_component)
                    
                    # 分析类方法
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            # 获取方法代码
                            start_line = item.lineno - 1
                            end_line = getattr(item, 'end_lineno', start_line + 10) - 1
                            end_line = min(end_line, len(content_lines) - 1)
                            method_code = '\n'.join(content_lines[start_line:end_line+1])
                            
                            # 提取方法签名
                            args = []
                            for arg in item.args.args:
                                arg_name = getattr(arg, 'arg', '')
                                if arg_name != 'self':  # 排除self参数
                                    args.append(arg_name)
                            signature = f"def {item.name}(self, {', '.join(args)})"
                            
                            # 创建方法组件
                            method_component = CodeComponent(
                                repository_id=self.current_repo.id,
                                file_id=code_file.id,
                                name=f"{node.name}.{item.name}",
                                type="method",
                                start_line=item.lineno,
                                end_line=getattr(item, 'end_lineno', item.lineno + 10),
                                code=method_code,
                                signature=signature,
                                complexity=self._calculate_python_complexity(item),
                                component_metadata={
                                    "class": node.name,
                                    "args": args,
                                    "docstring": ast.get_docstring(item) or "",
                                    "returns": self._get_python_return_hints(item)
                                }
                            )
                            self.db_session.add(method_component)
            
            self.db_session.commit()
                            
        except SyntaxError as e:
            logger.warning(f"Python语法错误 {code_file.file_path}: {str(e)}")
            # 降级为通用分析
            await self._analyze_generic_file(code_file, content)
    
    async def _analyze_js_file(self, code_file: CodeFile, content: str):
        """分析JavaScript/TypeScript文件
        
        Args:
            code_file: 文件对象
            content: 文件内容
        """
        # 函数定义模式
        function_pattern = re.compile(r'(?:function\s+(\w+)\s*\(([^)]*)\)|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\([^)]*\)\s*=>))')
        # 类定义模式
        class_pattern = re.compile(r'class\s+(\w+)(?:\s+extends\s+(\w+))?')
        # 方法定义模式
        method_pattern = re.compile(r'(\w+)\s*\(([^)]*)\)\s*{')
        # React组件模式
        react_component_pattern = re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*\((?:props|{[^}]*})\)\s*=>')
        
        lines = content.split('\n')
        
        # 处理函数和变量
        for i, line in enumerate(lines):
            # 函数定义
            for match in function_pattern.finditer(line):
                func_name = match.group(1) or match.group(3)
                if not func_name:
                    continue
                    
                # 寻找函数体结束
                start_line = i + 1
                end_line = self._find_js_block_end(lines, start_line)
                
                if end_line > start_line:
                    func_code = '\n'.join(lines[i:end_line+1])
                    
                    component = CodeComponent(
                        repository_id=self.current_repo.id,
                        file_id=code_file.id,
                        name=func_name,
                        type="function",
                        start_line=i + 1,
                        end_line=end_line + 1,
                        code=func_code,
                        signature=line.strip(),
                        complexity=1.0
                    )
                    self.db_session.add(component)
            
            # React组件
            for match in react_component_pattern.finditer(line):
                component_name = match.group(1)
                if not component_name:
                    continue
                    
                # 寻找组件体结束
                start_line = i + 1
                end_line = self._find_js_block_end(lines, start_line)
                
                if end_line > start_line:
                    component_code = '\n'.join(lines[i:end_line+1])
                    
                    component = CodeComponent(
                        repository_id=self.current_repo.id,
                        file_id=code_file.id,
                        name=component_name,
                        type="react_component",
                        start_line=i + 1,
                        end_line=end_line + 1,
                        code=component_code,
                        signature=line.strip(),
                        complexity=1.5
                    )
                    self.db_session.add(component)
            
            # 类定义
            for match in class_pattern.finditer(line):
                class_name = match.group(1)
                base_class = match.group(2) or ""
                
                start_line = i + 1
                end_line = self._find_js_block_end(lines, start_line)
                
                if end_line > start_line:
                    class_code = '\n'.join(lines[i:end_line+1])
                    
                    component = CodeComponent(
                        repository_id=self.current_repo.id,
                        file_id=code_file.id,
                        name=class_name,
                        type="class",
                        start_line=i + 1,
                        end_line=end_line + 1,
                        code=class_code,
                        signature=line.strip(),
                        component_metadata={"base_class": base_class}
                    )
                    self.db_session.add(component)
        
        self.db_session.commit()
    
    async def _analyze_java_file(self, code_file: CodeFile, content: str):
        """分析Java文件，仅实现基本分析功能"""
        # 简单实现，专注于识别类和方法
        class_pattern = re.compile(r'(public|private|protected)?\s*class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?')
        method_pattern = re.compile(r'(public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(([^)]*)\)')
        
        lines = content.split('\n')
        current_class = None
        
        for i, line in enumerate(lines):
            # 类定义
            class_match = class_pattern.search(line)
            if class_match:
                class_name = class_match.group(2)
                current_class = class_name
                
                # 查找类结束位置
                j = i
                open_braces = 0
                found_open = False
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            found_open = True
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                            if found_open and open_braces == 0:
                                break
                    
                    if found_open and open_braces == 0:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                class_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=class_name,
                    type="class",
                    start_line=i + 1,
                    end_line=end_line,
                    code=class_code,
                    signature=line.strip(),
                    complexity=2.0
                )
                self.db_session.add(component)
            
            # 方法定义
            method_match = method_pattern.search(line)
            if method_match:
                method_name = method_match.group(2)
                
                # 方法结束位置查找类似于类
                j = i
                open_braces = 0
                found_open = False
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            found_open = True
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                            if found_open and open_braces == 0:
                                break
                    
                    if found_open and open_braces == 0:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                method_code = '\n'.join(lines[i:end_line])
                
                full_name = f"{current_class}.{method_name}" if current_class else method_name
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=full_name,
                    type="method" if current_class else "function",
                    start_line=i + 1,
                    end_line=end_line,
                    code=method_code,
                    signature=line.strip(),
                    complexity=1.5
                )
                self.db_session.add(component)
        
        self.db_session.commit()
    
    async def _analyze_c_file(self, code_file: CodeFile, content: str):
        """分析C/C++文件，基本实现"""
        # 函数模式
        function_pattern = re.compile(r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*{')
        # 结构体/类模式
        struct_pattern = re.compile(r'(struct|class)\s+(\w+)(?:\s*:\s*(?:public|protected|private)\s+\w+)?')
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # 查找函数
            func_match = function_pattern.search(line)
            if func_match:
                return_type = func_match.group(1)
                func_name = func_match.group(2)
                
                # 跳过main函数和C++关键字
                if func_name in ['if', 'for', 'while', 'switch', 'return']:
                    continue
                
                # 查找函数结束
                j = i
                open_braces = 0
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                            if open_braces == 0:
                                break
                    
                    if open_braces == 0:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                func_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=func_name,
                    type="function",
                    start_line=i + 1,
                    end_line=end_line,
                    code=func_code,
                    signature=line.strip(),
                    complexity=1.0
                )
                self.db_session.add(component)
            
            # 查找结构体/类
            struct_match = struct_pattern.search(line)
            if struct_match:
                struct_type = struct_match.group(1)
                struct_name = struct_match.group(2)
                
                j = i
                open_braces = 0
                found_open = False
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            found_open = True
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                            if found_open and open_braces == 0:
                                break
                    
                    if found_open and open_braces == 0:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                struct_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=struct_name,
                    type=struct_type,  # "struct" 或 "class"
                    start_line=i + 1,
                    end_line=end_line,
                    code=struct_code,
                    signature=line.strip(),
                    complexity=1.5
                )
                self.db_session.add(component)
        
        self.db_session.commit()
    
    async def _analyze_go_file(self, code_file: CodeFile, content: str):
        """分析Go语言文件，提取函数、结构体和方法"""
        # 包名模式
        package_pattern = re.compile(r'package\s+(\w+)')
        # 导入模式
        import_pattern = re.compile(r'import\s+\(\s*(.*?)\s*\)', re.DOTALL)
        # 函数定义模式
        function_pattern = re.compile(r'func\s+(\w+)\s*\(([^)]*)\)')
        # 结构体定义模式
        struct_pattern = re.compile(r'type\s+(\w+)\s+struct\s*{')
        # 接口定义模式
        interface_pattern = re.compile(r'type\s+(\w+)\s+interface\s*{')
        # 方法定义模式（带接收器）
        method_pattern = re.compile(r'func\s+\((\w+)\s+[*]?(\w+)\)\s+(\w+)\s*\(([^)]*)\)')
        
        # 获取文件行
        lines = content.split('\n')
        
        # 当前包名
        package_name = None
        
        # 提取包名
        for line in lines:
            package_match = package_pattern.search(line)
            if package_match:
                package_name = package_match.group(1)
                break
        
        # 逐行分析
        for i, line in enumerate(lines):
            # 分析函数
            func_match = function_pattern.search(line)
            if func_match and "func (" not in line:  # 排除方法定义
                func_name = func_match.group(1)
                
                # 跳过main函数
                if func_name == "init" or func_name == "main":
                    continue
                
                # 查找函数结束位置
                j = i
                open_braces = 0
                found_open = False
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            found_open = True
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                    
                    if found_open and open_braces == 0:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                func_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=func_name,
                    type="function",
                    start_line=i + 1,
                    end_line=end_line,
                    code=func_code,
                    signature=line.strip(),
                    complexity=1.0,
                    component_metadata={
                        "package": package_name,
                        "is_exported": func_name[0].isupper()
                    }
                )
                self.db_session.add(component)
            
            # 分析结构体
            struct_match = struct_pattern.search(line)
            if struct_match:
                struct_name = struct_match.group(1)
                
                # 查找结构体结束位置
                j = i
                open_braces = 0
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                    
                    if open_braces == 0 and j > i:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                struct_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=struct_name,
                    type="struct",
                    start_line=i + 1,
                    end_line=end_line,
                    code=struct_code,
                    signature=line.strip(),
                    complexity=1.5,
                    component_metadata={
                        "package": package_name,
                        "is_exported": struct_name[0].isupper()
                    }
                )
                self.db_session.add(component)
            
            # 分析接口
            interface_match = interface_pattern.search(line)
            if interface_match:
                interface_name = interface_match.group(1)
                
                # 查找接口结束位置
                j = i
                open_braces = 0
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                    
                    if open_braces == 0 and j > i:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                interface_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=interface_name,
                    type="interface",
                    start_line=i + 1,
                    end_line=end_line,
                    code=interface_code,
                    signature=line.strip(),
                    complexity=1.2,
                    component_metadata={
                        "package": package_name,
                        "is_exported": interface_name[0].isupper()
                    }
                )
                self.db_session.add(component)
            
            # 分析方法
            method_match = method_pattern.search(line)
            if method_match:
                receiver_name = method_match.group(1)
                receiver_type = method_match.group(2)
                method_name = method_match.group(3)
                
                # 查找方法结束位置
                j = i
                open_braces = 0
                found_open = False
                
                while j < len(lines):
                    for char in lines[j]:
                        if char == '{':
                            found_open = True
                            open_braces += 1
                        elif char == '}':
                            open_braces -= 1
                    
                    if found_open and open_braces == 0:
                        break
                    j += 1
                
                end_line = min(j + 1, len(lines))
                method_code = '\n'.join(lines[i:end_line])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=f"{receiver_type}.{method_name}",
                    type="method",
                    start_line=i + 1,
                    end_line=end_line,
                    code=method_code,
                    signature=line.strip(),
                    complexity=1.0,
                    component_metadata={
                        "package": package_name,
                        "receiver": receiver_name,
                        "receiver_type": receiver_type,
                        "is_exported": method_name[0].isupper()
                    }
                )
                self.db_session.add(component)
        
        self.db_session.commit()
    
    async def _analyze_generic_file(self, code_file: CodeFile, content: str):
        """通用文件分析方法，使用简单的正则表达式"""
        # 通用函数模式
        function_pattern = re.compile(r'(?:function|def|func|public|private|protected)\s+(\w+)\s*\(')
        # 通用类/结构体模式
        class_pattern = re.compile(r'(?:class|struct|interface)\s+(\w+)')
        
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            # 通用函数查找
            for match in function_pattern.finditer(line):
                func_name = match.group(1)
                
                # 尝试找到函数结束位置（简单估计）
                end_line = min(i + 15, len(lines) - 1)  # 估计函数长度不超过15行
                j = i
                
                while j < end_line:
                    if j + 1 < len(lines) and re.search(r'^\s*}', lines[j + 1]):
                        end_line = j + 1
                        break
                    j += 1
                
                func_code = '\n'.join(lines[i:end_line+1])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=func_name,
                    type="function",
                    start_line=i + 1,
                    end_line=end_line + 1,
                    code=func_code,
                    complexity=1.0
                )
                self.db_session.add(component)
            
            # 通用类/结构体查找
            for match in class_pattern.finditer(line):
                class_name = match.group(1)
                
                # 尝试找到类结束位置（简单估计）
                end_line = min(i + 30, len(lines) - 1)  # 估计类长度不超过30行
                j = i
                
                while j < end_line:
                    if j + 1 < len(lines) and re.search(r'^\s*}', lines[j + 1]):
                        end_line = j + 1
                        break
                    j += 1
                
                class_code = '\n'.join(lines[i:end_line+1])
                
                component = CodeComponent(
                    repository_id=self.current_repo.id,
                    file_id=code_file.id,
                    name=class_name,
                    type="class",
                    start_line=i + 1,
                    end_line=end_line + 1,
                    code=class_code,
                    complexity=1.5
                )
                self.db_session.add(component)
        
        self.db_session.commit()
    
    def _find_js_block_end(self, lines, start_line):
        """查找JavaScript代码块结束位置
        
        Args:
            lines: 代码行列表
            start_line: 起始行索引
            
        Returns:
            int: 结束行索引
        """
        brace_count = 0
        in_block = False
        
        for i in range(start_line, len(lines)):
            line = lines[i]
            
            # 计算花括号
            for char in line:
                if char == '{':
                    in_block = True
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
            
            # 代码块结束
            if in_block and brace_count == 0:
                return i
        
        return min(start_line + 10, len(lines) - 1)  # 默认返回
    
    async def _analyze_dependencies(self):
        """分析组件间的依赖关系"""
        components = self.db_session.query(CodeComponent).filter_by(
            repository_id=self.current_repo.id
        ).all()
        
        # 创建名称到组件ID的映射
        name_to_id = {comp.name: comp.id for comp in components}
        
        # 分析每个组件内部的引用
        for component in components:
            if not component.code:
                continue
                
            # 查找组件代码中引用的其他组件
            for other_name, other_id in name_to_id.items():
                if other_name == component.name:  # 跳过自身引用
                    continue
                    
                # 简单字符串匹配方式查找依赖
                if re.search(r'\b' + re.escape(other_name) + r'\b', component.code):
                    # 检查是否已存在此依赖
                    existing = self.db_session.query(ComponentDependency).filter_by(
                        source_id=component.id,
                        target_id=other_id
                    ).first()
                    
                    if not existing:
                        dependency = ComponentDependency(
                            source_id=component.id,
                            target_id=other_id,
                            dependency_type="reference"
                        )
                        self.db_session.add(dependency)
        
        self.db_session.commit()
    
    async def _calculate_importance_scores(self):
        """计算组件重要性评分"""
        components = self.db_session.query(CodeComponent).filter_by(
            repository_id=self.current_repo.id
        ).all()
        
        for component in components:
            # 依赖因子: 被其他组件依赖的数量
            dependent_count = len(component.dependents)
            
            # 复杂度因子
            complexity = component.complexity or 1.0
            
            # 组件大小因子
            size = component.end_line - component.start_line
            
            # 类型因子（类比函数重要）
            type_factor = 1.5 if component.type == "class" else 1.0
            
            # 计算重要性得分
            importance = (dependent_count * 0.5 + 
                         complexity * 0.3 + 
                         size * 0.1) * type_factor
            
            component.importance_score = importance
        
        self.db_session.commit()
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        hasher = hashlib.md5()
        with open(file_path, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    
    def _calculate_python_complexity(self, node) -> float:
        """计算Python代码复杂度"""
        complexity = 1.0
        
        # 递归计算条件语句和循环
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While)):
                complexity += 0.1
            elif isinstance(child, ast.Try):
                complexity += 0.2
        
        return complexity
    
    def _get_python_return_hints(self, node) -> List[str]:
        """获取Python函数返回类型提示"""
        returns = []
        
        # 查找return语句
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value:
                if isinstance(child.value, ast.Name):
                    returns.append(child.value.id)
                elif isinstance(child.value, ast.Constant):
                    returns.append(str(type(child.value.value).__name__))
        
        return returns
    
    # 新增功能：将代码组件转换为文档对象，用于向量存储
    async def convert_components_to_documents(self, repo_id: int) -> List[Document]:
        """将代码组件转换为文档对象，以便存储到向量数据库
        
        Args:
            repo_id: 代码库ID
            
        Returns:
            List[Document]: 文档对象列表
        """
        logger.info(f"开始将仓库 {repo_id} 的代码组件转换为向量文档...")
        documents = []
        
        try:
            # 获取代码库所有组件
            components = self.db_session.query(CodeComponent).join(
                CodeFile, CodeComponent.file_id == CodeFile.id
            ).filter(
                CodeFile.repository_id == repo_id
            ).all()
            
            logger.info(f"找到 {len(components)} 个代码组件")
            
            for component in components:
                # 获取组件对应的文件
                file = self.db_session.query(CodeFile).filter(CodeFile.id == component.file_id).first()
                if not file:
                    logger.warning(f"组件 {component.id} 的文件记录丢失，跳过")
                    continue
                
                # 构建文档内容：包括组件代码和相关信息
                # 确保有可搜索的上下文
                content_parts = []
                
                # 添加组件名称和类型
                content_parts.append(f"组件名称: {component.name}")
                content_parts.append(f"组件类型: {component.type}")
                
                # 添加组件签名（如果有）
                if component.signature:
                    content_parts.append(f"签名: {component.signature}")
                
                # 添加组件元数据（如果有）
                if component.component_metadata:
                    # 将元数据转为字符串
                    try:
                        if isinstance(component.component_metadata, dict):
                            for key, value in component.component_metadata.items():
                                if key == "docstring" and value:
                                    content_parts.append(f"文档: {value}")
                                elif key == "args" and value:
                                    content_parts.append(f"参数: {', '.join(value)}")
                                elif key == "returns" and value:
                                    content_parts.append(f"返回: {', '.join(value)}")
                    except:
                        pass
                
                # 添加代码本身
                if component.code:
                    content_parts.append(f"\n代码:\n{component.code}")
                else:
                    logger.warning(f"组件 {component.id} ({component.name}) 没有代码内容，跳过")
                    continue  # 如果没有代码，跳过此组件
                
                # 合并所有内容部分
                full_content = "\n".join(content_parts)
                
                # 构建元数据
                metadata = {
                    "component_id": component.id,
                    "component_name": component.name,
                    "component_type": component.type,
                    "file_id": component.file_id,
                    "file_path": file.file_path,
                    "language": file.language,
                    "repository_id": repo_id,
                    "content_type": "code",  # 标记为代码文档
                    "importance": component.importance_score or 0.0,
                    "complexity": component.complexity or 0.0,
                    "start_line": component.start_line,
                    "end_line": component.end_line
                }
                
                # 创建文档对象
                doc = Document(
                    page_content=full_content,
                    metadata=metadata
                )
                documents.append(doc)
                
            logger.info(f"成功转换 {len(documents)} 个代码组件为文档对象")
            return documents
            
        except Exception as e:
            logger.error(f"转换代码组件为文档时出错: {str(e)}")
            return []

    # 新增功能：分析代码并存储到向量数据库
    async def analyze_and_vectorize_repository(self, repo_path: str, repo_name: Optional[str] = None, 
                                             knowledge_base_id: Optional[int] = None) -> Dict[str, Any]:
        """分析代码库并将组件存储到向量数据库
        
        Args:
            repo_path: 代码仓库路径
            repo_name: 仓库名称，默认使用目录名
            knowledge_base_id: 关联的知识库ID
            
        Returns:
            Dict: 处理结果
        """
        try:
            # 1. 分析代码库
            repo_id = await self.analyze_repository(repo_path, repo_name, knowledge_base_id)
            
            # 2. 将代码组件转换为可向量化的文档
            documents = await self.convert_components_to_documents(repo_id)
            
            if not documents:
                return {
                    "status": "warning",
                    "repository_id": repo_id,
                    "message": f"分析成功但没有生成可向量化的文档",
                    "document_count": 0
                }
            
            # 3. 返回文档，由调用者存储到向量数据库
            # 不在这里直接存储，避免循环依赖
            return {
                "status": "success",
                "repository_id": repo_id,
                "message": f"代码库分析完成，生成了 {len(documents)} 个文档",
                "documents": documents,
                "document_count": len(documents)
            }
            
        except Exception as e:
            logger.error(f"分析和向量化代码库时出错: {str(e)}")
            return {
                "status": "error",
                "message": f"处理失败: {str(e)}",
                "document_count": 0
            } 