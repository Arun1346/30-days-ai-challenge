document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM loaded. Aether Voice Universal Streaming script running.");

    // --- WebSocket Connection ---
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;

    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("✅ WebSocket connection established.");
            setAgentStatus('Ready to Stream', 'green');
            reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("📨 Received:", data);
                
                if (data.type === 'connection_established') {
                    console.log("✅ AssemblyAI Universal Streaming connected");
                    setAgentStatus('Universal Streaming Ready', 'green');
                } else if (data.type === 'partial_transcript') {
                    displayPartialTranscription(data.text);
                } else if (data.type === 'final_transcript') {
                    displayFinalTranscription(data.text);
                } else if (data.type === 'error') {
                    console.error("❌ Server error:", data.message);
                    setAgentStatus(`Error: ${data.message}`, 'red');
                } else if (data.type === 'session_begin') {
                    console.log("🚀 Session began:", data.session_id);
                } else if (data.type === 'session_terminated') {
                    console.log("🔒 Session terminated");
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

    // --- Get DOM elements ---
    const voiceSelect = document.getElementById('voice-select');
    const recordButton = document.getElementById('record-button');
    const recordIcon = document.getElementById('record-icon');
    const stopIcon = document.getElementById('stop-icon');
    const agentStatus = document.getElementById('agent-status');
    const userTranscriptionContainer = document.getElementById('user-transcription-container');

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
            voiceSelect.innerHTML = '<option value="">Error loading voices</option>';
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
            setAgentStatus('🎙️ Recording & Streaming...', 'red');
            clearTranscriptions();

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
            setAgentStatus('Processing...', 'blue');

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
                setAgentStatus('Ready to Stream', 'green');
            }, 2000);
        }
    }

    // --- UI Helper Functions ---
    function updateButtonUI(recording) {
        if (recording) {
            recordIcon.classList.add('hidden');
            stopIcon.classList.remove('hidden');
            recordButton.classList.remove('bg-blue-600', 'hover:bg-blue-700');
            recordButton.classList.add('bg-red-600', 'hover:bg-red-700');
        } else {
            recordIcon.classList.remove('hidden');
            stopIcon.classList.add('hidden');
            recordButton.classList.remove('bg-red-600', 'hover:bg-red-700');
            recordButton.classList.add('bg-blue-600', 'hover:bg-blue-700');
        }
    }

    function setAgentStatus(status, color) {
        agentStatus.textContent = status;
        agentStatus.className = `text-sm font-medium text-${color}-400`;
    }

    function clearTranscriptions() {
        userTranscriptionContainer.innerHTML = '';
        userTranscriptionContainer.classList.add('hidden');
    }

    function displayPartialTranscription(text) {
        if (!text.trim()) return;
        
        userTranscriptionContainer.innerHTML = `
            <div class="p-4 bg-gray-800 rounded-lg border border-gray-600">
                <p class="text-sm text-gray-400 mb-1">You're saying (partial):</p>
                <p class="text-white italic">${text}</p>
            </div>
        `;
        userTranscriptionContainer.classList.remove('hidden');
    }

    function displayFinalTranscription(text) {
        if (!text.trim()) return;
        
        userTranscriptionContainer.innerHTML = `
            <div class="p-4 bg-blue-900 rounded-lg border border-blue-600">
                <p class="text-sm text-blue-300 mb-1">✅ You said:</p>
                <p class="text-white font-medium">${text}</p>
            </div>
        `;
        userTranscriptionContainer.classList.remove('hidden');
    }
});
