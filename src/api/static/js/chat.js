// Vista do chat (consulta RAG com streaming SSE). E partilhada entre os
// dois papeis — farmaceutico e admin. O backend e stateless: o historico
// da conversa vive no cliente e e enviado em cada pedido.

import { apiFetch, ficheiroUrl, getToken, formatarDetalheErro } from './api.js';

let mensagens = [];     // [{role: 'user'|'assistant', conteudo: '...'}]
let sessionId = null;   // UUID gerado no cliente, agrupa registos no audit log

export function renderChat(container) {
    container.innerHTML = `
        <div class="container">
            <div class="stats-bar">
                <div class="stat-card">
                    <div class="stat-value" id="statDocs">-</div>
                    <div class="stat-label">Documentos</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="statChunks">-</div>
                    <div class="stat-label">Chunks Indexados</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="statTipos">-</div>
                    <div class="stat-label">Tipos de Documento</div>
                </div>
            </div>

            <div class="chat-card">
                <div class="chat-header">
                    <span class="chat-header-title">Conversa</span>
                    <button class="chat-new-btn" id="novaConversaBtn" title="Limpa o historico e comeca uma nova conversa">
                        + Nova conversa
                    </button>
                </div>

                <div class="chat-thread" id="chatThread">
                    <div class="chat-empty" id="chatEmpty">
                        Coloque a sua questao para iniciar a conversa.<br>
                        <span class="chat-empty-hint">Pode fazer perguntas de seguimento &mdash; o sistema lembra-se do contexto.</span>
                    </div>
                </div>

                <div class="error-card" id="errorCard">
                    <span class="error-icon">&#9888;</span>
                    <div class="error-text" id="errorText"></div>
                </div>

                <div class="chat-input-area">
                    <div class="filters-row">
                        <span class="filter-label">Filtrar por:</span>
                        <select class="filter-select" id="tipoFilter">
                            <option value="">Todos os documentos</option>
                            <option value="bula">Bulas</option>
                            <option value="monografia">Monografias</option>
                            <option value="guideline">Guidelines</option>
                            <option value="norma">Normas</option>
                        </select>
                    </div>
                    <div class="search-row">
                        <input type="text" class="search-input" id="queryInput"
                            placeholder="Ex: Quais sao os efeitos secundarios do ibuprofeno?" autocomplete="off">
                        <button class="search-btn" id="searchBtn">Enviar</button>
                    </div>
                </div>
            </div>
        </div>
    `;

    sessionId = gerarSessionId();
    document.getElementById('queryInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submitQuery();
    });
    document.getElementById('searchBtn').addEventListener('click', submitQuery);
    document.getElementById('novaConversaBtn').addEventListener('click', novaConversa);
    loadStats();
}

function gerarSessionId() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
}

async function loadStats() {
    try {
        const res = await apiFetch('/documentos');
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('statDocs').textContent = data.total_documentos;
        document.getElementById('statChunks').textContent = data.total_chunks;
        const tipos = new Set(data.documentos.map(d => d.tipo_documento));
        document.getElementById('statTipos').textContent = tipos.size;
    } catch { /* silencioso — o backend pode estar sem documentos ainda */ }
}

async function submitQuery() {
    const input = document.getElementById('queryInput');
    const query = input.value.trim();
    if (!query) return;
    const tipo = document.getElementById('tipoFilter').value || null;
    const btn = document.getElementById('searchBtn');

    // 1. Append imediato da mensagem do utilizador (UI responsiva).
    const userBubbleId = appendUserBubble(query);
    mensagens.push({ role: 'user', conteudo: query });
    input.value = '';

    // 2. Bubble de "a pensar..." durante o pre-amble. E substituida pela
    //    bubble do assistente quando o primeiro evento `meta` chegar.
    const thinkingId = appendThinkingBubble();

    btn.disabled = true;
    btn.textContent = 'A processar...';
    hide('errorCard');

    let textoAcumulado = '';
    let bubbleStream = null;

    try {
        const historiaParaEnviar = mensagens.slice(0, -1);

        // Nao usamos apiPostJson porque queremos manter o ReadableStream para
        // o parse de SSE. apiFetch trata da auth e do 401.
        const res = await apiFetch('/consulta/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query,
                tipo_documento: tipo,
                historia: historiaParaEnviar,
                session_id: sessionId,
            }),
        });

        // Erros (422 / 500) vem como JSON normal, ANTES do stream comecar.
        if (!res.ok) {
            const err = await res.json();
            throw new Error(formatarDetalheErro(err.detail) || 'Erro no servidor');
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Eventos SSE separados por '\n\n'. Mantemos o ultimo pedaco
            // incompleto em buffer para a iteracao seguinte.
            const eventos = buffer.split('\n\n');
            buffer = eventos.pop();

            for (const ev of eventos) {
                if (!ev.startsWith('data: ')) continue;
                let payload;
                try {
                    payload = JSON.parse(ev.slice(6));
                } catch {
                    continue;
                }

                if (payload.tipo === 'meta') {
                    removeBubble(thinkingId);
                    bubbleStream = criarBubbleStreaming(payload, query);
                } else if (payload.tipo === 'token') {
                    textoAcumulado += payload.texto || '';
                    if (bubbleStream) atualizarBubbleStreamingRaw(bubbleStream, textoAcumulado);
                } else if (payload.tipo === 'done') {
                    if (payload.texto_extra) textoAcumulado += payload.texto_extra;
                    if (bubbleStream) finalizarBubbleStreaming(bubbleStream, textoAcumulado);
                } else if (payload.tipo === 'error') {
                    throw new Error(payload.detalhe || 'Erro no pipeline');
                }
            }
        }

        mensagens.push({ role: 'assistant', conteudo: textoAcumulado });
    } catch (err) {
        removeBubble(thinkingId);
        if (bubbleStream && bubbleStream.wrap) bubbleStream.wrap.remove();
        removeBubble(userBubbleId);
        showError(err.message);
        mensagens.pop();
        input.value = query;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Enviar';
        input.focus();
    }
}

function novaConversa() {
    mensagens = [];
    sessionId = gerarSessionId();
    const thread = document.getElementById('chatThread');
    thread.innerHTML = `
        <div class="chat-empty" id="chatEmpty">
            Coloque a sua questao para iniciar a conversa.<br>
            <span class="chat-empty-hint">Pode fazer perguntas de seguimento &mdash; o sistema lembra-se do contexto.</span>
        </div>`;
    hide('errorCard');
    document.getElementById('queryInput').focus();
}

// ============ Render de bubbles ============
function _esconderEmpty() {
    const empty = document.getElementById('chatEmpty');
    if (empty) empty.remove();
}

function _scrollParaFundo() {
    const thread = document.getElementById('chatThread');
    thread.scrollTop = thread.scrollHeight;
}

function appendUserBubble(texto) {
    _esconderEmpty();
    const thread = document.getElementById('chatThread');
    const id = 'user-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6);
    const wrap = document.createElement('div');
    wrap.id = id;
    wrap.className = 'chat-msg chat-msg-user';
    wrap.innerHTML = `<div class="chat-bubble chat-bubble-user">${escapeHtml(texto)}</div>`;
    thread.appendChild(wrap);
    _scrollParaFundo();
    return id;
}

function appendThinkingBubble() {
    _esconderEmpty();
    const thread = document.getElementById('chatThread');
    const id = 'thinking-' + Date.now();
    const wrap = document.createElement('div');
    wrap.id = id;
    wrap.className = 'chat-msg chat-msg-assistant';
    wrap.innerHTML = `
        <div class="chat-bubble chat-bubble-assistant chat-bubble-thinking">
            <div class="thinking-dots"><span></span><span></span><span></span></div>
            <span class="thinking-label">A consultar a documentacao...</span>
        </div>`;
    thread.appendChild(wrap);
    _scrollParaFundo();
    return id;
}

function removeBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// Fase 1: meta recebida — bubble vazia com fontes ja visiveis.
function criarBubbleStreaming(meta, queryOriginal) {
    _esconderEmpty();
    const thread = document.getElementById('chatThread');

    let reformuladaHtml = '';
    if (meta.query_usada && meta.query_usada.trim() !== queryOriginal.trim()) {
        reformuladaHtml = `
            <div class="chat-reformulada" title="Query interpretada apos analise do contexto da conversa">
                Interpretado como: <em>${escapeHtml(meta.query_usada)}</em>
            </div>`;
    }

    let fontesHtml = '';
    if (meta.fontes && meta.fontes.length > 0) {
        const tags = meta.fontes.map(f => construirTagFonte(f)).join('');
        fontesHtml = `
            <div class="chat-sources">
                <div class="sources-title">Fontes Documentais</div>
                <div class="sources-list">${tags}</div>
            </div>`;
    }

    const ctxBadge = meta.contexto_suficiente
        ? '<span class="chat-meta-ok">&#10003; Contexto suficiente</span>'
        : '<span class="chat-meta-warn">&#9888; Contexto limitado</span>';

    const wrap = document.createElement('div');
    wrap.className = 'chat-msg chat-msg-assistant';
    wrap.innerHTML = `
        <div class="chat-bubble chat-bubble-assistant chat-bubble-streaming">
            ${reformuladaHtml}
            <div class="chat-bubble-body"></div>
            <div class="chat-meta-row">
                <span class="chat-meta-chunks">${meta.num_chunks_usados} chunks</span>
                ${ctxBadge}
            </div>
            ${fontesHtml}
        </div>`;
    thread.appendChild(wrap);
    _scrollParaFundo();

    return {
        wrap,
        body: wrap.querySelector('.chat-bubble-body'),
        bubble: wrap.querySelector('.chat-bubble'),
    };
}

// Fase 2: tokens a chegar — texto cru com cursor a piscar. Markdown so no fim.
function atualizarBubbleStreamingRaw(refs, texto) {
    refs.body.innerHTML = `<pre class="chat-body-raw">${escapeHtml(texto)}<span class="chat-cursor"></span></pre>`;
    _scrollParaFundo();
}

// Fase 3: stream terminou — aplicar formatResponse, remover cursor.
function finalizarBubbleStreaming(refs, textoFinal) {
    refs.body.innerHTML = formatResponse(textoFinal);
    refs.bubble.classList.remove('chat-bubble-streaming');
    _scrollParaFundo();
}

function construirTagFonte(f) {
    const label = `${escapeHtml(f.ficheiro || '?')}${f.pagina ? ', p.' + f.pagina : ''}`;
    const tipoBadge = `<span class="source-type">${f.tipo_documento || '?'}</span>`;
    if (!f.tipo_documento || !f.ficheiro) {
        return `<span class="source-tag">${tipoBadge}${label}</span>`;
    }
    const href = ficheiroUrl(f.tipo_documento, f.ficheiro, f.pagina);
    return `<a class="source-tag source-tag-link" href="${href}" target="_blank" rel="noopener"
        title="Abrir ${escapeHtml(f.ficheiro)}${f.pagina ? ' na pagina ' + f.pagina : ''}">${tipoBadge}${label}</a>`;
}

function formatResponse(text) {
    let mainText = text, disclaimer = '';
    const idx = text.indexOf('AVISO:');
    if (idx !== -1) {
        const hr = text.lastIndexOf('---', idx);
        mainText = text.substring(0, hr !== -1 && idx - hr < 10 ? hr : idx).trim();
        disclaimer = text.substring(idx).trim();
    }
    let html = mainText
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^---$/gm, '<hr>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
    html = '<p>' + html + '</p>';
    html = html.replace(/<p>\s*<\/p>/g, '')
        .replace(/<p>\s*(<h[123]>)/g, '$1')
        .replace(/(<\/h[123]>)\s*<\/p>/g, '$1')
        .replace(/<p>\s*(<ul>)/g, '$1')
        .replace(/(<\/ul>)\s*<\/p>/g, '$1')
        .replace(/<p>\s*(<hr>)\s*<\/p>/g, '$1');
    if (disclaimer) html += `<div class="disclaimer">${disclaimer}</div>`;
    return html;
}

// ============ Helpers ============
function show(id) { const el = document.getElementById(id); if (el) el.classList.add('active'); }
function hide(id) { const el = document.getElementById(id); if (el) el.classList.remove('active'); }
function showError(msg) {
    const txt = document.getElementById('errorText');
    if (txt) txt.textContent = msg;
    show('errorCard');
}
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
