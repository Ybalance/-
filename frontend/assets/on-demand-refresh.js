/**
 * 按需刷新机制 - 只在用户操作时刷新数据
 */

class OnDemandRefresh {
    constructor() {
        this.isRefreshing = false;
        this.lastRefreshTime = new Map(); // 记录每个section的最后刷新时间
        this.refreshCooldown = 0; // 移除冷却时间，直接响应
    }

    // 检查是否需要刷新
    shouldRefresh(sectionName) {
        const lastTime = this.lastRefreshTime.get(sectionName) || 0;
        const now = Date.now();
        return (now - lastTime) > this.refreshCooldown;
    }

    // 记录刷新时间
    recordRefresh(sectionName) {
        this.lastRefreshTime.set(sectionName, Date.now());
    }

    // 用户操作后刷新
    async refreshAfterUserAction(actionType, targetSection = null) {
        if (this.isRefreshing) {
            console.log('正在刷新中，跳过重复刷新');
            return;
        }

        this.isRefreshing = true;

        try {
            console.log(`用户操作后刷新: ${actionType}`);

            // 根据操作类型确定需要刷新的section
            const sectionsToRefresh = this.getSectionsToRefresh(actionType, targetSection);

            // 刷新相关sections
            for (const section of sectionsToRefresh) {
                if (this.shouldRefresh(section)) {
                    await this.refreshSection(section);
                    this.recordRefresh(section);
                }
            }

            // 显示刷新完成提示
            this.showRefreshComplete(actionType);

        } catch (error) {
            console.error('刷新失败:', error);
            this.showRefreshError(error.message);
        } finally {
            this.isRefreshing = false;
        }
    }

    // 根据操作类型确定需要刷新的sections
    getSectionsToRefresh(actionType, targetSection) {
        const refreshMap = {
            'create_registration': ['myRegistrations', 'booking'],
            'cancel_registration': ['myRegistrations'],
            'update_profile': ['profile'],
            'manual_refresh': [targetSection || this.getCurrentSection()],
            'section_switch': [] // 切换页面时不自动刷新
        };

        return refreshMap[actionType] || [];
    }

    // 获取当前活动的section
    getCurrentSection() {
        const activeSection = document.querySelector('.content-section.active');
        if (activeSection) {
            return activeSection.id.replace('section-', '');
        }
        return 'booking';
    }

    // 刷新当前活动的section
    async refreshCurrentSection() {
        const currentSection = this.getCurrentSection();
        console.log(`刷新当前section: ${currentSection}`);
        
        try {
            await this.refreshSection(currentSection);
            this.recordRefresh(currentSection);
        } catch (error) {
            console.error('刷新当前section失败:', error);
        }
    }

    // 刷新指定section
    async refreshSection(sectionName) {
        console.log(`刷新section: ${sectionName}`);

        try {
            switch (sectionName) {
                case 'myRegistrations':
                    if (typeof loadRegistrations === 'function') {
                        await loadRegistrations();
                    }
                    break;

                case 'booking':
                    if (typeof loadDepartments === 'function') {
                        await loadDepartments();
                    }
                    // 如果有选中的科室，也刷新医生列表
                    const deptSelect = document.getElementById('deptSelect');
                    if (deptSelect && deptSelect.value) {
                        // 触发科室选择事件来刷新医生列表
                        if (typeof onDeptSelect === 'function') {
                            await onDeptSelect();
                        }
                    }
                    break;

                case 'profile':
                    if (typeof loadProfile === 'function') {
                        await loadProfile();
                    }
                    break;

                default:
                    console.log(`未知的section: ${sectionName}`);
            }
        } catch (error) {
            console.error(`刷新${sectionName}失败:`, error);
            throw error;
        }
    }

    // 显示刷新完成提示
    showRefreshComplete(actionType) {
        const messages = {
            'create_registration': '挂号成功，数据已更新',
            'cancel_registration': '挂号已取消，数据已更新',
            'update_profile': '个人信息已更新',
            'manual_refresh': '数据已刷新'
        };

        const message = messages[actionType] || '操作完成';
        this.showToast(message, 'success');
    }

    // 显示刷新错误
    showRefreshError(errorMessage) {
        this.showToast(`刷新失败: ${errorMessage}`, 'error');
    }

    // 禁用提示消息显示
    showToast(message, type) {
        // 不显示任何toast提示，只在控制台记录
        console.log(`Toast提示: ${message} (${type})`);
    }

    // 添加toast样式
    addToastStyles() {
        if (document.getElementById('refresh-toast-styles')) return;

        const style = document.createElement('style');
        style.id = 'refresh-toast-styles';
        style.textContent = `
            .refresh-toast .toast-content {
                display: flex;
                align-items: center;
                padding: 12px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                min-width: 200px;
                background: white;
                border-left: 4px solid;
            }

            .refresh-toast .toast-content.success {
                border-left-color: #28a745;
                color: #155724;
            }

            .refresh-toast .toast-content.error {
                border-left-color: #dc3545;
                color: #721c24;
            }

            .refresh-toast .toast-icon {
                margin-right: 8px;
                font-size: 16px;
                font-weight: bold;
            }

            .refresh-toast .toast-content.success .toast-icon {
                color: #28a745;
            }

            .refresh-toast .toast-content.error .toast-icon {
                color: #dc3545;
            }
        `;
        document.head.appendChild(style);
    }

    // 手动刷新当前页面
    async manualRefresh() {
        const currentSection = this.getCurrentSection();
        await this.refreshAfterUserAction('manual_refresh', currentSection);
    }
}

// 创建全局按需刷新实例
window.onDemandRefresh = new OnDemandRefresh();

// 重写全局刷新函数
window.manualRefresh = function() {
    if (window.onDemandRefresh) {
        window.onDemandRefresh.manualRefresh();
    }
};

// 监听用户操作事件
document.addEventListener('DOMContentLoaded', function() {
    console.log('按需刷新机制已启用 - 只在用户操作时刷新数据');

    // 监听挂号相关操作
    document.addEventListener('click', function(event) {
        const target = event.target;
        
        // 确认挂号按钮
        if (target.textContent === '确认挂号' || target.closest('button')?.textContent === '确认挂号') {
            // 立即刷新，不等待
            window.onDemandRefresh.refreshAfterUserAction('create_registration');
        }
        
        // 取消挂号按钮
        if (target.textContent === '确认取消' || target.closest('button')?.textContent === '确认取消') {
            // 立即刷新，不等待
            window.onDemandRefresh.refreshAfterUserAction('cancel_registration');
        }
    });

    // 监听表单提交（个人信息更新）
    document.addEventListener('submit', function(event) {
        const form = event.target;
        if (form.id === 'profileForm' || form.closest('#profileForm')) {
            // 立即刷新，不等待
            window.onDemandRefresh.refreshAfterUserAction('update_profile');
        }
    });
});
