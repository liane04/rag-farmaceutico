// Wrappers de fetch que injectam o header Authorization e tratam 401.
// O token e o login propriamente dito vivem em auth.js — este modulo so
// cuida do transporte HTTP e da expiracao.

const TOKEN_KEY = 'rag_token';

export function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
}

// Quando uma chamada devolve 401 limpamos o token e disparamos um evento;
// o main.js escuta-o e volta ao ecra de login.
function notificarExpirado() {
    clearToken();
    window.dispatchEvent(new CustomEvent('auth:expired'));
}

export async function apiFetch(path, options = {}) {
    const token = getToken();
    const headers = new Headers(options.headers || {});
    if (token) headers.set('Authorization', 'Bearer ' + token);
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) {
        notificarExpirado();
        throw new Error('Sessao expirada — faca login novamente.');
    }
    return res;
}

export async function apiGet(path) {
    const res = await apiFetch(path);
    if (!res.ok) throw new Error(await extrairErro(res));
    return res.json();
}

export async function apiPostJson(path, body) {
    const res = await apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await extrairErro(res));
    return res.json();
}

export async function apiPostForm(path, formData) {
    const res = await apiFetch(path, { method: 'POST', body: formData });
    if (!res.ok) throw new Error(await extrairErro(res));
    return res.json();
}

// URL para o endpoint /ficheiros — com token no query param porque o browser
// nao envia headers em <a href> ou <iframe>.
export function ficheiroUrl(tipo, nome, pagina) {
    const token = getToken();
    const base = `/ficheiros/${encodeURIComponent(tipo)}/${encodeURIComponent(nome)}`;
    const qs = token ? `?token=${encodeURIComponent(token)}` : '';
    const hash = pagina ? `#page=${pagina}` : '';
    return base + qs + hash;
}

async function extrairErro(res) {
    try {
        const data = await res.json();
        return formatarDetalheErro(data.detail) || `Erro ${res.status}`;
    } catch {
        return `Erro ${res.status}`;
    }
}

// Normaliza o campo `detail` de uma resposta de erro do FastAPI:
// - HTTPException da nossa API: string simples
// - Erros de validacao do Pydantic (422): array de objectos {loc, msg, type}
export function formatarDetalheErro(detail) {
    if (!detail) return null;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail.map(d => {
            if (typeof d === 'string') return d;
            if (d && typeof d.msg === 'string') {
                const campo = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
                return campo ? `${campo}: ${d.msg}` : d.msg;
            }
            return JSON.stringify(d);
        }).join('; ');
    }
    if (typeof detail === 'object' && typeof detail.msg === 'string') return detail.msg;
    return String(detail);
}

// Traduz erros tecnicos (stacktrace do backend, erros de socket do SO) em
// mensagens compreensiveis para o utilizador final. O contexto opcional
// adapta o texto a accao em curso (consulta vs upload vs generico).
export function humanizarErro(msg, contexto) {
    const original = msg || '';
    const m = original.toLowerCase();
    if (m.includes('connection refused') || m.includes('winerror 10061') ||
        m.includes('errno 111') || m.includes('falha na recuperacao')) {
        if (contexto === 'consulta') {
            return 'O servico de pesquisa esta temporariamente indisponivel. Tente novamente em instantes.';
        }
        if (contexto === 'indexacao') {
            return 'O servico de indexacao esta temporariamente indisponivel. Tente novamente em instantes.';
        }
        return 'O sistema esta temporariamente indisponivel. Tente novamente em instantes.';
    }
    if (m.includes('timeout') || m.includes('timed out')) {
        return 'O sistema demorou demasiado a responder. Tente novamente.';
    }
    if (m.includes('rate limit') || m.includes('429')) {
        return 'Demasiados pedidos em pouco tempo. Aguarde alguns segundos e tente de novo.';
    }
    if (original.length > 220) {
        return 'Ocorreu um erro inesperado. Tente novamente em instantes.';
    }
    return original || 'Ocorreu um erro inesperado.';
}
