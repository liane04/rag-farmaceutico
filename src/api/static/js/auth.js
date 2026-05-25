// Login, logout e perfil do utilizador autenticado.
// Funciona contra os endpoints /auth/login e /auth/me da API.

import { apiGet, clearToken, setToken, formatarDetalheErro } from './api.js';

export async function login(username, password) {
    // OAuth2PasswordRequestForm exige application/x-www-form-urlencoded.
    const body = new URLSearchParams();
    body.set('username', username);
    body.set('password', password);

    const res = await fetch('/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
    });

    if (!res.ok) {
        let mensagem = 'Credenciais invalidas.';
        try {
            const data = await res.json();
            mensagem = formatarDetalheErro(data.detail) || mensagem;
        } catch {
            /* mantem mensagem default */
        }
        throw new Error(mensagem);
    }

    const data = await res.json();
    setToken(data.access_token);
    return data;
}

export function logout() {
    clearToken();
}

export async function obterUtilizadorAtual() {
    return apiGet('/auth/me');
}
