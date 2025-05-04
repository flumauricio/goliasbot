/**
 * Golias BOT - Dashboard
 * Script específico para página de dashboard
 */

document.addEventListener('DOMContentLoaded', function() {
    // Verifica autenticação
    const token = localStorage.getItem('discord_token');
    if (!token) {
        window.location.href = 'index.html';
        return;
    }

    // Inicializa o dashboard
    initDashboard();
});

/**
 * Inicializa o dashboard
 */
async function initDashboard() {
    // Verifica se há um servidor selecionado na URL
    const urlParams = new URLSearchParams(window.location.search);
    const serverId = urlParams.get('server');

    if (serverId) {
        // Mostra a visão de dashboard para o servidor selecionado
        await loadServerDashboard(serverId);
    } else {
        // Mostra a lista de servidores para seleção
        document.getElementById('server-selection-view').classList.remove('d-none');
        document.getElementById('dashboard-sidebar').classList.add('d-none');
        document.getElementById('dashboard-content').classList.add('d-none');
        
        // Carrega a lista de servidores
        await loadUserServers(localStorage.getItem('discord_token'));
    }

    // Configura os eventos de navegação
    setupNavigationEvents();
}

/**
 * Carrega o dashboard para um servidor específico
 * @param {string} serverId - ID do servidor
 */
async function loadServerDashboard(serverId) {
    try {
        // Mostra a interface do dashboard
        document.getElementById('server-selection-view').classList.add('d-none');
        document.getElementById('dashboard-sidebar').classList.remove('d-none');
        document.getElementById('dashboard-content').classList.remove('d-none');

        // Carrega os dados do servidor
        await loadServerInfo(serverId);
        
        // Carrega as estatísticas
        await loadStatistics(serverId);
        
        // Carrega as licenças ativas
        await loadActiveLicenses(serverId);
        
        // Carrega atividades recentes
        await loadRecentActivity(serverId);
        
        // Outros carregamentos serão feitos quando o usuário navegar pelas abas
    } catch (error) {
        console.error('Erro ao carregar dashboard:', error);
        showErrorMessage('Erro ao carregar informações do servidor. Por favor, tente novamente.');
    }
}

/**
 * Carrega informações básicas do servidor
 * @param {string} serverId - ID do servidor
 */
async function loadServerInfo(serverId) {
    try {
        const token = localStorage.getItem('discord_token');
        
        // Obtém informações do servidor do Discord
        const response = await fetch(`https://discord.com/api/guilds/${serverId}`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Falha ao obter informações do servidor');
        }

        const serverData = await response.json();
        
        // Atualiza a interface com os dados do servidor
        document.getElementById('server-name').textContent = serverData.name;
        
        // Define o ícone do servidor
        const serverIcon = document.getElementById('server-icon');
        if (serverData.icon) {
            serverIcon.src = `https://cdn.discordapp.com/icons/${serverData.id}/${serverData.icon}.png`;
        } else {
            serverIcon.src = `https://via.placeholder.com/40?text=${serverData.name.charAt(0)}`;
        }
        
        // Atualiza o título da página
        document.title = `${serverData.name} - Golias BOT Dashboard`;
        
        // Carrega outros servidores para o dropdown de troca
        await loadServerSwitcher(serverId);
    } catch (error) {
        console.error('Erro ao carregar informações do servidor:', error);
        document.getElementById('server-name').textContent = 'Erro ao carregar servidor';
    }
}

/**
 * Carrega o seletor de troca de servidores
 * @param {string} currentServerId - ID do servidor atual
 */
async function loadServerSwitcher(currentServerId) {
    try {
        const token = localStorage.getItem('discord_token');
        
        // Obtém lista de servidores do usuário
        const response = await fetch('https://discord.com/api/users/@me/guilds', {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error('Falha ao obter servidores');
        }

        const serversData = await response.json();
        
        // Filtra servidores onde o usuário tem permissão de administrador
        const adminServers = serversData.filter(server => 
            (server.permissions & 0x8) === 0x8 && server.id !== currentServerId
        );

        // Atualiza o dropdown
        const serverSwitcher = document.getElementById('server-switcher');
        const firstItem = serverSwitcher.querySelector('li');  // Mantém o primeiro item (Voltar para Seleção)
        
        // Limpa os itens existentes, mantendo o primeiro
        serverSwitcher.innerHTML = '';
        serverSwitcher.appendChild(firstItem);
        
        if (adminServers.length === 0) {
            const noServersItem = document.createElement('li');
            noServersItem.innerHTML = '<span class="dropdown-item text-muted">Nenhum outro servidor</span>';
            serverSwitcher.appendChild(noServersItem);
        } else {
            // Adiciona um separador
            const divider = document.createElement('li');
            divider.innerHTML = '<hr class="dropdown-divider">';
            serverSwitcher.appendChild(divider);
            
            // Adiciona os servidores
            adminServers.forEach(server => {
                const item = document.createElement('li');
                item.innerHTML = `<a class="dropdown-item" href="dashboard.html?server=${server.id}">${server.name}</a>`;
                serverSwitcher.appendChild(item);
            });
        }
    } catch (error) {
        console.error('Erro ao carregar switcher de servidores:', error);
    }
}

/**
 * Carrega estatísticas do servidor
 * @param {string} serverId - ID do servidor
 */
async function loadStatistics(serverId) {
    try {
        // Simula uma chamada à API backend
        // Em um ambiente real, isso seria uma chamada à API do backend
        const mockStats = {
            active_modules: 2,
            days_remaining: 15,
            expiring_licenses: 1,
            expired_licenses: 0
        };
        
        // Atualiza os contadores na interface
        document.getElementById('active-modules-count').textContent = mockStats.active_modules;
        document.getElementById('days-remaining').textContent = mockStats.days_remaining;
        document.getElementById('expiring-licenses').textContent = mockStats.expiring_licenses;
        document.getElementById('expired-licenses').textContent = mockStats.expired_licenses;
    } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
    }
}

/**
 * Carrega as licenças ativas
 * @param {string} serverId - ID do servidor
 */
async function loadActiveLicenses(serverId) {
    try {
        // Simula uma chamada à API backend
        const mockLicenses = [
            {
                module_id: 'advertencias',
                module_name: 'Sistema de Advertências',
                expiration_date: '2023-12-31T23:59:59',
                days_remaining: 25,
                status: 'active'
            },
            {
                module_id: 'ponto',
                module_name: 'Controle de Ponto',
                expiration_date: '2023-12-10T23:59:59',
                days_remaining: 5,
                status: 'expiring'
            }
        ];
        
        const licensesList = document.getElementById('active-licenses-list');
        licensesList.innerHTML = '';
        
        if (mockLicenses.length === 0) {
            licensesList.innerHTML = '<p class="text-muted">Nenhuma licença ativa encontrada.</p>';
            return;
        }
        
        // Cria uma lista de licenças
        const listGroup = document.createElement('div');
        listGroup.className = 'list-group';
        
        mockLicenses.forEach(license => {
            const expirationDate = new Date(license.expiration_date);
            const formattedDate = expirationDate.toLocaleDateString('pt-BR');
            
            const statusClass = license.status === 'active' ? 'success' : 'warning';
            const statusIcon = license.status === 'active' ? 'check-circle' : 'exclamation-triangle';
            
            const item = document.createElement('a');
            item.href = `#licenses-tab`;
            item.className = `list-group-item list-group-item-action d-flex justify-content-between align-items-center`;
            item.setAttribute('data-bs-toggle', 'tab');
            item.setAttribute('data-bs-target', '#licenses-tab');
            item.innerHTML = `
                <div>
                    <h6 class="mb-0">${license.module_name}</h6>
                    <small class="text-muted">Expira em ${formattedDate}</small>
                </div>
                <span class="badge bg-${statusClass} rounded-pill">
                    <i class="bi bi-${statusIcon}"></i> ${license.days_remaining} dias
                </span>
            `;
            listGroup.appendChild(item);
        });
        
        licensesList.appendChild(listGroup);
    } catch (error) {
        console.error('Erro ao carregar licenças ativas:', error);
        document.getElementById('active-licenses-list').innerHTML = 
            '<div class="alert alert-danger">Erro ao carregar licenças. Por favor, tente novamente.</div>';
    }
}

/**
 * Carrega atividades recentes
 * @param {string} serverId - ID do servidor
 */
async function loadRecentActivity(serverId) {
    try {
        // Simula uma chamada à API backend
        const mockActivities = [
            {
                type: 'payment',
                module: 'Sistema de Advertências',
                timestamp: '2023-11-05T14:32:00',
                message: 'Licença renovada por 30 dias'
            },
            {
                type: 'warning',
                module: 'Controle de Ponto',
                timestamp: '2023-11-01T09:15:00',
                message: 'Licença expirando em 10 dias'
            }
        ];
        
        const activityList = document.getElementById('recent-activity');
        activityList.innerHTML = '';
        
        if (mockActivities.length === 0) {
            activityList.innerHTML = '<p class="text-muted">Nenhuma atividade recente encontrada.</p>';
            return;
        }
        
        // Cria uma lista de atividades
        mockActivities.forEach(activity => {
            const date = new Date(activity.timestamp);
            const formattedDate = date.toLocaleDateString('pt-BR') + ' ' + date.toLocaleTimeString('pt-BR').slice(0, 5);
            
            let icon, color;
            switch (activity.type) {
                case 'payment':
                    icon = 'credit-card';
                    color = 'success';
                    break;
                case 'warning':
                    icon = 'exclamation-triangle';
                    color = 'warning';
                    break;
                default:
                    icon = 'info-circle';
                    color = 'info';
            }
            
            const item = document.createElement('div');
            item.className = 'mb-3 border-start border-3 ps-3';
            item.style.borderColor = `var(--${color}-color)`;
            item.innerHTML = `
                <div class="d-flex align-items-center mb-1">
                    <i class="bi bi-${icon} me-2 text-${color}"></i>
                    <strong>${activity.module}</strong>
                </div>
                <p class="mb-1">${activity.message}</p>
                <small class="text-muted">${formattedDate}</small>
            `;
            activityList.appendChild(item);
        });
    } catch (error) {
        console.error('Erro ao carregar atividades recentes:', error);
        document.getElementById('recent-activity').innerHTML = 
            '<div class="alert alert-danger">Erro ao carregar atividades. Por favor, tente novamente.</div>';
    }
}

/**
 * Configura eventos de navegação no dashboard
 */
function setupNavigationEvents() {
    // Links da barra lateral
    const sidebarLinks = document.querySelectorAll('.sidebar-link');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function() {
            // Remove a classe active de todos os links
            sidebarLinks.forEach(l => l.classList.remove('active'));
            // Adiciona a classe active ao link clicado
            this.classList.add('active');
            
            // Carrega os dados da aba selecionada, se necessário
            const target = this.getAttribute('data-bs-target').replace('#', '');
            if (target === 'modules-tab') {
                loadModules();
            } else if (target === 'licenses-tab') {
                loadLicenses();
            } else if (target === 'transactions-tab') {
                loadTransactions();
            } else if (target === 'settings-tab') {
                loadSettings();
            }
        });
    });
}

/**
 * Carrega os módulos disponíveis
 */
function loadModules() {
    // A implementação real faria uma chamada à API
    console.log('Carregando módulos...');
    
    // Simulação de dados de módulos
    const modules = [
        {
            id: 'advertencias',
            name: 'Sistema de Advertências',
            description: 'Gerencia advertências de usuários com limite configurável e ações automáticas.',
            price: 10.00,
            currency: 'BRL',
            status: 'active',
            features: ['Advertências configuráveis', 'Ações automáticas', 'Registro de logs']
        },
        {
            id: 'ponto',
            name: 'Controle de Ponto',
            description: 'Gerencie a presença de membros com sistema de entrada e saída.',
            price: 15.00,
            currency: 'BRL',
            status: 'active',
            features: ['Registro de horas', 'Relatórios semanais', 'Lembretes automáticos']
        },
        {
            id: 'economia',
            name: 'Sistema de Economia',
            description: 'Sistema completo de economia virtual para seu servidor.',
            price: 20.00,
            currency: 'BRL',
            status: 'available',
            features: ['Moeda virtual', 'Loja personalizada', 'Sistema de trabalhos', 'Jogos e apostas']
        }
    ];
    
    // Atualiza a interface
    const modulesList = document.getElementById('modules-list');
    modulesList.innerHTML = '';
    
    modules.forEach(module => {
        const isActive = module.status === 'active';
        const card = document.createElement('div');
        card.className = 'col-md-6 col-lg-4';
        card.innerHTML = `
            <div class="card h-100 ${isActive ? 'module-card active' : 'module-card'}">
                <div class="card-body">
                    <h3 class="card-title">${module.name}</h3>
                    <p class="card-text">${module.description}</p>
                    <ul class="list-unstyled">
                        ${module.features.map(feature => `
                            <li><i class="bi bi-check-circle text-success"></i> ${feature}</li>
                        `).join('')}
                    </ul>
                    <div class="d-flex justify-content-between align-items-center mt-3">
                        <span class="fw-bold">${module.price.toFixed(2)} ${module.currency}</span>
                        ${isActive ? 
                            `<button class="btn btn-success" disabled><i class="bi bi-check-circle"></i> Ativo</button>` : 
                            `<button class="btn btn-primary"><i class="bi bi-cart-plus"></i> Adquirir</button>`
                        }
                    </div>
                </div>
            </div>
        `;
        modulesList.appendChild(card);
    });
}

/**
 * Carrega as licenças do servidor
 */
function loadLicenses() {
    // A implementação real faria uma chamada à API
    console.log('Carregando licenças...');
    
    // Simulação de dados de licenças
    const licenses = [
        {
            id: '123456',
            module_id: 'advertencias',
            module_name: 'Sistema de Advertências',
            expiration_date: '2023-12-31T23:59:59',
            days_remaining: 25,
            status: 'active'
        },
        {
            id: '789012',
            module_id: 'ponto',
            module_name: 'Controle de Ponto',
            expiration_date: '2023-12-10T23:59:59',
            days_remaining: 5,
            status: 'expiring'
        }
    ];
    
    // Atualiza a interface
    const licensesTable = document.getElementById('licenses-table-body');
    licensesTable.innerHTML = '';
    
    if (licenses.length === 0) {
        licensesTable.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-muted">Nenhuma licença encontrada.</td>
            </tr>
        `;
        return;
    }
    
    licenses.forEach(license => {
        const expirationDate = new Date(license.expiration_date);
        const formattedDate = expirationDate.toLocaleDateString('pt-BR');
        
        let statusBadge;
        if (license.status === 'active') {
            statusBadge = '<span class="badge bg-success">Ativa</span>';
        } else if (license.status === 'expiring') {
            statusBadge = '<span class="badge bg-warning">Expirando</span>';
        } else {
            statusBadge = '<span class="badge bg-danger">Expirada</span>';
        }
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${license.module_name}</td>
            <td>${formattedDate}</td>
            <td>${statusBadge}</td>
            <td>${license.days_remaining} dias</td>
            <td>
                <button class="btn btn-sm btn-primary" title="Renovar Licença">
                    <i class="bi bi-arrow-clockwise"></i>
                </button>
            </td>
        `;
        licensesTable.appendChild(row);
    });
}

/**
 * Carrega as transações do servidor
 */
function loadTransactions() {
    // A implementação real faria uma chamada à API
    console.log('Carregando transações...');
    
    // Simulação de dados de transações
    const transactions = [
        {
            id: 'TX123456',
            module_id: 'advertencias',
            module_name: 'Sistema de Advertências',
            amount: 10.00,
            currency: 'BRL',
            date: '2023-11-05T14:32:00',
            status: 'approved'
        },
        {
            id: 'TX789012',
            module_id: 'ponto',
            module_name: 'Controle de Ponto',
            amount: 15.00,
            currency: 'BRL',
            date: '2023-10-12T10:45:00',
            status: 'approved'
        }
    ];
    
    // Atualiza a interface
    const transactionsTable = document.getElementById('transactions-table-body');
    transactionsTable.innerHTML = '';
    
    if (transactions.length === 0) {
        transactionsTable.innerHTML = `
            <tr>
                <td colspan="5" class="text-center text-muted">Nenhuma transação encontrada.</td>
            </tr>
        `;
        return;
    }
    
    transactions.forEach(transaction => {
        const transactionDate = new Date(transaction.date);
        const formattedDate = transactionDate.toLocaleDateString('pt-BR') + ' ' + 
                             transactionDate.toLocaleTimeString('pt-BR').slice(0, 5);
        
        let statusBadge;
        if (transaction.status === 'approved') {
            statusBadge = '<span class="badge bg-success">Aprovado</span>';
        } else if (transaction.status === 'pending') {
            statusBadge = '<span class="badge bg-warning">Pendente</span>';
        } else {
            statusBadge = '<span class="badge bg-danger">Recusado</span>';
        }
        
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${transaction.id}</td>
            <td>${transaction.module_name}</td>
            <td>${transaction.amount.toFixed(2)} ${transaction.currency}</td>
            <td>${formattedDate}</td>
            <td>${statusBadge}</td>
        `;
        transactionsTable.appendChild(row);
    });
}

/**
 * Carrega as configurações do servidor
 */
function loadSettings() {
    // A implementação real faria uma chamada à API
    console.log('Carregando configurações...');
    
    // Simulação de dados de canais do servidor
    const channels = [
        { id: '111222333444555666', name: 'geral' },
        { id: '222333444555666777', name: 'avisos' },
        { id: '333444555666777888', name: 'logs' }
    ];
    
    // Atualiza o select de canais
    const channelSelect = document.getElementById('notificationsChannel');
    channelSelect.innerHTML = '<option value="">Selecione um canal...</option>';
    
    channels.forEach(channel => {
        const option = document.createElement('option');
        option.value = channel.id;
        option.textContent = '#' + channel.name;
        channelSelect.appendChild(option);
    });
    
    // Configura o envio do formulário
    const settingsForm = document.getElementById('settings-form');
    settingsForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Obtém os valores do formulário
        const channelId = channelSelect.value;
        const notifyExpiring = document.getElementById('notifyExpiring').checked;
        const notifyExpired = document.getElementById('notifyExpired').checked;
        
        // Salva as configurações (simulado)
        console.log('Configurações salvas:', {
            notificationsChannel: channelId,
            notifyExpiring,
            notifyExpired
        });
        
        // Mostra mensagem de sucesso
        alert('Configurações salvas com sucesso!');
    });
}

/**
 * Exibe uma mensagem de erro
 * @param {string} message - Mensagem de erro
 */
function showErrorMessage(message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-danger alert-dismissible fade show';
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Fechar"></button>
    `;
    
    // Insere no início do conteúdo
    const contentDiv = document.getElementById('dashboard-content');
    contentDiv.insertBefore(alertDiv, contentDiv.firstChild);
} 