/**
 * 实时数据同步管理器
 * 确保操作后立即更新数据库并刷新页面显示
 */

class RealtimeSync {
    constructor() {
        this.pendingOperations = new Set();
        this.syncCallbacks = new Map();
        this.isEnabled = true;
    }

    // 注册操作完成后的回调
    registerCallback(operation, callback) {
        if (!this.syncCallbacks.has(operation)) {
            this.syncCallbacks.set(operation, []);
        }
        this.syncCallbacks.get(operation).push(callback);
    }

    // 执行操作并触发实时同步
    async executeOperation(operationType, apiCall, refreshCallback) {
        if (!this.isEnabled) {
            return await apiCall();
        }

        const operationId = `${operationType}_${Date.now()}`;
        this.pendingOperations.add(operationId);

        try {
            // 显示操作进行中的状态
            this.showOperationStatus('进行中...', 'info');

            // 执行API调用
            const result = await apiCall();

            // 等待一小段时间确保后端同步完成
            await this.waitForSync();

            // 立即刷新相关数据
            if (refreshCallback) {
                await refreshCallback();
            }

            // 触发注册的回调
            await this.triggerCallbacks(operationType, result);

            // 显示成功状态
            this.showOperationStatus('操作成功，数据已更新', 'success');

            this.pendingOperations.delete(operationId);
            return result;

        } catch (error) {
            this.pendingOperations.delete(operationId);
            this.showOperationStatus('操作失败: ' + error.message, 'error');
            throw error;
        }
    }

    // 不等待同步，直接响应
    async waitForSync(timeout = 0) {
        // 不等待，直接返回，像SQLite一样即时响应
        return Promise.resolve();
    }

    // 触发回调函数
    async triggerCallbacks(operation, result) {
        const callbacks = this.syncCallbacks.get(operation) || [];
        for (const callback of callbacks) {
            try {
                await callback(result);
            } catch (error) {
                console.error('回调执行失败:', error);
            }
        }
    }

    // 禁用操作状态显示
    showOperationStatus(message, type) {
        // 不显示任何弹窗提示
        console.log(`操作状态: ${message} (${type})`);
    }

    // 包装API请求以支持实时同步
    wrapApiRequest(originalApiRequest) {
        return async (endpoint, options = {}) => {
            const method = options.method || 'GET';
            const isModifyingOperation = ['POST', 'PUT', 'DELETE'].includes(method.toUpperCase());

            if (!isModifyingOperation) {
                return await originalApiRequest(endpoint, options);
            }

            // 对于修改操作，使用实时同步
            const operationType = this.getOperationType(endpoint, method);
            
            return await this.executeOperation(
                operationType,
                () => originalApiRequest(endpoint, options),
                () => this.refreshRelevantData(operationType)
            );
        };
    }

    // 根据端点和方法确定操作类型
    getOperationType(endpoint, method) {
        const path = endpoint.toLowerCase();
        
        if (path.includes('registration')) {
            if (method === 'POST') return 'create_registration';
            if (method === 'DELETE' || path.includes('cancel')) return 'cancel_registration';
            if (method === 'PUT') return 'update_registration';
        }
        
        if (path.includes('patient')) {
            if (method === 'POST') return 'create_patient';
            if (method === 'PUT') return 'update_patient';
            if (method === 'DELETE') return 'delete_patient';
        }
        
        if (path.includes('doctor')) {
            if (method === 'POST') return 'create_doctor';
            if (method === 'PUT') return 'update_doctor';
            if (method === 'DELETE') return 'delete_doctor';
        }

        return 'general_operation';
    }

    // 刷新相关数据
    async refreshRelevantData(operationType) {
        try {
            switch (operationType) {
                case 'create_registration':
                case 'cancel_registration':
                case 'update_registration':
                    // 刷新挂号相关数据
                    if (typeof loadRegistrations === 'function') {
                        await loadRegistrations();
                    }
                    if (typeof loadDepartments === 'function') {
                        await loadDepartments();
                    }
                    break;

                case 'create_patient':
                case 'update_patient':
                case 'delete_patient':
                    // 刷新患者相关数据
                    if (typeof loadProfile === 'function') {
                        await loadProfile();
                    }
                    break;

                case 'create_doctor':
                case 'update_doctor':
                case 'delete_doctor':
                    // 刷新医生相关数据
                    if (typeof loadDoctors === 'function') {
                        await loadDoctors();
                    }
                    break;
            }

            // 触发按需刷新
            if (window.onDemandRefresh && typeof window.onDemandRefresh.refreshCurrentSection === 'function') {
                await window.onDemandRefresh.refreshCurrentSection();
            }

        } catch (error) {
            console.error('刷新数据失败:', error);
        }
    }

    // 启用/禁用实时同步
    setEnabled(enabled) {
        this.isEnabled = enabled;
        console.log('实时同步', enabled ? '已启用' : '已禁用');
    }

    // 检查是否有待处理的操作
    hasPendingOperations() {
        return this.pendingOperations.size > 0;
    }

    // 等待所有操作完成
    async waitForAllOperations(timeout = 10000) {
        const startTime = Date.now();
        
        while (this.hasPendingOperations() && (Date.now() - startTime) < timeout) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        return !this.hasPendingOperations();
    }
}

// 创建全局实时同步实例
window.realtimeSync = new RealtimeSync();

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 包装原有的apiRequest函数
    if (typeof window.apiRequest === 'function') {
        const originalApiRequest = window.apiRequest;
        window.apiRequest = window.realtimeSync.wrapApiRequest(originalApiRequest);
        console.log('实时同步已启用');
    } else if (typeof apiRequest === 'function') {
        const originalApiRequest = apiRequest;
        window.apiRequest = window.realtimeSync.wrapApiRequest(originalApiRequest);
        console.log('实时同步已启用');
    }

    // 注册常用操作的回调
    window.realtimeSync.registerCallback('create_registration', async () => {
        console.log('挂号创建完成，刷新相关数据');
    });

    window.realtimeSync.registerCallback('cancel_registration', async () => {
        console.log('挂号取消完成，刷新相关数据');
    });
});

// 为现有函数添加实时同步支持
function enhanceExistingFunctions() {
    // 增强挂号确认函数
    if (typeof confirmBooking === 'function') {
        const originalConfirmBooking = confirmBooking;
        window.confirmBooking = async function() {
            try {
                await originalConfirmBooking();
                // 操作完成后立即刷新
                setTimeout(async () => {
                    if (typeof loadRegistrations === 'function') {
                        await loadRegistrations();
                    }
                }, 500);
            } catch (error) {
                console.error('挂号确认失败:', error);
            }
        };
    }

    // 增强取消挂号函数
    if (typeof cancelRegistration === 'function') {
        const originalCancelRegistration = cancelRegistration;
        window.cancelRegistration = async function(regId) {
            try {
                await originalCancelRegistration(regId);
                // 操作完成后立即刷新
                setTimeout(async () => {
                    if (typeof loadRegistrations === 'function') {
                        await loadRegistrations();
                    }
                }, 500);
            } catch (error) {
                console.error('取消挂号失败:', error);
            }
        };
    }
}

// 延迟执行增强函数，确保原函数已加载
setTimeout(enhanceExistingFunctions, 1000);
