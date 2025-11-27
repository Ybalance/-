/**
 * 增强的API处理，确保操作后立即获取最新数据
 */

// 增强挂号确认函数
function enhanceBookingConfirmation() {
    // 查找并增强确认挂号按钮的点击事件
    document.addEventListener('click', async function(event) {
        // 检查是否是确认挂号按钮
        if (event.target.textContent === '确认挂号' || 
            event.target.closest('button')?.textContent === '确认挂号') {
            
            event.preventDefault();
            event.stopPropagation();
            
            await handleBookingConfirmation();
        }
    });
}

// 处理挂号确认
async function handleBookingConfirmation() {
    try {
        // 显示加载状态
        showLoadingState('正在创建挂号...');
        
        // 获取选中的医生和时间
        const selectedSlot = document.querySelector('.time-slot.selected');
        if (!selectedSlot) {
            showMessage('请选择就诊时间', 'warning');
            return;
        }

        const doctorId = selectedSlot.dataset.doctorId;
        const dateTime = selectedSlot.dataset.datetime;

        // 创建挂号
        const response = await apiRequest('/registrations', {
            method: 'POST',
            body: JSON.stringify({
                doctor_id: parseInt(doctorId),
                reg_time: dateTime
            })
        });

        // 显示成功消息
        showMessage('挂号成功！', 'success');
        
        // 立即刷新相关数据
        await refreshAfterBooking();
        
        // 清除选择状态
        clearSelection();
        
    } catch (error) {
        showMessage('挂号失败: ' + error.message, 'danger');
    } finally {
        hideLoadingState();
    }
}

// 挂号后刷新数据
async function refreshAfterBooking() {
    try {
        // 刷新我的挂号列表（如果当前在该页面）
        const myRegistrationsSection = document.getElementById('section-myRegistrations');
        if (myRegistrationsSection && myRegistrationsSection.classList.contains('active')) {
            await loadRegistrations();
        }
        
        // 刷新预约页面的时间段显示
        const bookingSection = document.getElementById('section-booking');
        if (bookingSection && bookingSection.classList.contains('active')) {
            const deptSelect = document.getElementById('deptSelect');
            if (deptSelect && deptSelect.value) {
                await onDeptSelect(); // 重新加载医生和时间段
            }
        }
        
        console.log('挂号后数据刷新完成');
    } catch (error) {
        console.error('刷新数据失败:', error);
    }
}

// 增强取消挂号功能
function enhanceCancelRegistration() {
    // 重写取消挂号函数
    window.originalCancelRegistration = window.cancelRegistration;
    
    window.cancelRegistration = async function(regId) {
        try {
            showLoadingState('正在取消挂号...');
            
            // 调用API取消挂号
            await apiRequest(`/registrations/${regId}/cancel`, {
                method: 'POST'
            });
            
            showMessage('挂号已取消', 'success');
            
            // 立即刷新挂号列表
            await loadRegistrations();
            
            // 关闭模态框
            if (typeof closeCancelModal === 'function') {
                closeCancelModal();
            }
            
        } catch (error) {
            showMessage('取消挂号失败: ' + error.message, 'danger');
        } finally {
            hideLoadingState();
        }
    };
}

// 显示加载状态
function showLoadingState(message = '处理中...') {
    let loadingElement = document.getElementById('global-loading');
    
    if (!loadingElement) {
        loadingElement = document.createElement('div');
        loadingElement.id = 'global-loading';
        loadingElement.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 10001;
            backdrop-filter: blur(2px);
        `;
        
        loadingElement.innerHTML = `
            <div style="
                background: white;
                padding: 2rem;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                min-width: 200px;
            ">
                <div style="
                    width: 40px;
                    height: 40px;
                    border: 4px solid #f3f3f3;
                    border-top: 4px solid #007bff;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 1rem auto;
                "></div>
                <div id="loading-message" style="
                    font-size: 16px;
                    color: #333;
                    font-weight: 500;
                ">${message}</div>
            </div>
        `;
        
        // 添加旋转动画
        if (!document.getElementById('loading-animation-style')) {
            const style = document.createElement('style');
            style.id = 'loading-animation-style';
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(loadingElement);
    } else {
        const messageElement = document.getElementById('loading-message');
        if (messageElement) {
            messageElement.textContent = message;
        }
        loadingElement.style.display = 'flex';
    }
}

// 隐藏加载状态
function hideLoadingState() {
    const loadingElement = document.getElementById('global-loading');
    if (loadingElement) {
        loadingElement.style.display = 'none';
    }
}

// 清除选择状态
function clearSelection() {
    document.querySelectorAll('.time-slot.selected').forEach(slot => {
        slot.classList.remove('selected');
    });
}

// 增强页面切换时的数据刷新 - 只在首次进入时加载
function enhancePageSwitching() {
    const originalShowSection = window.showSection;
    const loadedSections = new Set(); // 记录已加载的section
    
    window.showSection = async function(sectionName) {
        // 调用原始函数
        if (originalShowSection) {
            originalShowSection(sectionName);
        }
        
        // 只在首次进入section时加载数据，避免重复刷新
        if (!loadedSections.has(sectionName)) {
            loadedSections.add(sectionName);
            
            setTimeout(async () => {
                try {
                    switch (sectionName) {
                        case 'myRegistrations':
                            await loadRegistrations();
                            break;
                        case 'booking':
                            await loadDepartments();
                            break;
                        case 'profile':
                            if (typeof loadProfile === 'function') {
                                await loadProfile();
                            }
                            break;
                    }
                } catch (error) {
                    console.error('页面首次加载数据失败:', error);
                }
            }, 100);
        }
    };
}

// 监听数据变化并自动刷新
function setupDataChangeListener() {
    // 监听存储变化（如果有其他标签页的操作）
    window.addEventListener('storage', function(event) {
        if (event.key === 'data_changed') {
            console.log('检测到数据变化，刷新页面数据');
            window.onDemandRefresh.refreshAfterUserAction('create_registration'); // 立即刷新，不等待
        }
    });
    
    // 监听页面焦点变化
    document.addEventListener('visibilitychange', function() {
        if (!document.hidden) {
            // 页面重新获得焦点时刷新数据
            setTimeout(() => {
                if (window.onDemandRefresh && typeof window.onDemandRefresh.refreshCurrentSection === 'function') {
                    window.onDemandRefresh.refreshCurrentSection();
                }
            }, 500);
        }
    });
}

// 初始化所有增强功能
function initializeEnhancements() {
    enhanceBookingConfirmation();
    enhanceCancelRegistration();
    enhancePageSwitching();
    setupDataChangeListener();
    
    console.log('API增强功能已初始化');
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保其他脚本已加载
    setTimeout(initializeEnhancements, 1000);
});

// 导出函数供其他脚本使用
window.enhancedAPI = {
    showLoadingState,
    hideLoadingState,
    refreshAfterBooking,
    clearSelection
};
