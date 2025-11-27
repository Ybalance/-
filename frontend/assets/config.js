// API Configuration
const API_BASE_URL = 'http://127.0.0.1:50002/api';

// API endpoints
const API_ENDPOINTS = {
    login: '/login',
    signup: '/signup',
    departments: '/departments',
    doctors: '/doctors',
    register: '/register',
    patientRegistrations: '/patient/registrations',
    cancelRegistration: '/registrations/{id}/cancel',
    doctorRegistrations: '/doctor/registrations',
    searchPatients: '/doctor/search',
    completeRegistration: '/registrations/{id}/complete',
    adminRegistrations: '/admin/registrations',
    adminPatients: '/admin/patients',
    adminDoctors: '/admin/doctors',
    adminDepartment: '/admin/department',
    adminStats: '/admin/stats',
    deleteUser: '/admin/users/{role}/{id}'
};

// Helper function to build full API URL
function getApiUrl(endpoint, params = {}) {
    let url = API_BASE_URL + endpoint;
    
    // Replace path parameters
    Object.keys(params).forEach(key => {
        url = url.replace(`{${key}}`, params[key]);
    });
    
    return url;
}

// Helper function to get auth headers
function getAuthHeaders() {
    const token = localStorage.getItem('token');
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

// Helper function to make API requests
async function apiRequest(endpoint, methodOrOptions = {}, body = null) {
    const url = typeof endpoint === 'string' ? getApiUrl(endpoint) : endpoint;
    
    // 支持两种调用方式：
    // 1. apiRequest(url, 'POST', data)
    // 2. apiRequest(url, {method: 'POST', body: JSON.stringify(data)})
    let options = {};
    if (typeof methodOrOptions === 'string') {
        // 简化调用方式
        options = {
            method: methodOrOptions,
            body: body ? JSON.stringify(body) : undefined
        };
    } else {
        // 完整options对象
        options = methodOrOptions;
    }
    
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
        }
    };
    
    console.log('API Request:', url, options); // Debug log
    
    const response = await fetch(url, { ...defaultOptions, ...options });
    
    console.log('API Response Status:', response.status); // Debug log
    
    if (response.status === 401) {
        // Token expired or invalid
        localStorage.removeItem('token');
        localStorage.removeItem('role');
        localStorage.removeItem('username');
        localStorage.removeItem('user_id');
        window.location.href = 'login.html';
        return;
    }
    
    const data = await response.json();
    console.log('API Response Data:', data); // Debug log
    
    if (!response.ok) {
        throw new Error(data.error || 'Request failed');
    }
    
    return data;
}
