/**
 * Golias BOT - Dashboard
 * JavaScript principal
 */

document.addEventListener('DOMContentLoaded', function() {
    // Login com Discord
    const loginBtn = document.getElementById('loginBtn');
    if (loginBtn) {
        loginBtn.addEventListener('click', function(e) {
            e.preventDefault();
            // Redireciona para a autenticação do Discord
            window.location.href = 'https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=' + 
                encodeURIComponent(window.location.origin + '/auth-callback.html') + 
                '&response_type=token&scope=identify%20guilds';
        });
    }

    // Verifica se o usuário já está logado
    checkAuthStatus();

    // Adiciona animação fade-in aos elementos
    const animatedElements = document.querySelectorAll('.card, .feature-icon, .hero-section h1, .hero-section p');
    animatedElements.forEach(el => {
        el.classList.add('animate-fade-in');
    });

    // Inicializa tooltips do Bootstrap (se existirem)
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    if (tooltips.length > 0) {
        tooltips.forEach(tooltip => {
            new bootstrap.Tooltip(tooltip);
        });
    }
});

/**
 * Verifica o status de autenticação do usuário
 */
function checkAuthStatus() {
    // Verifica se há um token armazenado
    const token = localStorage.getItem('discord_token');
    if (token) {
        // Atualiza a UI para usuário logado
        updateUIForLoggedUser(token);
    }
}

/**
 * Atualiza a interface para usuário logado
 * @param {string} token - Token de autenticação do Discord
 */
async function updateUIForLoggedUser(token) {
    try {
        // Obtém informações do usuário do Discord
        const userResponse = await fetch('https://discord.com/api/users/@me', {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        if (!userResponse.ok) {
            // Token inválido ou expirado
            localStorage.removeItem('discord_token');
            return;
        }

        const userData = await userResponse.json();
        
        // Atualiza o botão de login
        const loginBtn = document.getElementById('loginBtn');
        if (loginBtn) {
            loginBtn.innerHTML = `<img src="https://cdn.discordapp.com/avatars/${userData.id}/${userData.avatar}.png" alt="${userData.username}" width="24" height="24" class="rounded-circle me-2"> ${userData.username}`;
            loginBtn.href = "dashboard.html";
        }

        // Verifica se estamos na página do dashboard e carrega os servidores
        if (window.location.pathname.includes('dashboard.html')) {
            loadUserServers(token);
        }
    } catch (error) {
        console.error('Erro ao verificar autenticação:', error);
    }
}

/**
 * Carrega os servidores do usuário (para a página de dashboard)
 * @param {string} token - Token de autenticação do Discord
 */
async function loadUserServers(token) {
    try {
        const serversResponse = await fetch('https://discord.com/api/users/@me/guilds', {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        if (!serversResponse.ok) {
            throw new Error('Falha ao obter servidores');
        }

        const serversData = await serversResponse.json();
        
        // Filtra servidores onde o usuário tem permissão de administrador
        const adminServers = serversData.filter(server => 
            (server.permissions & 0x8) === 0x8
        );

        // Renderiza a lista de servidores
        const serversList = document.getElementById('servers-list');
        if (serversList) {
            serversList.innerHTML = '';
            
            if (adminServers.length === 0) {
                serversList.innerHTML = '<div class="alert alert-info">Você não possui servidores onde seja administrador.</div>';
                return;
            }

            adminServers.forEach(server => {
                const serverIcon = server.icon 
                    ? `https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png` 
                    : 'https://via.placeholder.com/50?text=' + server.name.charAt(0);
                
                const serverCard = document.createElement('div');
                serverCard.className = 'card mb-3 server-card';
                serverCard.innerHTML = `
                    <div class="card-body d-flex align-items-center">
                        <img src="${serverIcon}" alt="${server.name}" class="rounded-circle me-3" width="50" height="50">
                        <div>
                            <h5 class="card-title mb-1">${server.name}</h5>
                            <p class="card-text text-muted">ID: ${server.id}</p>
                        </div>
                        <a href="dashboard.html?server=${server.id}" class="btn btn-primary ms-auto">Gerenciar</a>
                    </div>
                `;
                serversList.appendChild(serverCard);
            });
        }
    } catch (error) {
        console.error('Erro ao carregar servidores:', error);
        const serversList = document.getElementById('servers-list');
        if (serversList) {
            serversList.innerHTML = '<div class="alert alert-danger">Erro ao carregar seus servidores. Por favor, tente novamente mais tarde.</div>';
        }
    }
}

/**
 * Faz logout do usuário
 */
function logout() {
    localStorage.removeItem('discord_token');
    window.location.href = 'index.html';
} 