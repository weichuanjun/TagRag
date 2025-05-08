import React, { useState, useEffect } from 'react';
import { Table, Card, Button, Typography, Tag, Space, Modal, Form, Input, message, Tooltip, Popconfirm, Select, ColorPicker } from 'antd';
import { PlusOutlined, DeleteOutlined, TagOutlined, EditOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;
const { Option } = Select;

const colorOptions = [
    "#1890ff", "#52c41a", "#faad14", "#f5222d", "#722ed1", "#13c2c2", "#eb2f96"
];

const TagManagementPage = () => {
    const [tags, setTags] = useState([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingTag, setEditingTag] = useState(null);
    const [form] = Form.useForm();
    const [parentTags, setParentTags] = useState([]);
    const [selectedColor, setSelectedColor] = useState("#1890ff");

    // 获取标签列表
    const fetchTags = async () => {
        setLoading(true);
        try {
            const response = await axios.get('/tags');
            // 按照层级排序
            const tagList = response.data.tags || [];
            setTags(tagList);

            // 提取可作为父标签的标签
            setParentTags(tagList.filter(tag => !tag.parent_id));
        } catch (error) {
            console.error('获取标签列表失败:', error);
            message.error('获取标签列表失败');
        } finally {
            setLoading(false);
        }
    };

    // 组件加载时获取标签列表
    useEffect(() => {
        fetchTags();
    }, []);

    // 打开添加标签模态框
    const showAddModal = () => {
        setEditingTag(null);
        form.resetFields();
        setSelectedColor("#1890ff");
        setModalVisible(true);
    };

    // 打开编辑标签模态框
    const showEditModal = (tag) => {
        setEditingTag(tag);
        form.setFieldsValue({
            name: tag.name,
            description: tag.description,
            parent_id: tag.parent_id,
        });
        setSelectedColor(tag.color || "#1890ff");
        setModalVisible(true);
    };

    // 处理模态框取消
    const handleCancel = () => {
        setModalVisible(false);
    };

    // 处理标签添加/编辑提交
    const handleSubmit = async () => {
        try {
            const values = await form.validateFields();

            // 添加颜色
            values.color = selectedColor;

            if (editingTag) {
                // 编辑现有标签
                await axios.put(`/tags/${editingTag.id}`, values);
                message.success('标签更新成功');
            } else {
                // 添加新标签
                await axios.post('/tags', values);
                message.success('标签添加成功');
            }

            setModalVisible(false);
            fetchTags();
        } catch (error) {
            console.error('提交标签失败:', error);
            message.error('提交标签失败');
        }
    };

    // 处理标签删除
    const handleDelete = async (tagId) => {
        try {
            await axios.delete(`/tags/${tagId}`);
            message.success('标签删除成功');
            fetchTags();
        } catch (error) {
            console.error('删除标签失败:', error);
            message.error('删除标签失败');
        }
    };

    // 表格列定义
    const columns = [
        {
            title: '标签',
            dataIndex: 'name',
            key: 'name',
            render: (text, record) => (
                <Tag color={record.color || '#1890ff'} style={{ fontSize: '14px', padding: '2px 8px' }}>
                    {text}
                </Tag>
            ),
        },
        {
            title: '描述',
            dataIndex: 'description',
            key: 'description',
        },
        {
            title: '父标签',
            dataIndex: 'parent_id',
            key: 'parent_id',
            render: (parentId) => {
                if (!parentId) return '-';
                const parent = tags.find(tag => tag.id === parentId);
                return parent ? (
                    <Tag color={parent.color || '#1890ff'}>
                        {parent.name}
                    </Tag>
                ) : '-';
            }
        },
        {
            title: '操作',
            key: 'action',
            render: (_, record) => (
                <Space size="middle">
                    <Tooltip title="编辑标签">
                        <Button
                            type="text"
                            icon={<EditOutlined />}
                            onClick={() => showEditModal(record)}
                        />
                    </Tooltip>
                    <Popconfirm
                        title="确定要删除这个标签吗？"
                        onConfirm={() => handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Tooltip title="删除标签">
                            <Button
                                type="text"
                                danger
                                icon={<DeleteOutlined />}
                            />
                        </Tooltip>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div>
            <Title level={4}>标签管理</Title>
            <Text type="secondary">
                管理系统中的标签，用于对文档和代码进行分类
            </Text>

            <Card style={{ marginTop: 16 }}
                extra={
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={showAddModal}
                    >
                        添加标签
                    </Button>
                }>
                <Table
                    columns={columns}
                    dataSource={tags}
                    rowKey="id"
                    loading={loading}
                    pagination={{ pageSize: 10 }}
                />
            </Card>

            {/* 添加/编辑标签模态框 */}
            <Modal
                title={editingTag ? "编辑标签" : "添加标签"}
                open={modalVisible}
                onOk={handleSubmit}
                onCancel={handleCancel}
                okText="保存"
                cancelText="取消"
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="name"
                        label="标签名称"
                        rules={[{ required: true, message: '请输入标签名称' }]}
                    >
                        <Input prefix={<TagOutlined />} placeholder="输入标签名称" />
                    </Form.Item>

                    <Form.Item
                        name="description"
                        label="描述"
                    >
                        <Input.TextArea placeholder="标签描述（可选）" />
                    </Form.Item>

                    <Form.Item
                        name="parent_id"
                        label="父标签"
                    >
                        <Select placeholder="选择父标签（可选）" allowClear>
                            {parentTags.map(tag => (
                                <Option key={tag.id} value={tag.id}>
                                    <Tag color={tag.color}>{tag.name}</Tag>
                                </Option>
                            ))}
                        </Select>
                    </Form.Item>

                    <Form.Item label="标签颜色">
                        <div style={{ display: 'flex', gap: '8px' }}>
                            {colorOptions.map(color => (
                                <div
                                    key={color}
                                    onClick={() => setSelectedColor(color)}
                                    style={{
                                        width: '24px',
                                        height: '24px',
                                        borderRadius: '4px',
                                        backgroundColor: color,
                                        cursor: 'pointer',
                                        border: selectedColor === color ? '2px solid #000' : '1px solid #d9d9d9'
                                    }}
                                />
                            ))}
                        </div>
                    </Form.Item>
                </Form>
            </Modal>
        </div>
    );
};

export default TagManagementPage; 