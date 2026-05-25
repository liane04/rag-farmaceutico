// Entrada da app: decide entre o ecra de login e a app autenticada, e
// encaminha o utilizador para a vista certa conforme o papel.

import { getToken } from './api.js';
import { login, logout, obterUtilizadorAtual } from './auth.js';
import { renderChat } from './chat.js';
import { renderDocumentos, renderAuditoria } from './admin.js';
import { renderHistorico } from './historico.js';

const loginView = document.getElementById('login-view');
const appView = document.getElementById('app-view');
const loginForm = document.getElementById('loginForm');
const loginError = document.getElementById('loginError');
const loginBtn = document.getElementById('loginBtn');
const tabsBar = document.getElementById('tabsBar');
const contentArea = document.getElementById('contentArea');
const logoutBtn = document.getElementById('logoutBtn');

let utilizadorAtual = null;
let tabAtiva = null;

// O api.js dispara este evento quando uma chamada devolve 401 — voltamos
// ao ecra de login sem ter de inserir verificacoes em cada vista.
window.addEventListener('auth:expired', () => {
    voltarParaLogin('Sessao expirada. Faca login novamente.');
});

logoutBtn.addEventListener('click', () => {
    logout();
    voltarParaLogin();
});

loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    loginError.hidden = true;
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    loginBtn.disabled = true;
    loginBtn.textContent = 'A entrar...';
    try {
        await login(username, password);
        await entrarNaApp();
    } catch (err) {
        loginError.textContent = err.message || 'Falha no login.';
        loginError.hidden = false;
    } finally {
        loginBtn.disabled = false;
        loginBtn.textContent = 'Entrar';
    }
});

async function entrarNaApp() {
    try {
        utilizadorAtual = await obterUtilizadorAtual();
    } catch {
        voltarParaLogin('Sessao invalida.');
        return;
    }
    loginView.hidden = true;
    appView.hidden = false;
    document.getElementById('userName').textContent = utilizadorAtual.username;
    document.getElementById('userRole').textContent =
        utilizadorAtual.papel === 'admin' ? 'Administrador' : 'Farmaceutico';
    document.getElementById('userRole').className =
        'user-role user-role-' + utilizadorAtual.papel;
    renderTabs();
    checkHealth();
}

function voltarParaLogin(mensagem) {
    utilizadorAtual = null;
    tabAtiva = null;
    appView.hidden = true;
    loginView.hidden = false;
    contentArea.innerHTML = '';
    tabsBar.innerHTML = '';
    loginForm.reset();
    if (mensagem) {
        loginError.textContent = mensagem;
        loginError.hidden = false;
    } else {
        loginError.hidden = true;
    }
    document.getElementById('loginUsername').focus();
}

function renderTabs() {
    const tabs = utilizadorAtual.papel === 'admin'
        ? [
            { id: 'consulta', label: 'Consulta', render: renderChat },
            { id: 'documentos', label: 'Documentos', render: renderDocumentos },
            { id: 'auditoria', label: 'Auditoria', render: renderAuditoria },
        ]
        : [
            { id: 'consulta', label: 'Consulta', render: renderChat },
            { id: 'historico', label: 'Historico', render: renderHistorico },
        ];

    tabsBar.innerHTML = '';
    tabs.forEach((tab, i) => {
        const btn = document.createElement('button');
        btn.className = 'tab-btn';
        btn.textContent = tab.label;
        btn.addEventListener('click', () => activarTab(tab, btn));
        tabsBar.appendChild(btn);
        if (i === 0) activarTab(tab, btn);
    });
}

function activarTab(tab, btnEl) {
    if (tabAtiva === tab.id) return;
    Array.from(tabsBar.children).forEach(b => b.classList.remove('active'));
    btnEl.classList.add('active');
    tabAtiva = tab.id;
    contentArea.innerHTML = '';
    tab.render(contentArea, utilizadorAtual);
}

// /health e publico — nao precisa de token nem do api.js
async function checkHealth() {
    try {
        const res = await fetch('/health');
        const data = await res.json();
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        dot.classList.remove('offline', 'warning');
        if (data.status === 'ok') {
            text.textContent = `Operacional (${data.total_pontos} pontos)`;
        } else if (data.status === 'vazio') {
            dot.classList.add('warning');
            text.textContent = 'Pronto — sem documentos';
        } else {
            dot.classList.add('offline');
            text.textContent = 'Sistema degradado';
        }
    } catch {
        const dot = document.getElementById('statusDot');
        dot.classList.add('offline');
        document.getElementById('statusText').textContent = 'Sem ligacao';
    }
}

// ============ Arranque ============
(async () => {
    if (getToken()) {
        await entrarNaApp();
    } else {
        voltarParaLogin();
    }
})();
