import React, { useState, useContext } from 'react';
import { Form, Input, Button, Card, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

const LoginPage = () => {
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();
    const { login } = useContext(AuthContext);

    const onFinish = async (values) => {
        setLoading(true);
        try {
            // 注意：axios 在这里发送的是一个 application/x-www-form-urlencoded 请求
            // 这正是 FastAPI 的 OAuth2PasswordRequestForm 所期望的格式。
            const params = new URLSearchParams();
            params.append('username', values.username);
            params.append('password', values.password);

            const response = await axios.post('/auth/token', params, {
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            });

            const { access_token } = response.data;
            login(access_token); // 使用 context 中的 login 函数
            message.success('登录成功!');
            navigate('/app/chat'); // 登录成功后跳转到主页面
        } catch (error) {
            console.error('Login failed:', error);
            message.error(error.response?.data?.detail || '登录失败，请检查您的用户名和密码。');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: '#f0f2f5' }}>
            <Card title="欢迎登录 TagRAG 系统" style={{ width: 400 }}>
                <Form
                    name="normal_login"
                    className="login-form"
                    initialValues={{ remember: true }}
                    onFinish={onFinish}
                >
                    <Form.Item
                        name="username"
                        rules={[{ required: true, message: '请输入用户名!' }]}
                    >
                        <Input prefix={<UserOutlined className="site-form-item-icon" />} placeholder="用户名" />
                    </Form.Item>
                    <Form.Item
                        name="password"
                        rules={[{ required: true, message: '请输入密码!' }]}
                    >
                        <Input
                            prefix={<LockOutlined className="site-form-item-icon" />}
                            type="password"
                            placeholder="密码"
                        />
                    </Form.Item>
                    <Form.Item>
                        <Button type="primary" htmlType="submit" className="login-form-button" loading={loading} block>
                            登录
                        </Button>
                    </Form.Item>
                </Form>
            </Card>
        </div>
    );
};

export default LoginPage; 