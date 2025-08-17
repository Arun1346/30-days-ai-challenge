document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM fully loaded. Aether Voice Streaming script is running.");

    // --- WebSocket Connection ---
    let ws;
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

        ws.onopen = () => {
            console.log("WebSocket connection established.");
            setAgentStatus('Ready to Stream', 'gray');
        };

        ws.onmessage = (event) => {
            // We can listen for server messages here if needed in the future
            console.log("Server message:", event.data);
        };

        ws.onclose = () => {
            console.log("WebSocket connection closed. Attempting to reconnect...");
            setAgentStatus('Disconnected', 'gray');
            // Optional: attempt to reconnect after a delay
            setTimeout(connectWebSocket, 3000); 
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            ws.close();
        };
    }
    connectWebSocket(); // Initial connection

    // --- State Management ---
    let isRecording = false;
    let mediaRecorder;
    
    // --- Get all DOM elements ---
    const voiceSelect = document.getElementById('voice-select');
    const recordButton = document.getElementById('record-button');
    const recordIcon = document.getElementById('record-icon');
    const stopIcon = document.getElementById('stop-icon');
    const agentStatus = document.getElementById('agent-status');
    // ... other elements are not used in this task but we leave them for now

    // --- Load Voices (no changes) ---
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
            voiceSelect.innerHTML = '<option>Failed to load</option>';
        }
    }
    await loadVoices();
    
    // --- Main Record Button Logic ---
    recordButton.addEventListener('click', async () => {
        if (isRecording) {
            stopRecording();
        } else {
            await startRecording();
        }
    });

    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            isRecording = true;
            updateButtonUI(true);
            setAgentStatus('Streaming...', 'red');
            
            mediaRecorder = new MediaRecorder(stream);
            
            // --- MODIFIED: Send audio chunks as they become available ---
            mediaRecorder.addEventListener('dataavailable', event => {
                if (event.data.size > 0 && ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(event.data);
                }
            });

            mediaRecorder.addEventListener('stop', () => {
                // Stop the tracks of the old stream to turn off the mic light
                stream.getTracks().forEach(track => track.stop());
                console.log("Recording stopped, stream closed.");
            });

            // Start recording and slice the data into chunks every 250ms
            mediaRecorder.start(250); 

        } catch (error) {
            console.error("Could not access microphone:", error);
            alert("Could not access microphone. Please allow microphone access in your browser settings.");
            isRecording = false;
            updateButtonUI(false);
            setAgentStatus('Mic Error', 'gray');
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            isRecording = false;
            updateButtonUI(false);
            setAgentStatus('Stream ended', 'blue');
        }
    }
    
    // --- Helper functions (no changes) ---
    function updateButtonUI(recording) {
        if (recording) {
            recordButton.classList.add('is-recording');
            recordIcon.classList.add('hidden');
            stopIcon.classList.remove('hidden');
        } else {
            recordButton.classList.remove('is-recording');
            recordIcon.classList.remove('hidden');
            stopIcon.classList.add('hidden');
        }
    }

    function setAgentStatus(text, color) {
        const colorClasses = {
            gray: 'status-dot-gray',
            red: 'status-dot-red',
            blue: 'status-dot-blue',
            green: 'status-dot-green'
        };
        agentStatus.innerHTML = `<div class="status-dot ${colorClasses[color]}"></div><span>${text}</span>`;
    }
});
