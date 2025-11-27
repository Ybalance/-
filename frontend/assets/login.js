// Login page functionality
let selectedRole = 'patient'; // Move to global scope

document.addEventListener('DOMContentLoaded', function() {
    const roleOptions = document.querySelectorAll('.role-option');
    const loginForm = document.getElementById('loginForm');
    const messageDiv = document.getElementById('message');

    // Role selection
    roleOptions.forEach(option => {
        option.addEventListener('click', function() {
            roleOptions.forEach(opt => opt.classList.remove('active'));
            this.classList.add('active');
            selectedRole = this.dataset.role;
        });
    });

    // Login form submission
    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        
        if (!username || !password) {
            showMessage('请填写用户名和密码', 'danger');
            return;
        }

        try {
            showMessage('正在登录...', 'info');
            
            const response = await fetch(getApiUrl('/login'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: username,
                    password: password,
                    role: selectedRole
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Store login information
                localStorage.setItem('token', data.access_token);
                localStorage.setItem('role', data.role);
                localStorage.setItem('username', data.username);
                localStorage.setItem('user_id', data.user_id);

                showMessage('登录成功，正在跳转...', 'success');

                // Redirect based on role
                setTimeout(() => {
                    switch (data.role) {
                        case 'patient':
                            window.location.href = 'patient.html';
                            break;
                        case 'doctor':
                            window.location.href = 'doctor.html';
                            break;
                        case 'admin':
                            window.location.href = 'admin.html';
                            break;
                        default:
                            window.location.href = 'login.html';
                    }
                }, 1000);
            } else {
                showMessage(data.error || '登录失败', 'danger');
            }
        } catch (error) {
            console.error('Login error:', error);
            showMessage('网络错误，请检查后端服务是否启动', 'danger');
        }
    });
});

// Quick login function
function quickLogin(username, password, role) {
    document.getElementById('username').value = username;
    document.getElementById('password').value = password;
    
    // Set role and update selectedRole variable
    document.querySelectorAll('.role-option').forEach(opt => {
        opt.classList.remove('active');
        if (opt.dataset.role === role) {
            opt.classList.add('active');
        }
    });
    
    // Update the selectedRole variable
    selectedRole = role;
    
    // Submit form
    document.getElementById('loginForm').dispatchEvent(new Event('submit'));
}

// Show message function
function showMessage(message, type) {
    const messageDiv = document.getElementById('message');
    messageDiv.className = `alert alert-${type}`;
    messageDiv.textContent = message;
    messageDiv.style.display = 'block';
    
    if (type === 'success') {
        setTimeout(() => {
            messageDiv.style.display = 'none';
        }, 3000);
    }
}

// Check if already logged in
if (localStorage.getItem('token')) {
    const role = localStorage.getItem('role');
    switch (role) {
        case 'patient':
            window.location.href = 'patient.html';
            break;
        case 'doctor':
            window.location.href = 'doctor.html';
            break;
        case 'admin':
            window.location.href = 'admin.html';
            break;
    }
}
