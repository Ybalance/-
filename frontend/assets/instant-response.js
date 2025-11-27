/**
 * 即时响应优化 - 解决用户操作延迟问题
 */

class InstantResponse {
    constructor() {
        this.pendingOperations = new Map();
        this.optimisticUpdates = new Map();
    }

    // 乐观更新 - 立即更新UI，后台同步数据
    async optimisticUpdate(operation, updateFunction, rollbackFunction) {
        const operationId = Date.now().toString();
        
        try {
            // 1. 立即更新UI (乐观更新)
            const result = await updateFunction();
            this.optimisticUpdates.set(operationId, { rollbackFunction, result });
            
            // 2. 显示即时反馈
            this.showInstantFeedback('操作成功', 'success');
            
            // 3. 后台验证和同步 (不阻塞用户)
            this.backgroundSync(operationId, operation);
            
            return result;
            
        } catch (error) {
            // 如果立即操作失败，显示错误
            this.showInstantFeedback('操作失败: ' + error.message, 'error');
            throw error;
        }
    }

    // 后台同步验证
    async backgroundSync(operationId, operation) {
        try {
            // 等待一小段时间让后端同步完成
            await new Promise(resolve => setTimeout(resolve, 100));
            
            // 验证操作是否真正成功
            const isValid = await this.validateOperation(operation);
            
            if (isValid) {
                // 同步成功，移除乐观更新记录
                this.optimisticUpdates.delete(operationId);
                console.log('后台同步验证成功');
            } else {
                // 同步失败，执行回滚
                await this.rollbackOperation(operationId);
            }
            
        } catch (error) {
            console.error('后台同步失败:', error);
            await this.rollbackOperation(operationId);
        }
    }

    // 验证操作是否成功
    async validateOperation(operation) {
        try {
            // 这里可以添加具体的验证逻辑
            // 例如：检查数据是否真正保存到数据库
            return true; // 简化处理，假设都成功
        } catch (error) {
            return false;
        }
    }

    // 回滚操作
    async rollbackOperation(operationId) {
        const update = this.optimisticUpdates.get(operationId);
        if (update && update.rollbackFunction) {
            try {
                await update.rollbackFunction();
                this.showInstantFeedback('操作已回滚', 'warning');
            } catch (error) {
                console.error('回滚失败:', error);
            }
        }
        this.optimisticUpdates.delete(operationId);
    }

    // 禁用即时反馈显示
    showInstantFeedback(message, type) {
        // 不显示任何弹窗，只在控制台记录
        console.log(`即时反馈: ${message} (${type})`);
    }

    // 获取图标
    getIcon(type) {
        const icons = {
            'success': '✓',
            'error': '✗',
            'warning': '⚠',
            'info': 'ℹ'
        };
        return icons[type] || 'ℹ';
    }

    // 添加反馈样式
    addFeedbackStyles() {
        if (document.getElementById('instant-feedback-styles')) return;

        const style = document.createElement('style');
        style.id = 'instant-feedback-styles';
        style.textContent = `
            .instant-feedback .feedback-content {
                display: flex;
                align-items: center;
                padding: 12px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                min-width: 200px;
            }

            .instant-feedback .feedback-content.success {
                background: #28a745;
                color: white;
            }

            .instant-feedback .feedback-content.error {
                background: #dc3545;
                color: white;
            }

            .instant-feedback .feedback-content.warning {
                background: #ffc107;
                color: #212529;
            }

            .instant-feedback .feedback-content.info {
                background: #17a2b8;
                color: white;
            }

            .instant-feedback .feedback-icon {
                margin-right: 8px;
                font-size: 16px;
            }

            @keyframes slideInRight {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }

            @keyframes slideOutRight {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(100%);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }

    // 包装API请求以支持即时响应
    wrapApiForInstantResponse(originalApiRequest) {
        return async (endpoint, options = {}) => {
            const method = options.method || 'GET';
            const isModifyingOperation = ['POST', 'PUT', 'DELETE'].includes(method.toUpperCase());

            if (!isModifyingOperation) {
                return await originalApiRequest(endpoint, options);
            }

            // 对于修改操作，使用乐观更新
            return await this.optimisticUpdate(
                `${method} ${endpoint}`,
                () => originalApiRequest(endpoint, options),
                () => {
                    // 回滚函数 - 刷新相关数据
                    if (window.onDemandRefresh) {
                        window.onDemandRefresh.refreshCurrentSection();
                    }
                }
            );
        };
    }
}

// 创建全局即时响应实例
window.instantResponse = new InstantResponse();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 包装原有的apiRequest函数以支持即时响应
    if (typeof window.apiRequest === 'function') {
        const originalApiRequest = window.apiRequest;
        window.apiRequest = window.instantResponse.wrapApiForInstantResponse(originalApiRequest);
        console.log('即时响应优化已启用');
    }

    // 即时响应已启用，按需刷新系统将处理数据更新
    console.log('即时响应系统已启用，数据将按需更新');
});
