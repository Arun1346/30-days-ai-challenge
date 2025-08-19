document.addEventListener('DOMContentLoaded', async () => {
    console.log("🎙️ Day 18 - Enhanced Turn Detection script loaded");

    // --- WebSocket Connection ---
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("✅ WebSocket connection established for Turn Detection");
            setAgentStatus('Turn Detection Ready', 'green');
            reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("📨 Received:", data);

                if (data.type === 'connection_established') {
                    console.log("🚀 Enhanced Turn Detection connected");
                    setAgentStatus('Turn Detection Active', 'green');
                    displaySystemMessage(data.message);
                } else if (data.type === 'partial_transcript') {
                    displayPartialTranscription(data.text);
                    setAgentStatus('🎤 User Speaking...', 'blue');
                } else if (data.type === 'final_transcript' || data.type === 'turn_completed' || data.type === 'turn_updated') {
                    // UPDATED: Handle both new turns and punctuation updates
                    displayFinalTranscription(data.text || data.final_transcript, data.turn_number);
                    updateOrAddTurnInHistory(data);
                    
                    if (data.type === 'turn_completed') {
                        handleTurnCompleted(data);
                    }
                } else if (data.type === 'error') {
                    console.error("❌ Server error:", data.message);
                    setAgentStatus(`Error: ${data.message}`, 'red');
                } else if (data.type === 'session_begin') {
                    console.log("🎯 Turn Detection session began:", data.session_id);
                    displaySystemMessage("Turn detection active - speak naturally and pause to complete turns");
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
            voiceSelect.innerHTML = '';
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
            setAgentStatus('🎙️ Recording & Detecting Turns...', 'red');
            clearCurrentTurn();
            turnCount = 0;

            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
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
                setAgentStatus('Turn Detection Ready', 'green');
            }, 3000);
        }
    }

    // --- DAY 18: ENHANCED UI FUNCTIONS FOR TURN DETECTION ---
    
    // NEW FUNCTION: Update or add turn in history with punctuated text
    function updateOrAddTurnInHistory(data) {
        if (!turnHistoryContainer) return;
        
        // Look for existing turn element
        let existingTurnElement = turnHistoryContainer.querySelector(`[data-turn-number="${data.turn_number}"]`);
        
        if (existingTurnElement) {
            // UPDATE existing turn with punctuated text
            const transcriptElement = existingTurnElement.querySelector('.transcript-text');
            if (transcriptElement) {
                transcriptElement.textContent = `"${data.text || data.final_transcript}"`;
            }
            console.log(`✏️ Updated turn ${data.turn_number} with punctuation`);
        } else {
            // ADD new turn element
            const turnElement = document.createElement('div');
            turnElement.className = 'turn-history-item bg-green-900/30 border border-green-600 rounded-lg p-4 mb-3';
            turnElement.setAttribute('data-turn-number', data.turn_number);
            turnElement.innerHTML = `
                <div class="text-sm text-green-400 font-semibold">Turn ${data.turn_number}</div>
                <div class="text-white transcript-text">"${data.text || data.final_transcript}"</div>
                ${data.audio_duration ? `<div class="text-xs text-green-300 mt-1">Duration: ${data.audio_duration}s</div>` : ''}
            `;
            
            turnHistoryContainer.appendChild(turnElement);
            turnHistoryContainer.scrollTop = turnHistoryContainer.scrollHeight;
            console.log(`➕ Added new turn ${data.turn_number}`);
        }
    }

    function handleTurnCompleted(data) {
        console.log("🎯 TURN COMPLETED:", data);
        
        // Update status to show turn completion
        setAgentStatus(`🔇 Turn ${data.turn_number} Completed - User Stopped Speaking`, 'green');
        
        // Clear current turn display
        setTimeout(() => {
            clearCurrentTurn();
            setAgentStatus('🎤 Ready for next turn...', 'gray');
        }, 2000);
        
        // Show turn completion notification
        showTurnCompletionNotification(data);
    }

    // UPDATED: Modified to use new logic
    function addTurnToHistory(turnData) {
        updateOrAddTurnInHistory(turnData);
    }

    function showTurnCompletionNotification(data) {
        const notification = document.createElement('div');
        notification.className = 'turn-notification fixed top-4 right-4 bg-green-600 text-white px-4 py-2 rounded-lg shadow-lg z-50';
        notification.innerHTML = `
            <div class="font-semibold">Turn ${data.turn_number} Completed!</div>
            <div class="text-sm">"${data.final_transcript}"</div>
        `;
        
        document.body.appendChild(notification);
        
        // Remove notification after 3 seconds
        setTimeout(() => {
            if (notification && notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 3000);
    }

    // --- Helper Functions ---
    function updateButtonUI(recording) {
        if (recording) {
            recordButton.classList.add('recording');
            recordIcon.style.display = 'none';
            stopIcon.style.display = 'inline-block';
        } else {
            recordButton.classList.remove('recording');
            recordIcon.style.display = 'inline-block';
            stopIcon.style.display = 'none';
        }
    }

    function setAgentStatus(status, color) {
        if (agentStatus) {
            agentStatus.textContent = status;
            agentStatus.className = `text-${color}-400`;
        }
    }

    function displayPartialTranscription(text) {
        if (currentTurnContainer) {
            currentTurnContainer.innerHTML = `
                <div class="text-blue-400 text-sm">Speaking...</div>
                <div class="text-white">"${text}"</div>
            `;
        }
    }

    function displayFinalTranscription(text, turnNumber) {
        if (currentTurnContainer) {
            currentTurnContainer.innerHTML = `
                <div class="text-green-400 text-sm">Turn ${turnNumber} Completed</div>
                <div class="text-white">"${text}"</div>
            `;
        }
    }

    function clearCurrentTurn() {
        if (currentTurnContainer) {
            currentTurnContainer.innerHTML = `
                <div class="text-gray-400">Start speaking to see real-time turn detection</div>
            `;
        }
    }

    function displaySystemMessage(message) {
        if (systemMessagesContainer) {
            const messageElement = document.createElement('div');
            messageElement.className = 'text-blue-300 text-sm mb-2';
            messageElement.textContent = message;
            systemMessagesContainer.appendChild(messageElement);
            systemMessagesContainer.scrollTop = systemMessagesContainer.scrollHeight;
        }
    }
});
