const API_BASE = window.location.origin;

        // ==================== Estado da conversa ====================
        // Historico mantido no cliente — o backend e stateless. Cada pedido a
        // /consulta envia o array completo, e o backend usa-o para reformular
        // a query como standalone antes do retrieval.
        let mensagens = [];          // [{role: 'user'|'assistant', conteudo: '...'}]
        let sessionId = null;        // UUID gerado pelo frontend, agrupa no audit log

        function gerarSessionId() {
            if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
            // Fallback simples se randomUUID nao estiver disponivel
            return 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
        }

        // ==================== Init ====================
        document.addEventListener('DOMContentLoaded', () => {
            sessionId = gerarSessionId();
            checkHealth();
            loadStats();
            document.getElementById('queryInput').addEventListener('keydown', (e) => {
                if (e.key === 'Enter') submitQuery();
            });
        });

        // ==================== Tabs ====================
        function switchTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

            // Show selected
            document.getElementById('tab-' + tabName).classList.add('active');
            event.target.classList.add('active');

            // Load data on tab switch
            if (tabName === 'documentos') loadDocumentos();
            if (tabName === 'auditoria') loadAudit();
        }

        // ==================== Health ====================
        async function checkHealth() {
            try {
                const res = await fetch(`${API_BASE}/health`);
                const data = await res.json();
                const dot = document.getElementById('statusDot');
                const text = document.getElementById('statusText');
                dot.classList.remove('offline', 'warning');
                if (data.status === 'ok') {
                    text.textContent = `Operacional (${data.total_pontos} pontos)`;
                } else if (data.status === 'vazio') {
                    dot.classList.add('warning');
                    text.textContent = 'Pronto - sem documentos';
                } else {
                    dot.classList.add('offline');
                    text.textContent = 'Sistema degradado';
                }
            } catch {
                const dot = document.getElementById('statusDot');
                dot.classList.remove('warning');
                dot.classList.add('offline');
                document.getElementById('statusText').textContent = 'Sem ligacao';
            }
        }

        // ==================== Stats ====================
        async function loadStats() {
            try {
                const res = await fetch(`${API_BASE}/documentos`);
                const data = await res.json();
                document.getElementById('statDocs').textContent = data.total_documentos;
                document.getElementById('statChunks').textContent = data.total_chunks;
                const tipos = new Set(data.documentos.map(d => d.tipo_documento));
                document.getElementById('statTipos').textContent = tipos.size;
            } catch { /* silencioso */ }
        }

        // ==================== Consulta (chat com streaming SSE) ====================
        async function submitQuery() {
            const input = document.getElementById('queryInput');
            const query = input.value.trim();
            if (!query) return;
            const tipo = document.getElementById('tipoFilter').value || null;
            const btn = document.getElementById('searchBtn');

            // 1. Append imediato da mensagem do utilizador (UI responsiva)
            const userBubbleId = appendUserBubble(query);
            mensagens.push({ role: 'user', conteudo: query });
            input.value = '';

            // 2. Bubble de "a pensar..." durante o pre-amble (input_guard,
            //    reformulator, retrieval, reranker, CRAG). Esta bubble e
            //    substituida pela do assistente quando o primeiro evento `meta`
            //    chegar (~7-12s).
            const thinkingId = appendThinkingBubble();

            btn.disabled = true;
            btn.textContent = 'A processar...';
            hide('errorCard');

            let textoAcumulado = '';
            let bubbleStream = null;  // {wrap, body} elementos da bubble durante stream

            try {
                const historiaParaEnviar = mensagens.slice(0, -1);

                const res = await fetch(`${API_BASE}/consulta/stream`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query,
                        tipo_documento: tipo,
                        historia: historiaParaEnviar,
                        session_id: sessionId,
                    }),
                });

                // Erros de validacao (422) ou HTTP 500 vem como JSON normal,
                // ANTES do stream comecar. So tratamos como stream se res.ok.
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(formatErrorDetail(err.detail) || 'Erro no servidor');
                }

                // Parse de Server-Sent Events a partir do ReadableStream
                const reader = res.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });

                    // Eventos SSE estao separados por '\n\n'. Mantemos o ultimo
                    // pedaco incompleto em buffer para o ciclo seguinte.
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
                            // Primeira coisa que chega — substituir thinking pela bubble real
                            removeBubble(thinkingId);
                            bubbleStream = criarBubbleStreaming(payload, query);
                        } else if (payload.tipo === 'token') {
                            textoAcumulado += payload.texto || '';
                            if (bubbleStream) atualizarBubbleStreamingRaw(bubbleStream, textoAcumulado);
                        } else if (payload.tipo === 'done') {
                            if (payload.texto_extra) textoAcumulado += payload.texto_extra;
                            if (bubbleStream) finalizarBubbleStreaming(bubbleStream, textoAcumulado, payload);
                        } else if (payload.tipo === 'error') {
                            throw new Error(payload.detalhe || 'Erro no pipeline');
                        }
                    }
                }

                // Push da resposta completa ao historico (apos o stream terminar)
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

        // ==================== Render de bubbles ====================
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

        // ============== Bubble streaming (3 fases) ==============
        // Fase 1: meta recebida -> criar bubble vazia com fontes ja visiveis
        function criarBubbleStreaming(meta, queryOriginal) {
            _esconderEmpty();
            const thread = document.getElementById('chatThread');

            // Linha "Interpretado como:" se houve reformulacao contextual
            let reformuladaHtml = '';
            if (meta.query_usada && meta.query_usada.trim() !== queryOriginal.trim()) {
                reformuladaHtml = `
                    <div class="chat-reformulada" title="Query interpretada apos analise do contexto da conversa">
                        Interpretado como: <em>${escapeHtml(meta.query_usada)}</em>
                    </div>`;
            }

            // Fontes (clicaveis) — visiveis logo no inicio do stream
            let fontesHtml = '';
            if (meta.fontes && meta.fontes.length > 0) {
                const tags = meta.fontes.map(f => {
                    const label = `${escapeHtml(f.ficheiro)}${f.pagina ? ', p.' + f.pagina : ''}`;
                    const tipoBadge = `<span class="source-type">${f.tipo_documento || '?'}</span>`;
                    if (!f.tipo_documento || !f.ficheiro) {
                        return `<span class="source-tag">${tipoBadge}${label}</span>`;
                    }
                    const href = `${API_BASE}/ficheiros/${encodeURIComponent(f.tipo_documento)}/${encodeURIComponent(f.ficheiro)}${f.pagina ? '#page=' + f.pagina : ''}`;
                    return `<a class="source-tag source-tag-link" href="${href}" target="_blank" rel="noopener"
                        title="Abrir ${escapeHtml(f.ficheiro)}${f.pagina ? ' na pagina ' + f.pagina : ''}">${tipoBadge}${label}</a>`;
                }).join('');
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

        // Fase 2: tokens a chegar -> mostrar texto cru com cursor a piscar.
        //         Re-formatamos com markdown so no fim para evitar render parcial estranho.
        function atualizarBubbleStreamingRaw(refs, texto) {
            refs.body.innerHTML = `<pre class="chat-body-raw">${escapeHtml(texto)}<span class="chat-cursor"></span></pre>`;
            _scrollParaFundo();
        }

        // Fase 3: stream terminou -> aplicar formatResponse, remover cursor/streaming class
        function finalizarBubbleStreaming(refs, textoFinal, doneEvent) {
            refs.body.innerHTML = formatResponse(textoFinal);
            refs.bubble.classList.remove('chat-bubble-streaming');
            _scrollParaFundo();
        }

        // Bubble single-shot (usado em fallback ou caso /consulta nao-stream seja chamado)
        function appendAssistantBubble(data, queryOriginal) {
            _esconderEmpty();
            const thread = document.getElementById('chatThread');

            // Cabecalho de transparencia: se a query foi reformulada, mostrar discreto
            let reformuladaHtml = '';
            if (data.query_usada && data.query_usada.trim() !== queryOriginal.trim()) {
                reformuladaHtml = `
                    <div class="chat-reformulada" title="Query interpretada apos analise do contexto da conversa">
                        Interpretado como: <em>${escapeHtml(data.query_usada)}</em>
                    </div>`;
            }

            // Meta-informacao (chunks + contexto)
            const ctxBadge = data.contexto_suficiente
                ? '<span class="chat-meta-ok">&#10003; Contexto suficiente</span>'
                : '<span class="chat-meta-warn">&#9888; Contexto limitado</span>';

            // Fontes — clicaveis: abrem o PDF na pagina citada (#page=N e suportado
            // nativamente pelos viewers de PDF do Chrome/Edge/Firefox).
            let fontesHtml = '';
            if (data.fontes && data.fontes.length > 0) {
                const tags = data.fontes.map(f => {
                    const label = `${escapeHtml(f.ficheiro)}${f.pagina ? ', p.' + f.pagina : ''}`;
                    const tipo = f.tipo_documento || '?';
                    const tipoBadge = `<span class="source-type">${tipo}</span>`;
                    // Se nao tivermos tipo/ficheiro nao conseguimos construir o URL — fica como span
                    if (!f.tipo_documento || !f.ficheiro) {
                        return `<span class="source-tag">${tipoBadge}${label}</span>`;
                    }
                    const ficheiroEnc = encodeURIComponent(f.ficheiro);
                    const hash = f.pagina ? `#page=${f.pagina}` : '';
                    const href = `${API_BASE}/ficheiros/${encodeURIComponent(f.tipo_documento)}/${ficheiroEnc}${hash}`;
                    return `<a class="source-tag source-tag-link" href="${href}" target="_blank" rel="noopener"
                        title="Abrir ${escapeHtml(f.ficheiro)}${f.pagina ? ' na pagina ' + f.pagina : ''}">${tipoBadge}${label}</a>`;
                }).join('');
                fontesHtml = `
                    <div class="chat-sources">
                        <div class="sources-title">Fontes Documentais</div>
                        <div class="sources-list">${tags}</div>
                    </div>`;
            }

            const wrap = document.createElement('div');
            wrap.className = 'chat-msg chat-msg-assistant';
            wrap.innerHTML = `
                <div class="chat-bubble chat-bubble-assistant">
                    ${reformuladaHtml}
                    <div class="chat-bubble-body">${formatResponse(data.resposta)}</div>
                    <div class="chat-meta-row">
                        <span class="chat-meta-chunks">${data.num_chunks_usados} chunks</span>
                        ${ctxBadge}
                    </div>
                    ${fontesHtml}
                </div>`;
            thread.appendChild(wrap);
            _scrollParaFundo();
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

        // ==================== Upload ====================
        async function uploadDocument() {
            const fileInput = document.getElementById('uploadFile');
            const tipo = document.getElementById('uploadTipo').value;
            const btn = document.getElementById('uploadBtn');
            const status = document.getElementById('uploadStatus');

            if (!fileInput.files || fileInput.files.length === 0) {
                status.className = 'upload-status active error';
                status.innerHTML = '&#9888; Selecione um ficheiro PDF.';
                return;
            }

            const file = fileInput.files[0];
            if (!file.name.toLowerCase().endsWith('.pdf')) {
                status.className = 'upload-status active error';
                status.innerHTML = '&#9888; Apenas ficheiros PDF sao aceites.';
                return;
            }

            btn.disabled = true;
            btn.textContent = 'A processar...';
            status.className = 'upload-status active loading';
            status.innerHTML = '<div class="spinner-small"></div> A enviar e indexar o documento...';

            try {
                const formData = new FormData();
                formData.append('ficheiro', file);
                formData.append('tipo_documento', tipo);

                const res = await fetch(`${API_BASE}/upload`, {
                    method: 'POST',
                    body: formData,
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(formatErrorDetail(err.detail) || 'Erro no upload');
                }

                const data = await res.json();
                status.className = 'upload-status active success';
                const perdidos = data.chunks_gerados - data.pontos_indexados;
                const aviso = perdidos > 0 ? ` &#9888; ${perdidos} chunk(s) nao foram indexados.` : '';
                status.innerHTML = `&#10003; Documento indexado: ${data.chunks_gerados} chunks gerados, ${data.pontos_indexados} indexados, ${data.total_na_collection} pontos totais.${aviso}`;

                // Atualizar a lista de documentos e stats
                fileInput.value = '';
                loadDocumentos();
                loadStats();
                checkHealth();
            } catch (err) {
                status.className = 'upload-status active error';
                status.innerHTML = `&#9888; ${err.message}`;
            } finally {
                btn.disabled = false;
                btn.textContent = 'Enviar e Indexar';
            }
        }

        // ==================== Documentos ====================
        async function loadDocumentos() {
            const grid = document.getElementById('docsGrid');
            try {
                const res = await fetch(`${API_BASE}/documentos`);
                const data = await res.json();

                document.getElementById('statDocs2').textContent = data.total_documentos;
                document.getElementById('statChunks2').textContent = data.total_chunks;

                let totalPaginas = 0;
                data.documentos.forEach(d => totalPaginas += d.paginas.length);
                document.getElementById('statPaginas').textContent = totalPaginas;

                if (data.documentos.length === 0) {
                    grid.innerHTML = '<div class="audit-empty">Nenhum documento indexado.</div>';
                    return;
                }

                grid.innerHTML = '';
                data.documentos.forEach(doc => {
                    const typeClass = 'doc-type-' + (doc.tipo_documento || 'desconhecido');
                    const card = document.createElement('div');
                    card.className = 'doc-card';
                    card.innerHTML = `
                        <div class="doc-card-header">
                            <span class="doc-name">${doc.ficheiro}</span>
                            <span class="doc-type-badge ${typeClass}">${doc.tipo_documento}</span>
                        </div>
                        <div class="doc-card-body">
                            <div class="doc-stat-row">
                                <span class="doc-stat-label">Chunks indexados</span>
                                <span class="doc-stat-value">${doc.total_chunks}</span>
                            </div>
                            <div class="doc-stat-row">
                                <span class="doc-stat-label">Paginas</span>
                                <span class="doc-stat-value">${doc.paginas.length}</span>
                            </div>
                            <div class="doc-stat-row">
                                <span class="doc-stat-label">Intervalo de paginas</span>
                                <span class="doc-stat-value">${doc.paginas[0]} - ${doc.paginas[doc.paginas.length - 1]}</span>
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            } catch {
                grid.innerHTML = '<div class="audit-empty">Erro ao carregar documentos.</div>';
            }
        }

        // ==================== Auditoria ====================
        async function loadAudit() {
            const body = document.getElementById('auditBody');
            try {
                const res = await fetch(`${API_BASE}/audit`);
                const data = await res.json();

                document.getElementById('auditCount').textContent = `${data.total} registos`;

                if (data.total === 0) {
                    body.innerHTML = '<tr><td colspan="6" class="audit-empty">Nenhuma consulta registada hoje.</td></tr>';
                    return;
                }

                body.innerHTML = '';
                // Mostrar do mais recente para o mais antigo
                const registos = data.registos.reverse();
                registos.forEach((reg, i) => {
                    const hora = new Date(reg.timestamp).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                    const fontes = (reg.fontes || []).map(f =>
                        `<span class="audit-source-mini">${f.ficheiro || '?'}</span>`
                    ).join('');
                    const ctxClass = reg.contexto_suficiente ? 'audit-context-ok' : 'audit-context-warn';
                    const ctxText = reg.contexto_suficiente ? 'OK' : 'Limitado';
                    const duracao = reg.duracao_segundos ? reg.duracao_segundos.toFixed(1) + 's' : '-';

                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td class="audit-time">${hora}</td>
                        <td class="audit-query" title="${escapeHtml(reg.query_original)}">${escapeHtml(reg.query_original)}</td>
                        <td><div class="audit-sources">${fontes}</div></td>
                        <td><span class="audit-context-badge ${ctxClass}">${ctxText}</span></td>
                        <td><span class="audit-duration">${duracao}</span></td>
                        <td><button class="audit-expand-btn" onclick="toggleAuditDetail(${i})">Ver</button></td>
                    `;
                    body.appendChild(tr);

                    // Detail row
                    const detailTr = document.createElement('tr');
                    detailTr.id = `audit-detail-${i}`;
                    detailTr.style.display = 'none';
                    detailTr.innerHTML = `
                        <td colspan="6" style="padding:0;">
                            <div style="padding:1rem 1.25rem; background:#f8fafc; border-top:1px solid var(--border);">
                                <div class="audit-detail-label">Query usada</div>
                                <p style="margin-bottom:0.75rem; font-size:0.85rem;">${escapeHtml(reg.query_usada)}</p>
                                <div class="audit-detail-label">Resposta</div>
                                <div class="audit-detail-response">${escapeHtml(reg.resposta)}</div>
                            </div>
                        </td>
                    `;
                    body.appendChild(detailTr);
                });
            } catch {
                body.innerHTML = '<tr><td colspan="6" class="audit-empty">Erro ao carregar auditoria.</td></tr>';
            }
        }

        function toggleAuditDetail(index) {
            const row = document.getElementById(`audit-detail-${index}`);
            row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
        }

        // ==================== Helpers ====================
        function show(id) { document.getElementById(id).classList.add('active'); }
        function hide(id) { document.getElementById(id).classList.remove('active'); }
        function showError(msg) { document.getElementById('errorText').textContent = msg; show('errorCard'); }
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        }

        // Formata o campo `detail` de uma resposta de erro do FastAPI.
        // - HTTPException levantadas pela nossa API: string simples
        // - Erros de validacao do Pydantic (422): array de objectos
        //   [{loc: [...], msg: '...', type: '...'}, ...]
        function formatErrorDetail(detail) {
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
            if (typeof detail === 'object') {
                if (typeof detail.msg === 'string') return detail.msg;
                return JSON.stringify(detail);
            }
            return String(detail);
        }