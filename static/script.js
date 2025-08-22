document.addEventListener('DOMContentLoaded', async () => {
    console.log("🎙️ Day 21 - Streaming Audio Data to Client script loaded");

    // --- NEW: Audio streaming variables ---
    let audioChunks = [];
    let currentTurnAudio = null;

    // --- WebSocket Connection ---
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("✅ WebSocket connection established for Streaming LLM");
            setAgentStatus('Turn Detection + LLM Ready', 'green');
            reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("📨 Received:", data);

                if (data.type === 'connection_established') {
                    console.log("🚀 Enhanced Turn Detection with LLM Streaming connected");
                    setAgentStatus('Turn Detection + LLM Active', 'green');
                    displaySystemMessage(data.message);
                } else if (data.type === 'partial_transcript') {
                    displayPartialTranscription(data.text);
                    setAgentStatus('🎤 User Speaking...', 'blue');
                } else if (data.type === 'final_transcript' || data.type === 'turn_completed' || data.type === 'turn_updated') {
                    displayFinalTranscription(data.text || data.final_transcript, data.turn_number);
                    updateOrAddTurnInHistory(data);
                    if (data.type === 'turn_completed') {
                        handleTurnCompleted(data);
                    }
                } else if (data.type === 'llm_streaming_start') {
                    console.log(`🤖 LLM streaming started for turn ${data.turn_number}`);
                    setAgentStatus('🤖 AI Thinking...', 'orange');
                } else if (data.type === 'llm_chunk') {
                    console.log(`🤖 LLM Chunk: "${data.chunk}"`);
                    console.log(`📝 Accumulated: "${data.accumulated}"`);
                    setAgentStatus('🤖 AI Responding...', 'purple');
                } else if (data.type === 'llm_streaming_complete') {
                    console.log("="+"=".repeat(60));
                    console.log(`🤖 LLM RESPONSE COMPLETE for turn ${data.turn_number}`);
                    console.log(`📝 Full Response: "${data.full_response}"`);
                    console.log(`📊 Response Length: ${data.full_response.length} characters`);
                    console.log("="+"=".repeat(60));
                    setAgentStatus('🎵 Generating Audio...', 'blue'); // Changed this line
                    displaySystemMessage(`AI Response: ${data.full_response}`);
                } 
                // NEW: Add these audio handlers
                else if (data.type === 'audio_chunk') {
                    handleAudioChunk(data);
                } else if (data.type === 'audio_streaming_complete') {
                    handleAudioStreamingComplete(data);
                }
                else if (data.type === 'llm_error') {
                    console.error(`❌ LLM Error for turn ${data.turn_number}:`, data.error);
                    setAgentStatus('❌ LLM Error', 'red');
                } else if (data.type === 'error') {
                    console.error("❌ Server error:", data.message);
                    setAgentStatus(`Error: ${data.message}`, 'red');
                } else if (data.type === 'session_begin') {
                    console.log("🎯 Turn Detection with LLM session began:", data.session_id);
                    displaySystemMessage("Turn detection with LLM streaming active - speak naturally!");
                } else if (data.type === 'session_terminated') {
                    console.log("🔒 Turn Detection session terminated");
                    displaySystemMessage(`Session ended - ${data.total_audio_duration} seconds processed`);
                }
            } catch (e) {
                console.log("Server message:", event.data);
            }
        };

        ws.onclose = () => {
            console.log("WebSocket connection closed.");
            setAgentStatus('Disconnected', 'gray');
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                console.log(`Reconnecting... (${reconnectAttempts}/${maxReconnectAttempts})`);
                setTimeout(connectWebSocket, 3000);
            } else {
                setAgentStatus('Connection failed', 'red');
            }
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            setAgentStatus('Connection Error', 'red');
        };
    }

    // NEW: Add these audio handling functions
    function handleAudioChunk(data) {
        console.log(`🎵 Received audio chunk for turn ${data.turn_number || 'N/A'}`);
        console.log(`📊 Chunk size: ${data.audio_data.length} base64 characters`);
        console.log(`🏁 Final chunk: ${data.final}`);
        
        // Initialize array for new turn if needed
        if (!currentTurnAudio || currentTurnAudio.turn !== data.turn_number) {
            currentTurnAudio = {
                turn: data.turn_number,
                chunks: []
            };
            console.log(`🎯 Starting audio accumulation for turn ${data.turn_number}`);
            setAgentStatus('🎵 Receiving Audio...', 'blue');
        }
        
        // Accumulate the base64 chunk
        currentTurnAudio.chunks.push(data.audio_data);
        
        // Log acknowledgment
        console.log(`✅ Audio chunk ${currentTurnAudio.chunks.length} acknowledged and accumulated`);
        console.log(`📈 Total chunks accumulated: ${currentTurnAudio.chunks.length}`);
        
        if (data.final) {
            console.log("="+"=".repeat(60));
            console.log(`🎵 AUDIO STREAMING COMPLETE for turn ${data.turn_number}`);
            console.log(`📊 Total audio chunks: ${currentTurnAudio.chunks.length}`);
            console.log(`📏 Total base64 length: ${currentTurnAudio.chunks.join('').length} characters`);
            console.log("="+"=".repeat(60));
            
            // Store completed audio for this turn
            audioChunks.push({
                turn: data.turn_number,
                chunks: currentTurnAudio.chunks,
                totalLength: currentTurnAudio.chunks.join('').length,
                timestamp: data.timestamp
            });
            
            setAgentStatus('✅ Audio Complete', 'green');
            displaySystemMessage(`🎵 Audio streaming complete for turn ${data.turn_number} (${currentTurnAudio.chunks.length} chunks)`);
            
            // Reset for next turn
            currentTurnAudio = null;
            
            // Reset status after a delay
            setTimeout(() => {
                setAgentStatus('Turn Detection + LLM Ready', 'green');
            }, 2000);
        }
    }

    function handleAudioStreamingComplete(data) {
        console.log(`🎵 Audio streaming session complete for turn ${data.turn_number}`);
        console.log(`📊 Total turns with audio: ${audioChunks.length}`);
    }

    // Optional: Add function to inspect accumulated audio data
    function inspectAudioData() {
        console.log("🔍 AUDIO DATA INSPECTION:");
        console.log(`📊 Total turns with audio: ${audioChunks.length}`);
        
        audioChunks.forEach((turn, index) => {
            console.log(`Turn ${turn.turn}: ${turn.chunks.length} chunks, ${turn.totalLength} base64 chars`);
        });
        
        return audioChunks;
    }

    // Make inspection function available globally
    window.inspectAudioData = inspectAudioData;

    connectWebSocket();

    // --- State Management ---
    let isRecording = false;
    let audioContext;
    let processor;
    let turnCount = 0;

    // --- Get DOM elements ---
    const voiceSelect = document.getElementById('voice-select');
    const recordButton = document.getElementById('record-button');
    const recordIcon = document.getElementById('record-icon');
    const stopIcon = document.getElementById('stop-icon');
    const agentStatus = document.getElementById('agent-status');
    const userTranscriptionContainer = document.getElementById('user-transcription-container');
    const turnHistoryContainer = document.getElementById('turn-history-container');
    const currentTurnContainer = document.getElementById('current-turn-container');
    const systemMessagesContainer = document.getElementById('system-messages');

    // --- Load Voices ---
    async function loadVoices() {
        try {
            const response = await fetch('/voices');
            if (!response.ok) throw new Error(`Failed to load voices: ${response.statusText}`);
            
            const data = await response.json();
            if (data.error || !data.voices) throw new Error(data.error || 'Voice data is invalid.');
            
            voiceSelect.innerHTML = '';
            data.voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.voice_id;
                option.textContent = `${voice.name} (${voice.labels.gender || 'N/A'})`;
                voiceSelect.appendChild(option);
            });
        } catch (error) {
            console.error("Failed to load voices:", error);
            voiceSelect.innerHTML = '<option>Failed to load voices</option>';
        }
    }

    await loadVoices();

    // --- Record Button Logic ---
    recordButton.addEventListener('click', async () => {
        if (isRecording) {
            stopRecording();
        } else {
            await startRecording();
        }
    });

    // --- Audio Functions ---
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
                throw new Error("WebSocket connection is not open");
            }

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
            setAgentStatus('🎙️ Recording & AI Ready...', 'red');
            clearCurrentTurn();
            turnCount = 0;

            audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            const source = audioContext.createMediaStreamSource(stream);
            processor = audioContext.createScriptProcessor(4096, 1, 1);

            processor.onaudioprocess = (event) => {
                if (isRecording && ws && ws.readyState === WebSocket.OPEN) {
                    const inputData = event.inputBuffer.getChannelData(0);
                    const int16Data = convertFloat32ToInt16(inputData);
                    ws.send(int16Data.buffer);
                }
            };

            source.connect(processor);
            processor.connect(audioContext.destination);

            window.currentStream = stream;

        } catch (error) {
            console.error("Could not access microphone:", error);
            alert("Could not access microphone. Please allow microphone access.");
            isRecording = false;
            updateButtonUI(false);
            setAgentStatus('Mic Error', 'red');
        }
    }

    function stopRecording() {
        if (isRecording) {
            isRecording = false;
            updateButtonUI(false);
            setAgentStatus('Processing final turn...', 'blue');

            if (processor) {
                processor.disconnect();
                processor = null;
            }

            if (audioContext) {
                audioContext.close();
                audioContext = null;
            }

            if (window.currentStream) {
                window.currentStream.getTracks().forEach(track => track.stop());
                window.currentStream = null;
            }

            setTimeout(() => {
                setAgentStatus('Turn Detection + LLM Ready', 'green');
            }, 3000);
        }
    }

    // --- UI FUNCTIONS ---
    function updateOrAddTurnInHistory(data) {
        if (!turnHistoryContainer) return;

        let existingTurnElement = turnHistoryContainer.querySelector(`[data-turn-number="${data.turn_number}"]`);
        
        if (existingTurnElement) {
            const transcriptElement = existingTurnElement.querySelector('.transcript-text');
            if (transcriptElement) {
                transcriptElement.textContent = `"${data.text || data.final_transcript}"`;
            }
            console.log(`✏️ Updated turn ${data.turn_number} with punctuation`);
        } else {
            const turnElement = document.createElement('div');
            turnElement.className = 'turn-history-item bg-green-900/30 border border-green-600 rounded-lg p-4 mb-3';
            turnElement.setAttribute('data-turn-number', data.turn_number);
            
            turnElement.innerHTML = `
                <div class="flex items-start justify-between mb-2">
                    <div class="text-sm text-green-400 font-semibold">Turn #${data.turn_number}</div>
                    <div class="text-xs text-gray-500">${new Date(data.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="transcript-text text-white">"${data.text || data.final_transcript}"</div>
                ${data.audio_duration ? `<div class="text-xs text-gray-400 mt-2">Duration: ${data.audio_duration.toFixed(2)}s</div>` : ''}
            `;
            
            turnHistoryContainer.insertBefore(turnElement, turnHistoryContainer.firstChild);
            console.log(`➕ Added new turn ${data.turn_number} to history`);
        }
    }

    function displayPartialTranscription(transcript) {
        if (!currentTurnContainer) return;
        
        currentTurnContainer.innerHTML = `
            <div class="bg-blue-900/30 border border-blue-600 rounded-lg p-4">
                <div class="text-sm text-blue-400 font-semibold mb-2">Current Turn (In Progress)</div>
                <div class="text-white italic">"${transcript}"</div>
                <div class="text-xs text-gray-400 mt-2">Speaking...</div>
            </div>
        `;
    }

    function displayFinalTranscription(transcript, turnNumber) {
        if (!currentTurnContainer) return;
        
        currentTurnContainer.innerHTML = `
            <div class="bg-green-900/30 border border-green-600 rounded-lg p-4">
                <div class="text-sm text-green-400 font-semibold mb-2">Turn #${turnNumber} Complete</div>
                <div class="text-white">"${transcript}"</div>
                <div class="text-xs text-gray-400 mt-2">Processing...</div>
            </div>
        `;
    }

    function clearCurrentTurn() {
        if (!currentTurnContainer) return;
        currentTurnContainer.innerHTML = `
            <div class="bg-gray-800/30 border border-gray-600 rounded-lg p-4">
                <div class="text-sm text-gray-400 font-semibold mb-2">Current Turn</div>
                <div class="text-gray-500">Start speaking to see real-time turn detection</div>
            </div>
        `;
    }

    function handleTurnCompleted(data) {
        console.log(`🎯 Turn ${data.turn_number} completed:`, data.final_transcript);
    }

    function displaySystemMessage(message) {
        if (!systemMessagesContainer) return;
        
        const messageElement = document.createElement('div');
        messageElement.className = 'system-message bg-purple-900/30 border border-purple-600 rounded-lg p-3 mb-2';
        messageElement.innerHTML = `
            <div class="text-sm text-purple-400">${message}</div>
            <div class="text-xs text-gray-500 mt-1">${new Date().toLocaleTimeString()}</div>
        `;
        
        systemMessagesContainer.insertBefore(messageElement, systemMessagesContainer.firstChild);
        
        // Keep only last 5 messages
        while (systemMessagesContainer.children.length > 5) {
            systemMessagesContainer.removeChild(systemMessagesContainer.lastChild);
        }
    }

    function setAgentStatus(status, color) {
        if (!agentStatus) return;
        
        const colorClasses = {
            'green': 'text-green-400',
            'red': 'text-red-400',
            'blue': 'text-blue-400',
            'orange': 'text-orange-400',
            'purple': 'text-purple-400',
            'gray': 'text-gray-400'
        };
        
        agentStatus.className = `text-sm font-semibold ${colorClasses[color] || 'text-white'}`;
        agentStatus.textContent = status;
    }

    function updateButtonUI(recording) {
        if (!recordButton || !recordIcon || !stopIcon) return;
        
        if (recording) {
            recordButton.classList.remove('bg-green-600', 'hover:bg-green-700');
            recordButton.classList.add('bg-red-600', 'hover:bg-red-700', 'animate-pulse');
            recordIcon.classList.add('hidden');
            stopIcon.classList.remove('hidden');
        } else {
            recordButton.classList.remove('bg-red-600', 'hover:bg-red-700', 'animate-pulse');
            recordButton.classList.add('bg-green-600', 'hover:bg-green-700');
            recordIcon.classList.remove('hidden');
            stopIcon.classList.add('hidden');
        }
    }

    // Initialize the page
    clearCurrentTurn();
    setAgentStatus('Initializing...', 'gray');
    
    console.log("🎵 Day 21 audio streaming features initialized");
    console.log("📝 Use inspectAudioData() in console to examine accumulated audio chunks");
});
