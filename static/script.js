document.addEventListener('DOMContentLoaded', async () => {
    console.log("🎙️ A.R.I.A Day 27 - Advanced Voice Agent with Configuration Panel");
    
    // Global variables
    window.audioChunks = [];
    window.currentTurnAudio = null;
    window.audioContext = null;
    let isPlayingAudio = false;
    let currentUserTranscript = '';
    let isRecording = false;
    let recordingAudioContext;
    let processor;
    
    // WebSocket Connection
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    // Configuration Management Class
    class ConfigurationManager {
        constructor() {
            this.apiKeys = {};
            this.useEnvKeys = true;
            this.serviceStatus = {
                'assemblyai': false,
                'gemini': false,
                'murf': false,
                'tavily': false
            };
            this.initializeConfig();
        }
        
        async initializeConfig() {
            console.log("🔧 Initializing configuration manager...");
            
            // Load saved preferences
            const saved = localStorage.getItem('aria_config_day27');
            if (saved) {
                try {
                    const config = JSON.parse(saved);
                    this.useEnvKeys = config.use_env_keys !== false; // Default to true
                    document.getElementById('use-env-keys').checked = this.useEnvKeys;
                } catch (e) {
                    console.error('Error loading saved config:', e);
                }
            }
            
            // Check initial status
            await this.checkAllAPIs();
        }
        
        async saveApiKey(service, key) {
            if (!key || key.length < 5) {
                this.showSystemMessage(`❌ Invalid ${service} API key`, 'error');
                return false;
            }
            
            try {
                const response = await fetch('/api/config/keys', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        keys: {[service]: key}
                    })
                });
                
                const result = await response.json();
                if (response.ok && result.success) {
                    this.apiKeys[service] = key;
                    this.saveToLocalStorage();
                    this.showSystemMessage(`✅ ${service} API key saved successfully`);
                    return true;
                } else {
                    this.showSystemMessage(`❌ Failed to save ${service} key: ${result.message || 'Unknown error'}`, 'error');
                    return false;
                }
            } catch (error) {
                console.error(`Error saving ${service} key:`, error);
                this.showSystemMessage(`❌ Error saving ${service} key: ${error.message}`, 'error');
                return false;
            }
        }
        
        async testApiKey(service) {
            const statusElement = document.getElementById(`${service}-status`);
            const testButton = document.getElementById(`test-${service}`);
            
            // Update UI to show testing state
            statusElement.className = 'api-status status-testing';
            testButton.disabled = true;
            testButton.innerHTML = '<i class="fas fa-spinner fa-spin text-sm"></i>';
            
            try {
                const response = await fetch(`/api/config/test/${service}`);
                const result = await response.json();
                
                if (result.connected) {
                    statusElement.className = 'api-status status-connected';
                    this.serviceStatus[service] = true;
                    this.showSystemMessage(`✅ ${service}: ${result.message}`);
                } else {
                    statusElement.className = 'api-status status-error';
                    this.serviceStatus[service] = false;
                    this.showSystemMessage(`❌ ${service}: ${result.error}`, 'error');
                }
                
                this.updateOverallStatus();
                return result.connected;
                
            } catch (error) {
                statusElement.className = 'api-status status-error';
                this.serviceStatus[service] = false;
                this.showSystemMessage(`❌ ${service} test failed: ${error.message}`, 'error');
                return false;
            } finally {
                // Reset button
                testButton.disabled = false;
                testButton.innerHTML = '<i class="fas fa-plug text-sm"></i>';
            }
        }
        
        async checkAllAPIs() {
            console.log("🔍 Checking all API configurations...");
            
            try {
                const response = await fetch('/api/config/status');
                const status = await response.json();
                
                // Update individual service indicators
                Object.keys(status.api_keys).forEach(service => {
                    const statusElement = document.getElementById(`${service}-status`);
                    if (statusElement) {
                        const isConfigured = status.api_keys[service];
                        statusElement.className = isConfigured 
                            ? 'api-status status-connected' 
                            : 'api-status status-error';
                        this.serviceStatus[service] = isConfigured;
                    }
                });
                
                // Update overall health
                this.updateOverallStatus(status.overall_health);
                
                // Update status summary
                this.updateStatusSummary(status);
                
            } catch (error) {
                console.error('Error checking API status:', error);
                this.showSystemMessage(`❌ Failed to check API status: ${error.message}`, 'error');
            }
        }
        
        updateOverallStatus(overallHealth = null) {
            const healthStatus = document.getElementById('api-health-status');
            if (!healthStatus) return;
            
            const health = overallHealth !== null ? overallHealth : 
                          Object.values(this.serviceStatus).filter(Boolean).length >= 3;
            
            healthStatus.className = health 
                ? 'w-3 h-3 bg-green-500 rounded-full shadow-sm'
                : 'w-3 h-3 bg-red-500 rounded-full shadow-sm';
        }
        
        updateStatusSummary(status) {
            const summaryElement = document.getElementById('config-status-summary');
            const messageElement = document.getElementById('status-message');
            const overallIndicator = document.getElementById('overall-status-indicator');
            
            if (!summaryElement || !messageElement || !overallIndicator) return;
            
            const configuredCount = status.total_configured || 0;
            const requiredCount = 3; // assemblyai, gemini, murf are required
            
            if (status.overall_health) {
                overallIndicator.className = 'api-status status-connected';
                messageElement.textContent = `All required services configured (${configuredCount}/3)`;
                messageElement.className = 'text-xs text-green-400';
            } else if (configuredCount > 0) {
                overallIndicator.className = 'api-status status-warning';
                messageElement.textContent = `Partially configured (${configuredCount}/3). Missing: ${status.missing_services?.join(', ')}`;
                messageElement.className = 'text-xs text-yellow-400';
            } else {
                overallIndicator.className = 'api-status status-error';
                messageElement.textContent = 'No API keys configured. Please add your keys below.';
                messageElement.className = 'text-xs text-red-400';
            }
        }
        
        async toggleEnvKeys(useEnv) {
            try {
                const response = await fetch('/api/config/toggle-env', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({use_env: useEnv})
                });
                
                const result = await response.json();
                if (response.ok && result.success) {
                    this.useEnvKeys = useEnv;
                    this.saveToLocalStorage();
                    this.showSystemMessage(`✅ ${useEnv ? 'Using' : 'Not using'} environment variables`);
                    // Recheck status with new preference
                    await this.checkAllAPIs();
                } else {
                    throw new Error(result.message || 'Failed to toggle environment keys');
                }
            } catch (error) {
                console.error('Error toggling env keys:', error);
                this.showSystemMessage(`❌ Error toggling environment keys: ${error.message}`, 'error');
                // Revert checkbox
                document.getElementById('use-env-keys').checked = this.useEnvKeys;
            }
        }
        
        saveToLocalStorage() {
            const config = {
                use_env_keys: this.useEnvKeys,
                timestamp: new Date().toISOString()
            };
            localStorage.setItem('aria_config_day27', JSON.stringify(config));
        }
        
        async exportConfig() {
            try {
                const response = await fetch('/api/config/export');
                const config = await response.json();
                
                const dataStr = JSON.stringify(config, null, 2);
                const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
                
                const exportFileDefaultName = `aria_day27_config_${new Date().toISOString().split('T')[0]}.json`;
                
                const linkElement = document.createElement('a');
                linkElement.setAttribute('href', dataUri);
                linkElement.setAttribute('download', exportFileDefaultName);
                linkElement.click();
                
                this.showSystemMessage('✅ Configuration exported successfully');
                
            } catch (error) {
                console.error('Export error:', error);
                this.showSystemMessage(`❌ Export failed: ${error.message}`, 'error');
            }
        }
        
        showSystemMessage(message, type = 'info') {
            const systemMessages = document.getElementById('system-messages');
            if (!systemMessages) return;
            
            const messageElement = document.createElement('div');
            const timestamp = new Date().toLocaleTimeString();
            const iconClass = type === 'error' ? 'fas fa-exclamation-circle' : 
                             type === 'success' ? 'fas fa-check-circle' : 'fas fa-info-circle';
            const colorClass = type === 'error' ? 'text-red-400' : 
                              type === 'success' ? 'text-green-400' : 'text-blue-400';
            
            messageElement.className = `${colorClass} text-sm`;
            messageElement.innerHTML = `
                <i class="${iconClass} mr-2"></i>
                <span class="text-gray-500">[${timestamp}]</span> ${message}
            `;
            
            systemMessages.appendChild(messageElement);
            systemMessages.scrollTop = systemMessages.scrollHeight;
            
            // Remove old messages (keep last 10)
            while (systemMessages.children.length > 10) {
                systemMessages.removeChild(systemMessages.firstChild);
            }
        }
    }
    
    // Initialize configuration manager
    const configManager = new ConfigurationManager();

    // Audio Context Management
    async function initAudioContext() {
        if (!window.audioContext || window.audioContext.state === 'closed') {
            try {
                window.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 44100
                });
                console.log(`✅ AudioContext initialized: ${window.audioContext.state}`);
            } catch (error) {
                console.error('❌ AudioContext init failed:', error);
                throw error;
            }
        }
        
        if (window.audioContext.state === 'suspended') {
            try {
                await window.audioContext.resume();
                console.log('🔊 AudioContext resumed');
            } catch (error) {
                console.warn('⚠️ AudioContext resume failed:', error);
            }
        }
        
        return window.audioContext;
    }

    // Audio Processing Functions
    function base64ToUint8Array(base64) {
        const binary = atob(base64);
        const len = binary.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes;
    }

    function createWavHeader(dataLength, sampleRate = 44100, numChannels = 1, bitDepth = 16) {
        const blockAlign = (numChannels * bitDepth) / 8;
        const byteRate = sampleRate * blockAlign;
        const buffer = new ArrayBuffer(44);
        const view = new DataView(buffer);

        function writeStr(offset, str) {
            for (let i = 0; i < str.length; i++) {
                view.setUint8(offset + i, str.charCodeAt(i));
            }
        }

        writeStr(0, "RIFF");
        view.setUint32(4, 36 + dataLength, true);
        writeStr(8, "WAVE");
        writeStr(12, "fmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, byteRate, true);
        view.setUint16(32, blockAlign, true);
        view.setUint16(34, bitDepth, true);
        writeStr(36, "data");
        view.setUint32(40, dataLength, true);

        return new Uint8Array(buffer);
    }

    function playCombinedWavChunks(base64Chunks) {
        const pcmData = [];
        for (let i = 0; i < base64Chunks.length; i++) {
            const bytes = base64ToUint8Array(base64Chunks[i]);
            if (i === 0) {
                pcmData.push(bytes.slice(44)); // skip header in first chunk
            } else {
                pcmData.push(bytes); // entire chunk is raw PCM
            }
        }

        const totalPcm = new Uint8Array(pcmData.reduce((sum, c) => sum + c.length, 0));
        let offset = 0;
        for (const part of pcmData) {
            totalPcm.set(part, offset);
            offset += part.length;
        }

        const wavHeader = createWavHeader(totalPcm.length);
        const finalWav = new Uint8Array(wavHeader.length + totalPcm.length);
        finalWav.set(wavHeader, 0);
        finalWav.set(totalPcm, wavHeader.length);

        return finalWav.buffer;
    }

    function playCompleteAudio(audioBuffer) {
        if (!window.audioContext || !audioBuffer) {
            console.error('❌ Missing audio context or buffer');
            return;
        }

        try {
            console.log(`🔊 PLAYING AUDIO: ${audioBuffer.duration.toFixed(3)}s`);
            const source = window.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            
            const gainNode = window.audioContext.createGain();
            source.connect(gainNode);
            gainNode.connect(window.audioContext.destination);
            gainNode.gain.setValueAtTime(0.8, window.audioContext.currentTime);
            
            source.start(0);
            isPlayingAudio = true;

            source.onended = () => {
                console.log(`✅ Audio playback completed successfully`);
                isPlayingAudio = false;
                setAgentStatus('Ready for conversation', 'green');
            };

            source.onerror = (error) => {
                console.error('❌ Audio source error:', error);
                isPlayingAudio = false;
                setAgentStatus('❌ Playback Error', 'red');
            };

        } catch (error) {
            console.error('❌ playCompleteAudio error:', error);
            setAgentStatus('❌ Playback Error', 'red');
        }
    }

    // Audio chunk handler
    async function handleAudioChunk(data) {
        console.log(`🎵 RECEIVED AUDIO CHUNK for turn ${data.turn_number}`);
        
        try {
            await initAudioContext();
        } catch (error) {
            console.error('❌ Audio context error:', error);
            setAgentStatus('❌ Audio Context Error', 'red');
            return;
        }

        if (!window.currentTurnAudio || window.currentTurnAudio.turn !== data.turn_number) {
            window.currentTurnAudio = {
                turn: data.turn_number,
                base64Chunks: [],
                validChunks: 0
            };
            console.log(`🎯 NEW TURN: Starting audio accumulation for turn ${data.turn_number}`);
            setAgentStatus('🎵 Receiving Audio...', 'blue');
        }

        if (data.audio_data && data.audio_data.length > 0) {
            window.currentTurnAudio.base64Chunks.push(data.audio_data);
            window.currentTurnAudio.validChunks++;
        }

        if (data.final || (data.audio_data !== undefined && data.audio_data.length === 0)) {
            console.log("🎵 PROCESSING COMPLETE AUDIO");
            
            if (window.currentTurnAudio.base64Chunks.length === 0) {
                console.error(`❌ No audio chunks to process for turn ${data.turn_number}`);
                setAgentStatus('❌ No Audio Data', 'red');
                return;
            }

            setAgentStatus('🔄 Processing Audio...', 'orange');
            
            try {
                const combinedWav = playCombinedWavChunks(window.currentTurnAudio.base64Chunks);
                const audioBuffer = await window.audioContext.decodeAudioData(combinedWav);

                if (!audioBuffer || audioBuffer.length === 0) {
                    throw new Error('Empty decoded buffer');
                }

                console.log(`✅ DECODE SUCCESS: ${audioBuffer.duration.toFixed(3)}s`);
                
                window.audioChunks.push({
                    turn: data.turn_number,
                    chunks: window.currentTurnAudio.validChunks,
                    duration: audioBuffer.duration,
                    success: true,
                    timestamp: new Date().toISOString()
                });

                setAgentStatus('🔊 Playing Audio...', 'green');
                playCompleteAudio(audioBuffer);
                configManager.showSystemMessage(`🎵 Playing: ${audioBuffer.duration.toFixed(1)}s (${window.currentTurnAudio.validChunks} chunks)`);

            } catch (error) {
                console.error(`❌ AUDIO PROCESSING FAILED: ${error.message}`);
                setAgentStatus('❌ Audio Decode Failed', 'red');
                configManager.showSystemMessage(`❌ Audio failed: ${error.message}`, 'error');
                
                window.audioChunks.push({
                    turn: data.turn_number,
                    chunks: window.currentTurnAudio.validChunks,
                    success: false,
                    error: error.message,
                    timestamp: new Date().toISOString()
                });
            }

            setTimeout(() => {
                window.currentTurnAudio = null;
                if (!isPlayingAudio) {
                    setAgentStatus('Ready for conversation', 'green');
                }
            }, 1000);
        }
    }

    function handleAudioStreamingComplete(data) {
        console.log(`🎵 Audio streaming complete for turn ${data.turn_number}`);
        if (window.currentTurnAudio && window.currentTurnAudio.base64Chunks.length > 0) {
            handleAudioChunk({
                turn_number: data.turn_number,
                audio_data: "",
                final: true
            });
        }
    }

    // Debug functions
    window.inspectAudio = function() {
        console.log("🔍 AUDIO INSPECTION:");
        console.log(`📊 Total attempts: ${window.audioChunks.length}`);
        console.log(`🎵 AudioContext: ${window.audioContext ? window.audioContext.state : 'null'}`);
        console.log(`▶️ Playing: ${isPlayingAudio}`);
        console.log(`🎯 Current turn:`, window.currentTurnAudio);
        
        window.audioChunks.forEach((attempt, i) => {
            const status = attempt.success ? '✅' : '❌';
            console.log(`${status} Turn ${attempt.turn}: ${attempt.chunks} chunks, ${attempt.duration ? attempt.duration.toFixed(3) : 'N/A'}s`);
            if (attempt.error) console.log(`  Error: ${attempt.error}`);
        });
        
        return {
            audioChunks: window.audioChunks,
            currentTurn: window.currentTurnAudio
        };
    };

    window.testAudio = function() {
        console.log("🧪 Testing audio...");
        initAudioContext().then(() => {
            const oscillator = window.audioContext.createOscillator();
            const gainNode = window.audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(window.audioContext.destination);
            
            oscillator.frequency.value = 440;
            gainNode.gain.setValueAtTime(0.1, window.audioContext.currentTime);
            
            oscillator.start();
            oscillator.stop(window.audioContext.currentTime + 0.5);
            
            configManager.showSystemMessage("🔊 Audio test tone played");
            console.log("🔊 Test tone should play");
        }).catch(error => {
            console.error("❌ Audio test failed:", error);
            configManager.showSystemMessage(`❌ Audio test failed: ${error.message}`, 'error');
        });
    };

    // WebSocket connection management
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("✅ WebSocket connected");
            setConnectionStatus(true);
            setAgentStatus('Connected - Ready to chat', 'green');
            reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.log("📨 Raw message:", event.data);
            }
        };

        ws.onclose = () => {
            console.log("❌ WebSocket disconnected");
            setConnectionStatus(false);
            setAgentStatus('Disconnected', 'gray');
            
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                configManager.showSystemMessage(`🔄 Reconnecting... (${reconnectAttempts}/${maxReconnectAttempts})`, 'info');
                setTimeout(connectWebSocket, 3000);
            } else {
                configManager.showSystemMessage('❌ Connection failed. Please refresh the page.', 'error');
            }
        };

        ws.onerror = (error) => {
            console.error("❌ WebSocket error:", error);
            setConnectionStatus(false);
        };
    }

    // WebSocket message handler
    function handleWebSocketMessage(data) {
        switch (data.type) {
            case 'connection_established':
                setAgentStatus('🎙️ Ready - Start speaking!', 'green');
                configManager.showSystemMessage("✅ A.R.I.A connected and ready!");
                break;
                
            case 'config_error':
                setAgentStatus('❌ Configuration Error', 'red');
                configManager.showSystemMessage(`❌ Missing API keys: ${data.missing_services?.join(', ')}`, 'error');
                // Auto-open config panel
                document.getElementById('config-panel').classList.add('active');
                document.getElementById('config-overlay').classList.add('active');
                break;
                
            case 'partial_transcript':
                displayPartialTranscription(data.text);
                setAgentStatus('🎤 Listening...', 'blue');
                break;
                
            case 'final_transcript':
            case 'turn_completed':
            case 'turn_updated':
                displayFinalTranscription(data.text || data.final_transcript, data.turn_number);
                currentUserTranscript = data.text || data.final_transcript;
                updateOrAddTurnInHistory(data);
                break;
                
            case 'llm_streaming_start':
                setAgentStatus('🤖 AI Thinking...', 'orange');
                break;
                
            case 'llm_chunk':
                setAgentStatus('🤖 AI Responding...', 'purple');
                break;
                
            case 'llm_streaming_complete':
                setAgentStatus('🎵 Generating Audio...', 'blue');
                configManager.showSystemMessage(`🤖 AI: ${data.full_response.substring(0, 100)}${data.full_response.length > 100 ? '...' : ''}`);
                addToConversationHistory(data.turn_number, currentUserTranscript, data.full_response);
                break;
                
            case 'audio_chunk':
                handleAudioChunk(data);
                break;
                
            case 'audio_streaming_complete':
                handleAudioStreamingComplete(data);
                break;
                
            case 'llm_error':
                setAgentStatus('❌ AI Error', 'red');
                configManager.showSystemMessage(`❌ AI Error: ${data.error}`, 'error');
                break;
                
            case 'error':
                setAgentStatus(`❌ ${data.message}`, 'red');
                configManager.showSystemMessage(`❌ System Error: ${data.message}`, 'error');
                break;
                
            case 'session_begin':
                configManager.showSystemMessage("✅ Session started - speak naturally!");
                break;
                
            default:
                console.log(`📨 Unhandled message type: ${data.type}`, data);
        }
    }

    // UI Helper Functions
    function setConnectionStatus(connected) {
        const statusElement = document.getElementById('connection-status');
        if (statusElement) {
            statusElement.className = connected
                ? 'w-3 h-3 bg-green-500 rounded-full shadow-sm'
                : 'w-3 h-3 bg-red-500 rounded-full shadow-sm';
        }
    }

    function setAgentStatus(message, color) {
        const agentStatus = document.getElementById('agent-status');
        if (agentStatus) {
            agentStatus.textContent = message;
            agentStatus.className = `text-center py-3 px-4 rounded-xl glass-effect font-medium border border-gray-600 ${getColorClass(color)}`;
        }
    }

    function getColorClass(color) {
        const colors = {
            'green': 'text-green-300 border-green-500/50',
            'blue': 'text-blue-300 border-blue-500/50',
            'red': 'text-red-300 border-red-500/50',
            'orange': 'text-orange-300 border-orange-500/50',
            'purple': 'text-purple-300 border-purple-500/50',
            'gray': 'text-gray-300 border-gray-500/50'
        };
        return colors[color] || colors['gray'];
    }

    function displayPartialTranscription(text) {
        const container = document.getElementById('current-turn-container');
        if (container) {
            container.innerHTML = `
                <div class="flex items-center space-x-3">
                    <div class="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
                    <span class="text-blue-300 font-medium">You:</span>
                    <span class="text-white">${text}</span>
                </div>
            `;
        }
    }

    function displayFinalTranscription(text, turnNumber) {
        const container = document.getElementById('current-turn-container');
        if (container) {
            container.innerHTML = `
                <div class="flex items-center space-x-3">
                    <div class="w-2 h-2 bg-green-400 rounded-full"></div>
                    <span class="text-green-300 font-medium">Turn #${turnNumber}:</span>
                    <span class="text-white">${text}</span>
                </div>
            `;
        }
    }

    function updateOrAddTurnInHistory(data) {
        // Implementation for updating turn history
        console.log('Updating turn history:', data);
    }

    function addToConversationHistory(turnNumber, userText, aiResponse) {
        const historyContainer = document.getElementById('turn-history-container');
        if (!historyContainer) return;

        // Remove "no conversations" message if it exists
        if (historyContainer.children.length === 1 && historyContainer.children[0].classList.contains('text-center')) {
            historyContainer.innerHTML = '';
        }

        const conversationItem = document.createElement('div');
        conversationItem.className = 'conversation-item bg-gradient-to-br from-gray-800/50 to-gray-900/50 rounded-xl p-5 border border-gray-700 shadow-lg mb-4';
        conversationItem.innerHTML = `
            <div class="flex items-center justify-between mb-3">
                <span class="text-sm font-medium text-blue-400">Turn #${turnNumber}</span>
                <span class="text-xs text-gray-500">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="space-y-3">
                <div class="flex items-start space-x-3">
                    <div class="w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                        <i class="fas fa-user text-xs text-white"></i>
                    </div>
                    <div class="flex-1">
                        <p class="text-blue-300 font-medium text-sm mb-1">You said:</p>
                        <p class="text-white">${userText}</p>
                    </div>
                </div>
                <div class="flex items-start space-x-3">
                    <div class="w-6 h-6 bg-purple-600 rounded-full flex items-center justify-center flex-shrink-0">
                        <i class="fas fa-robot text-xs text-white"></i>
                    </div>
                    <div class="flex-1">
                        <p class="text-purple-300 font-medium text-sm mb-1">A.R.I.A responded:</p>
                        <p class="text-gray-300">${aiResponse}</p>
                    </div>
                </div>
            </div>
        `;

        historyContainer.insertBefore(conversationItem, historyContainer.firstChild);
        
        // Keep only last 5 conversations for performance
        while (historyContainer.children.length > 5) {
            historyContainer.removeChild(historyContainer.lastChild);
        }
    }

    function clearCurrentTurn() {
        const container = document.getElementById('current-turn-container');
        if (container) {
            container.innerHTML = `
                <p class="text-gray-400 italic flex items-center">
                    <i class="fas fa-microphone mr-2 text-blue-400"></i>
                    Listening for your voice...
                </p>
            `;
        }
    }

    // Recording Functions
    function convertFloat32ToInt16(buffer) {
        const int16Buffer = new Int16Array(buffer.length);
        for (let i = 0; i < buffer.length; i++) {
            const sample = Math.max(-1, Math.min(1, buffer[i]));
            int16Buffer[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        }
        return int16Buffer;
    }

    async function startRecording() {
        try {
            if (ws.readyState !== WebSocket.OPEN) {
                throw new Error("WebSocket not connected");
            }

            await initAudioContext();

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: 16000,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });

            isRecording = true;
            updateButtonUI(true);
            setAgentStatus('🎙️ Recording...', 'red');
            clearCurrentTurn();

            recordingAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            const source = recordingAudioContext.createMediaStreamSource(stream);
            processor = recordingAudioContext.createScriptProcessor(4096, 1, 1);

            processor.onaudioprocess = (event) => {
                if (isRecording && ws && ws.readyState === WebSocket.OPEN) {
                    const inputData = event.inputBuffer.getChannelData(0);
                    const int16Data = convertFloat32ToInt16(inputData);
                    ws.send(int16Data.buffer);
                }
            };

            source.connect(processor);
            processor.connect(recordingAudioContext.destination);
            window.currentStream = stream;

            console.log("🎙️ Recording started");

        } catch (error) {
            console.error("❌ Recording error:", error);
            configManager.showSystemMessage(`❌ Microphone error: ${error.message}`, 'error');
            isRecording = false;
            updateButtonUI(false);
            setAgentStatus('❌ Mic Error', 'red');
        }
    }

    function stopRecording() {
        if (!isRecording) return;

        isRecording = false;
        updateButtonUI(false);
        setAgentStatus('⏹️ Stopping...', 'orange');

        if (processor) {
            processor.disconnect();
            processor = null;
        }

        if (recordingAudioContext) {
            recordingAudioContext.close();
            recordingAudioContext = null;
        }

        if (window.currentStream) {
            window.currentStream.getTracks().forEach(track => track.stop());
            window.currentStream = null;
        }

        setTimeout(() => {
            if (!isPlayingAudio) {
                setAgentStatus('Ready for conversation', 'green');
            }
        }, 1000);
    }

    function updateButtonUI(recording) {
        const recordButton = document.getElementById('record-button');
        const recordIcon = document.getElementById('record-icon');
        const stopIcon = document.getElementById('stop-icon');
        
        if (recordIcon && stopIcon) {
            recordIcon.style.display = recording ? 'none' : 'block';
            stopIcon.style.display = recording ? 'block' : 'none';
            recordButton.classList.toggle('recording', recording);
        }
    }

    // Configuration Panel Event Listeners
    const configPanel = document.getElementById('config-panel');
    const configOverlay = document.getElementById('config-overlay');
    const openConfigButton = document.getElementById('open-config');
    const closeConfigButton = document.getElementById('close-config');

    // Panel toggle
    openConfigButton.addEventListener('click', () => {
        configPanel.classList.add('active');
        configOverlay.classList.add('active');
    });

    const closeConfig = () => {
        configPanel.classList.remove('active');
        configOverlay.classList.remove('active');
    };

    closeConfigButton.addEventListener('click', closeConfig);
    configOverlay.addEventListener('click', closeConfig);

    // API key inputs and test buttons
    ['assemblyai', 'gemini', 'murf', 'tavily'].forEach(service => {
        const input = document.getElementById(`${service}-key`);
        const testButton = document.getElementById(`test-${service}`);

        if (input) {
            input.addEventListener('change', async () => {
                if (input.value.trim()) {
                    await configManager.saveApiKey(service, input.value.trim());
                }
            });

            input.addEventListener('keypress', async (e) => {
                if (e.key === 'Enter' && input.value.trim()) {
                    await configManager.saveApiKey(service, input.value.trim());
                }
            });
        }

        if (testButton) {
            testButton.addEventListener('click', () => {
                if (input && input.value.trim()) {
                    configManager.testApiKey(service);
                } else {
                    configManager.showSystemMessage(`❌ Please enter ${service} API key first`, 'error');
                }
            });
        }
    });

    // Configuration actions
    document.getElementById('save-config')?.addEventListener('click', () => {
        configManager.saveToLocalStorage();
        configManager.showSystemMessage('✅ Configuration saved locally');
    });

    document.getElementById('test-all-apis')?.addEventListener('click', async () => {
        configManager.showSystemMessage('🔄 Testing all APIs...');
        await configManager.checkAllAPIs();
    });

    document.getElementById('export-config')?.addEventListener('click', () => {
        configManager.exportConfig();
    });

    document.getElementById('import-config-btn')?.addEventListener('click', () => {
        document.getElementById('import-config').click();
    });

    document.getElementById('import-config')?.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                try {
                    const config = JSON.parse(e.target.result);
                    configManager.showSystemMessage('✅ Configuration file loaded (keys not imported for security)');
                } catch (error) {
                    configManager.showSystemMessage('❌ Invalid configuration file', 'error');
                }
            };
            reader.readAsText(file);
        }
    });

    document.getElementById('use-env-keys')?.addEventListener('change', async (e) => {
        await configManager.toggleEnvKeys(e.target.checked);
    });

    // Recording button
    const recordButton = document.getElementById('record-button');
    recordButton?.addEventListener('click', async () => {
        if (isRecording) {
            stopRecording();
        } else {
            await startRecording();
        }
    });

    // Initialize WebSocket connection
    connectWebSocket();

    // Initialize UI
    setAgentStatus('Initializing A.R.I.A...', 'orange');
    configManager.showSystemMessage('🎙️ A.R.I.A Day 27 initialized. Configure API keys to begin.');

    console.log("✅ A.R.I.A Day 27 initialization complete!");
});
