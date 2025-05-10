import React from 'react';
import { Typography, Collapse, Tag, Space, Card, Divider } from 'antd';
import { CodeOutlined, ExpandAltOutlined } from '@ant-design/icons';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import js from 'react-syntax-highlighter/dist/esm/languages/hljs/javascript';
import python from 'react-syntax-highlighter/dist/esm/languages/hljs/python';
import java from 'react-syntax-highlighter/dist/esm/languages/hljs/java';
import cpp from 'react-syntax-highlighter/dist/esm/languages/hljs/cpp';
import docco from 'react-syntax-highlighter/dist/esm/styles/hljs/docco';

// 注册语言
SyntaxHighlighter.registerLanguage('javascript', js);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('java', java);
SyntaxHighlighter.registerLanguage('cpp', cpp);

const { Text, Title } = Typography;
const { Panel } = Collapse;

/**
 * 代码搜索结果组件
 * @param {Object} props
 * @param {Array} props.codeSnippets - 代码片段列表
 */
const CodeRAGResults = ({ codeSnippets = [] }) => {
    if (!codeSnippets || codeSnippets.length === 0) {
        return null;
    }

    // 根据文件扩展名判断代码语言
    const getLanguage = (filePath) => {
        if (!filePath) return 'javascript';

        const extension = filePath.split('.').pop().toLowerCase();
        const languageMap = {
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
            'py': 'python',
            'java': 'java',
            'c': 'c',
            'cpp': 'cpp',
            'h': 'c',
            'go': 'go',
            'html': 'html',
            'css': 'css',
            'json': 'json',
            'md': 'markdown',
        };

        return languageMap[extension] || 'javascript';
    };

    return (
        <div style={{ marginTop: '15px', marginBottom: '15px' }}>
            <Text strong>
                <CodeOutlined style={{ marginRight: '5px' }} />
                相关代码片段
            </Text>
            <Divider style={{ margin: '8px 0' }} />

            <Collapse bordered={false} style={{ backgroundColor: 'transparent' }}>
                {codeSnippets.map((snippet, index) => (
                    <Panel
                        key={index}
                        header={
                            <Space>
                                <Text strong>{snippet.name || '未命名组件'}</Text>
                                <Tag color="blue">{snippet.type || '未知类型'}</Tag>
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    {snippet.file_path || '未知文件路径'}
                                    {snippet.start_line && snippet.end_line && ` (${snippet.start_line}-${snippet.end_line}行)`}
                                </Text>
                            </Space>
                        }
                    >
                        <Card size="small" bodyStyle={{ padding: '0', overflow: 'auto', maxHeight: '400px' }}>
                            <SyntaxHighlighter
                                language={getLanguage(snippet.file_path)}
                                style={docco}
                                showLineNumbers
                                startingLineNumber={snippet.start_line || 1}
                                wrapLines
                                lineProps={lineNumber => {
                                    const style = { display: 'block' };
                                    if (snippet.start_line &&
                                        snippet.signature &&
                                        lineNumber === snippet.start_line) {
                                        style.backgroundColor = 'rgba(255, 255, 0, 0.1)';
                                    }
                                    return { style };
                                }}
                            >
                                {snippet.code || '// 代码内容不可用'}
                            </SyntaxHighlighter>
                        </Card>
                        {snippet.signature && (
                            <div style={{ marginTop: '8px', padding: '8px', backgroundColor: '#f5f5f5', borderRadius: '4px' }}>
                                <Text code>{snippet.signature}</Text>
                            </div>
                        )}
                    </Panel>
                ))}
            </Collapse>
        </div>
    );
};

export default CodeRAGResults; 