const { createApp, ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } = Vue;

const API = '/api';

createApp({
    setup() {
        const currentView = ref('projects');
        const projects = ref([]);
        const currentProject = ref(null);
        const projectStatus = reactive({ agents: {}, current_phase: '', fix_round: 0 });
        const logs = ref([]);
        const selectedAgent = ref('');
        const selectedArtifact = ref('prd');
        const artifacts = reactive({});
        const llmConfigs = ref([]);
        const providers = ref({});
        const hasDefaultLLM = ref(false);
        const showNewProject = ref(false);
        const showNewLLM = ref(false);
        const logsContainer = ref(null);
        const deliveryReport = reactive({
            project_name: '', can_deliver: false, test_passed: false, security_passed: false,
            test_summary: {}, security_summary: {}, report_markdown: '', artifacts_count: 0,
        });
        const deliveryPreview = reactive({ total_files: 0, files: [] });
        const approvalInfo = reactive({
            approval_enabled: true,
            current_approval: null,
            current_info: null,
            approvals: {},
        });
        const approvalFeedback = ref('');
        const showRerunOptions = ref(false);
        const rerunOptions = ref([]);
        const selectedRerunAgents = ref([]);
        const showForkProject = ref(false);
        const forkData = reactive({ source_project_id: '', name: '', requirement: '', copy_artifacts: true });
        const showApprovalHistory = ref(false);
        const approvalHistoryData = reactive({ point: '', history: [], snapshots: [] });

        const newProject = reactive({ name: '', requirement: '', llm_config_id: '' });
        const newLLM = reactive({
            name: '', provider_id: 'deepseek', api_key: '', base_url: '',
            model: '', temperature: 0.7, max_tokens: 4096, is_default: false,
        });

        let ws = null;
        let statusInterval = null;
        let heartbeatTimer = null;
        let reconnectTimer = null;
        let reconnectDelay = 1000;
        const MAX_RECONNECT_DELAY = 30000;
        const editingArtifact = ref(false);
        const editArtifactContent = ref('');
        const toast = reactive({ show: false, message: '', type: 'info' });

        function showToast(message, type = 'info') {
            toast.message = message;
            toast.type = type;
            toast.show = true;
            clearTimeout(toast._timer);
            toast._timer = setTimeout(() => { toast.show = false; }, 3500);
        }

        const artifactTabs = [
            { key: 'user_requirement', label: '原始需求', icon: 'ri-file-text-line' },
            { key: 'prd', label: 'PRD文档', icon: 'ri-file-list-3-line' },
            { key: 'ui_spec', label: 'UI规范', icon: 'ri-palette-line' },
            { key: 'api_design', label: 'API设计', icon: 'ri-server-line' },
            { key: 'db_schema', label: '数据库设计', icon: 'ri-database-2-line' },
            { key: 'frontend_code', label: '前端代码', icon: 'ri-html5-line' },
            { key: 'backend_code', label: '后端代码', icon: 'ri-code-s-slash-line' },
            { key: 'test_report', label: '测试报告', icon: 'ri-bug-line' },
            { key: 'security_report', label: '安全审计', icon: 'ri-shield-check-line' },
            { key: 'bug_list', label: 'Bug清单', icon: 'ri-error-warning-line' },
        ];

        const currentArtifactContent = computed(() => {
            return artifacts[selectedArtifact.value] || null;
        });

        function hasArtifact(key) {
            return artifacts[key] !== undefined && artifacts[key] !== null;
        }

        async function fetchProjects() {
            try {
                const res = await fetch(`${API}/projects`);
                const data = await res.json();
                projects.value = data.projects || [];
            } catch (e) { console.error(e); }
        }

        async function fetchLLMConfigs() {
            try {
                const [configsRes, providersRes, defaultRes] = await Promise.all([
                    fetch(`${API}/llm/configs`),
                    fetch(`${API}/llm/providers`),
                    fetch(`${API}/llm/default`),
                ]);
                llmConfigs.value = (await configsRes.json()).configs || [];
                providers.value = (await providersRes.json()).providers || {};
                hasDefaultLLM.value = (await defaultRes.json()).has_default || false;
            } catch (e) { console.error(e); }
        }

        async function openProject(project) {
            currentProject.value = project;
            currentView.value = 'workspace';
            selectedAgent.value = '';
            logs.value = [];
            editingArtifact.value = false;
            Object.keys(artifacts).forEach(k => delete artifacts[k]);

            await fetchProjectStatus();
            await fetchArtifacts();
            await fetchApprovalStatus();
            connectWS();

            if (statusInterval) clearInterval(statusInterval);
            statusInterval = setInterval(fetchProjectStatus, 3000);
        }

        async function fetchProjectStatus() {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/projects/${currentProject.value.id}/status`);
                const data = await res.json();
                Object.assign(projectStatus, data);
            } catch (e) { console.error(e); }
        }

        async function fetchArtifacts() {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/projects/${currentProject.value.id}/artifacts`);
                const data = await res.json();
                const arts = data.artifacts || {};
                for (const [k, v] of Object.entries(arts)) {
                    artifacts[k] = v.content;
                }
            } catch (e) { console.error(e); }
        }

        function connectWS() {
            // 先清理之前的连接和定时器
            if (ws) {
                ws.onclose = null;  // 禁止旧连接触发重连
                ws.onerror = null;
                ws.close();
                ws = null;
            }
            if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
            if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }

            if (!currentProject.value) return;

            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${location.host}/ws/${currentProject.value.id}`);

            ws.onopen = () => {
                // 连接成功，重置退避延迟
                reconnectDelay = 1000;

                // 启动客户端心跳：每 20 秒发送 ping
                heartbeatTimer = setInterval(() => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        try {
                            ws.send(JSON.stringify({ type: 'ping' }));
                        } catch (e) {
                            console.error('Heartbeat send error:', e);
                        }
                    }
                }, 20000);
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    // 响应服务端心跳
                    if (data.type === 'ping') {
                        try {
                            ws.send(JSON.stringify({ type: 'pong' }));
                        } catch (e) { /* ignore */ }
                        return;
                    }
                    if (data.type === 'pong') return;  // 忽略 pong
                    handleWSMessage(data);
                } catch (e) { console.error(e); }
            };

            ws.onerror = (event) => {
                console.error('WebSocket error:', event);
                // onerror 后通常会触发 onclose，不在此处理
            };

            ws.onclose = (event) => {
                // 清理心跳
                if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }

                // 只在仍在工作区时重连，使用指数退避
                if (currentProject.value && currentView.value === 'workspace') {
                    console.log(`WebSocket closed (code: ${event.code}), reconnecting in ${reconnectDelay}ms...`);
                    reconnectTimer = setTimeout(() => {
                        connectWS();
                    }, reconnectDelay);
                    // 指数退避：每次翻倍，上限 30s
                    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
                }
            };
        }

        function handleWSMessage(data) {
            if (data.type === 'init_status') {
                Object.assign(projectStatus, { agents: data.agents, current_phase: data.current_phase, fix_round: data.fix_round });
                return;
            }

            logs.value.push(data);
            if (logs.value.length > 500) logs.value = logs.value.slice(-300);

            nextTick(() => {
                if (logsContainer.value) {
                    logsContainer.value.scrollTop = logsContainer.value.scrollHeight;
                }
            });

            if (['agent_start', 'agent_done', 'agent_error', 'phase_change', 'workflow_done'].includes(data.type)) {
                fetchProjectStatus();
            }
            if (['agent_done', 'workflow_done'].includes(data.type)) {
                fetchArtifacts();
            }
            if (data.type === 'approval_required') {
                approvalInfo.current_approval = data.point;
                approvalInfo.current_info = {
                    label: data.label,
                    description: data.description,
                    review_artifacts: data.review_artifacts,
                };
                approvalFeedback.value = '';
                showRerunOptions.value = false;
                selectedRerunAgents.value = [];
                fetchRerunOptions(data.point);
                if (data.review_artifacts && data.review_artifacts.length) {
                    selectedArtifact.value = data.review_artifacts[0];
                }
            }
            if (data.type === 'approval_decided') {
                approvalInfo.current_approval = null;
                approvalInfo.current_info = null;
                showRerunOptions.value = false;
            }
            if (data.type === 'agents_rerun') {
                fetchArtifacts();
            }
            if (data.type === 'workflow_done' || data.type === 'workflow_error') {
                if (currentProject.value) {
                    if (data.type === 'workflow_done') {
                        currentProject.value.status = data.qa_passed ? 'completed' : 'needs_review';
                    } else {
                        currentProject.value.status = 'failed';
                    }
                }
            }
        }

        async function createProject() {
            try {
                const res = await fetch(`${API}/projects`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(newProject),
                });
                const data = await res.json();
                newProject.name = '';
                newProject.requirement = '';
                newProject.llm_config_id = '';
                showNewProject.value = false;
                await fetchProjects();
                const proj = projects.value.find(p => p.id === data.project_id);
                if (proj) openProject(proj);
            } catch (e) { console.error(e); }
        }

        async function startProject() {
            if (!currentProject.value) return;
            try {
                await fetch(`${API}/projects/${currentProject.value.id}/start`, { method: 'POST' });
                currentProject.value.status = 'running';
            } catch (e) { console.error(e); }
        }

        async function stopProject() {
            if (!currentProject.value) return;
            try {
                await fetch(`${API}/projects/${currentProject.value.id}/stop`, { method: 'POST' });
                currentProject.value.status = 'stopped';
            } catch (e) { console.error(e); }
        }

        async function deleteProject(id) {
            if (!confirm('确定删除此项目？')) return;
            try {
                await fetch(`${API}/projects/${id}`, { method: 'DELETE' });
                if (currentProject.value && currentProject.value.id === id) {
                    currentProject.value = null;
                    currentView.value = 'projects';
                }
                await fetchProjects();
            } catch (e) { console.error(e); }
        }

        async function forkProject() {
            try {
                const res = await fetch(`${API}/projects/fork`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(forkData),
                });
                const data = await res.json();
                showForkProject.value = false;
                await fetchProjects();
                const proj = projects.value.find(p => p.id === data.project_id);
                if (proj) openProject(proj);
                showToast('项目已基于模板创建', 'success');
            } catch (e) { console.error(e); }
        }

        function openForkDialog(project) {
            forkData.source_project_id = project.id;
            forkData.name = project.name + ' (副本)';
            forkData.requirement = '';
            forkData.copy_artifacts = true;
            showForkProject.value = true;
        }

        async function fetchApprovalHistory(point) {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/approval/${currentProject.value.id}/history/${point}`);
                if (res.ok) {
                    const data = await res.json();
                    approvalHistoryData.point = data.point;
                    approvalHistoryData.history = data.history;
                    approvalHistoryData.snapshots = data.snapshots || [];
                    showApprovalHistory.value = true;
                }
            } catch (e) { console.error(e); }
        }

        async function createLLMConfig() {
            try {
                await fetch(`${API}/llm/configs`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(newLLM),
                });
                newLLM.name = '';
                newLLM.api_key = '';
                newLLM.base_url = '';
                newLLM.model = '';
                newLLM.is_default = false;
                showNewLLM.value = false;
                await fetchLLMConfigs();
            } catch (e) { console.error(e); }
        }

        async function setDefaultLLM(id) {
            try {
                await fetch(`${API}/llm/configs/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_default: true }),
                });
                await fetchLLMConfigs();
            } catch (e) { console.error(e); }
        }

        async function deleteLLMConfig(id) {
            if (!confirm('确定删除此配置？')) return;
            try {
                await fetch(`${API}/llm/configs/${id}`, { method: 'DELETE' });
                await fetchLLMConfigs();
            } catch (e) { console.error(e); }
        }

        const projectSearch = ref('');
        const testingLLM = ref(false);
        const testResult = ref(null);

        const filteredProjects = computed(() => {
            if (!projectSearch.value) return projects.value;
            const q = projectSearch.value.toLowerCase();
            return projects.value.filter(p =>
                p.name.toLowerCase().includes(q) ||
                (p.requirement || '').toLowerCase().includes(q)
            );
        });

        async function testLLMConnection() {
            testingLLM.value = true;
            testResult.value = null;
            try {
                const res = await fetch(`${API}/llm/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: 'test',
                        provider_id: newLLM.provider_id,
                        api_key: newLLM.api_key,
                        base_url: newLLM.base_url || undefined,
                        model: newLLM.model || undefined,
                    }),
                });
                const data = await res.json();
                testResult.value = data;
                showToast(data.success ? 'LLM 连接成功 ✅' : '连接失败: ' + data.message, data.success ? 'success' : 'error');
            } catch (e) {
                testResult.value = { success: false, message: '网络请求失败' };
                showToast('测试请求失败', 'error');
            } finally {
                testingLLM.value = false;
            }
        }

        function onProviderChange() {
            newLLM.base_url = '';
            newLLM.model = '';
        }

        function providerBaseUrl() {
            const p = providers.value[newLLM.provider_id];
            return p ? p.base_url : '';
        }

        function providerModels() {
            const p = providers.value[newLLM.provider_id];
            return p ? p.models || [] : [];
        }

        function providerDefaultModel() {
            const p = providers.value[newLLM.provider_id];
            return p ? p.default_model || '' : '';
        }

        function providerName(id) {
            const p = providers.value[id];
            return p ? p.name : id;
        }

        function selectAgent(key) {
            selectedAgent.value = key;
        }

        function statusText(s) {
            const map = { created: '待启动', running: '运行中', completed: '已完成', needs_review: '待修复', failed: '失败', stopped: '已停止', interrupted: '已中断' };
            return map[s] || s;
        }

        function phaseText(p) {
            const map = { requirement: '需求分析', design_dev: '设计开发', qa: '质量保障', fix: '修复中', done: '已完成' };
            return map[p] || p;
        }

        function agentIcon(key) {
            const map = {
                product_manager: 'ri-product-hunt-line',
                ui_designer: 'ri-palette-line',
                backend_developer: 'ri-server-line',
                frontend_developer: 'ri-html5-line',
                tester: 'ri-bug-line',
                security_auditor: 'ri-shield-check-line',
            };
            return map[key] || 'ri-robot-line';
        }

        function agentStatusText(agent) {
            const map = { waiting: '等待中', running: '执行中', completed: '已完成', failed: '失败', skipped: '已跳过' };
            let text = map[agent.status] || agent.status;
            if (agent.message) text += ` - ${agent.message}`;
            return text;
        }

        function artifactLabel(key) {
            const tab = artifactTabs.find(t => t.key === key);
            return tab ? tab.label : key;
        }

        function formatArtifact(content) {
            if (typeof content === 'string') return content;
            return JSON.stringify(content, null, 2);
        }

        function formatTime(iso) {
            if (!iso) return '';
            const d = new Date(iso);
            return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
        }

        function formatLogTime(ts) {
            if (!ts) return '';
            const d = new Date(ts * 1000);
            return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
        }

        function logMessage(log) {
            if (log.type === 'agent_start') return `${log.display_name} 开始工作`;
            if (log.type === 'agent_done') return `${log.display_name} 完成工作`;
            if (log.type === 'agent_error') return `${log.display_name} 出错: ${log.error}`;
            if (log.type === 'phase_change') return `进入阶段: ${phaseText(log.phase)}`;
            if (log.type === 'workflow_start') return `工作流启动`;
            if (log.type === 'workflow_done') return `工作流完成 (修复: ${log.fix_rounds || 0}轮, QA: ${log.qa_passed ? '✅通过' : '❌未通过'})`;
            if (log.type === 'workflow_error') return `工作流出错: ${log.error}`;
            return JSON.stringify(log);
        }

        async function openDelivery() {
            if (!currentProject.value) return;
            currentView.value = 'delivery';
            await Promise.all([fetchDeliveryReport(), fetchDeliveryPreview()]);
        }

        async function fetchDeliveryReport() {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/delivery/${currentProject.value.id}/report`);
                if (res.ok) {
                    const data = await res.json();
                    Object.assign(deliveryReport, data);
                }
            } catch (e) { console.error(e); }
        }

        async function fetchDeliveryPreview() {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/delivery/${currentProject.value.id}/preview`);
                if (res.ok) {
                    const data = await res.json();
                    deliveryPreview.total_files = data.total_files || 0;
                    deliveryPreview.files = data.files || [];
                }
            } catch (e) { console.error(e); }
        }

        function downloadProject() {
            if (!currentProject.value) return;
            window.open(`${API}/delivery/${currentProject.value.id}/download`, '_blank');
        }

        async function previewFile(path) {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/delivery/${currentProject.value.id}/file/${encodeURIComponent(path)}`);
                if (res.ok) {
                    const data = await res.json();
                    selectedArtifact.value = '__delivery_file__';
                    artifacts['__delivery_file__'] = `// ${data.description}\n// ${data.path}\n\n${data.content}`;
                }
            } catch (e) { console.error(e); }
        }

        function fileIcon(path) {
            if (path.endsWith('.py')) return 'ri-python-line';
            if (path.endsWith('.html')) return 'ri-html5-line';
            if (path.endsWith('.js')) return 'ri-javascript-line';
            if (path.endsWith('.css')) return 'ri-css3-line';
            if (path.endsWith('.md')) return 'ri-markdown-line';
            if (path.endsWith('.json')) return 'ri-braces-line';
            if (path.endsWith('.txt')) return 'ri-file-text-line';
            if (path.endsWith('.sql')) return 'ri-database-2-line';
            return 'ri-file-line';
        }

        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }

        async function fetchApprovalStatus() {
            if (!currentProject.value) return;
            try {
                const res = await fetch(`${API}/approval/${currentProject.value.id}/status`);
                if (res.ok) {
                    const data = await res.json();
                    approvalInfo.approval_enabled = data.approval_enabled;
                    approvalInfo.approvals = data.approvals;
                    if (data.current_approval) {
                        approvalInfo.current_approval = data.current_approval;
                        approvalInfo.current_info = data.current_info;
                    }
                }
            } catch (e) { console.error(e); }
        }

        async function fetchRerunOptions(point) {
            if (!currentProject.value || !point) return;
            try {
                const res = await fetch(`${API}/approval/${currentProject.value.id}/rerun-options/${point}`);
                if (res.ok) {
                    const data = await res.json();
                    rerunOptions.value = data.options || [];
                }
            } catch (e) { console.error(e); }
        }

        async function submitApproval(action, needFeedback = false) {
            if (!currentProject.value) return;
            if (needFeedback && !approvalFeedback.value.trim()) return;

            try {
                const body = {
                    action: action,
                    feedback: approvalFeedback.value,
                    rerun_agents: action === 'rerun' ? selectedRerunAgents.value : [],
                };
                await fetch(`${API}/approval/${currentProject.value.id}/decide`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                approvalFeedback.value = '';
                showRerunOptions.value = false;
                selectedRerunAgents.value = [];
            } catch (e) { console.error(e); }
        }

        function startEditArtifact() {
            if (selectedArtifact.value.startsWith('__')) return;  // 虚拟产出物不可编辑
            const content = artifacts[selectedArtifact.value];
            editArtifactContent.value = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
            editingArtifact.value = true;
        }

        async function saveArtifactEdit() {
            if (!currentProject.value) return;
            try {
                await fetch(`${API}/projects/${currentProject.value.id}/artifacts/${selectedArtifact.value}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: editArtifactContent.value }),
                });
                // 更新本地缓存
                try {
                    artifacts[selectedArtifact.value] = JSON.parse(editArtifactContent.value);
                } catch (e) {
                    artifacts[selectedArtifact.value] = editArtifactContent.value;
                }
                editingArtifact.value = false;
            } catch (e) { console.error(e); }
        }

        function cancelEditArtifact() {
            editingArtifact.value = false;
        }

        function artifactIcon(key) {
            const map = {
                user_requirement: 'ri-file-text-line',
                prd: 'ri-file-list-3-line',
                ui_spec: 'ri-palette-line',
                api_design: 'ri-server-line',
                db_schema: 'ri-database-2-line',
                frontend_code: 'ri-html5-line',
                backend_code: 'ri-code-s-slash-line',
                test_report: 'ri-bug-line',
                security_report: 'ri-shield-check-line',
                bug_list: 'ri-error-warning-line',
            };
            return map[key] || 'ri-file-line';
        }

        watch(currentView, (v) => {
            if (v !== 'workspace') {
                if (ws) { ws.onclose = null; ws.close(); ws = null; }
                if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
                if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
                if (statusInterval) { clearInterval(statusInterval); statusInterval = null; }
            }
        });

        onMounted(() => {
            fetchProjects();
            fetchLLMConfigs();
        });

        onUnmounted(() => {
            if (ws) { ws.onclose = null; ws.close(); }
            if (heartbeatTimer) clearInterval(heartbeatTimer);
            if (reconnectTimer) clearTimeout(reconnectTimer);
            if (statusInterval) clearInterval(statusInterval);
        });

        return {
            currentView, projects, currentProject, projectStatus, logs,
            selectedAgent, selectedArtifact, artifacts, llmConfigs, providers,
            hasDefaultLLM, showNewProject, showNewLLM, logsContainer,
            deliveryReport, deliveryPreview,
            approvalInfo, approvalFeedback, showRerunOptions, rerunOptions, selectedRerunAgents,
            showForkProject, forkData, forkProject, openForkDialog,
            showApprovalHistory, approvalHistoryData, fetchApprovalHistory,
            newProject, newLLM, artifactTabs, currentArtifactContent,
            hasArtifact, fetchProjects, openProject, createProject,
            startProject, stopProject, deleteProject, createLLMConfig,
            setDefaultLLM, deleteLLMConfig, onProviderChange, testLLMConnection, testingLLM, testResult,
            providerBaseUrl, providerModels, providerDefaultModel, providerName,
            projectSearch, filteredProjects, toast, showToast,
            selectAgent, statusText, phaseText, agentIcon, agentStatusText,
            artifactLabel, artifactIcon, formatArtifact, formatTime, formatLogTime, logMessage,
            editingArtifact, editArtifactContent, startEditArtifact, saveArtifactEdit, cancelEditArtifact,
            openDelivery, downloadProject, previewFile, fileIcon, formatFileSize,
            submitApproval, fetchApprovalStatus,
        };
    },
}).mount('#app');
