const API_BASE = window.location.origin;

        // ==================== Init ====================
        document.addEventListener('DOMContentLoaded', () => {
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

        // ==================== Consulta ====================
        async function submitQuery() {
            const query = document.getElementById('queryInput').value.trim();
            if (!query) return;
            const tipo = document.getElementById('tipoFilter').value || null;
            const btn = document.getElementById('searchBtn');

            btn.disabled = true;
            btn.textContent = 'A processar...';
            show('loading'); hide('responseCard'); hide('errorCard');

            try {
                const res = await fetch(`${API_BASE}/consulta`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, tipo_documento: tipo }),
                });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Erro no servidor');
                }
                const data = await res.json();
                renderResponse(data);
            } catch (err) {
                showError(err.message);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Consultar';
                hide('loading');
            }
        }

        function renderResponse(data) {
            document.getElementById('metaChunks').textContent = `${data.num_chunks_usados} chunks`;
            document.getElementById('metaContexto').innerHTML =
                data.contexto_suficiente ? '&#10003; Contexto suficiente' : '&#9888; Contexto limitado';

            document.getElementById('responseBody').innerHTML = formatResponse(data.resposta);

            const sourcesList = document.getElementById('sourcesList');
            sourcesList.innerHTML = '';
            data.fontes.forEach(fonte => {
                const tag = document.createElement('div');
                tag.className = 'source-tag';
                tag.innerHTML = `<span class="source-type">${fonte.tipo_documento || '?'}</span>
                    ${fonte.ficheiro}${fonte.pagina ? ', p.' + fonte.pagina : ''}`;
                sourcesList.appendChild(tag);
            });
            show('responseCard');
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
                    throw new Error(err.detail || 'Erro no upload');
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