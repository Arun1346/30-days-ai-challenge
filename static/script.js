document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM fully loaded. Aether Voice UI Revamp script is running.");

    // --- State Management ---
    let isRecording = false;
    let mediaRecorder, audioChunks = [];
    
    // --- Session ID Management ---
    let sessionId = new URLSearchParams(window.location.search).get('session_id');
    if (!sessionId) {
        sessionId = Date.now().toString();
        window.history.replaceState(null, '', `?session_id=${sessionId}`);
    }
    console.log("Current Session ID:", sessionId);

    // --- Get all DOM elements ---
    const voiceSelect = document.getElementById('voice-select');
    const recordButton = document.getElementById('record-button');
    const recordIcon = document.getElementById('record-icon');
    const stopIcon = document.getElementById('stop-icon');
    const agentStatus = document.getElementById('agent-status');
    const userTranscriptionContainer = document.getElementById('user-transcription-container');
    const aiResponseContainer = document.getElementById('ai-response-container');
    const audioContainer = document.getElementById('audio-container');
    const canvas = document.getElementById('visualizer');
    const visualizerContainer = document.querySelector('.voice_visualizer');
    
    const canvasCtx = canvas.getContext('2d');
    let audioCtx, analyser, animationFrameId;

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
            voiceSelect.innerHTML = '<option>Failed to load</option>';
        }
    }
    await loadVoices();
    setAgentStatus('Ready', 'gray');

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
            setAgentStatus('Listening...', 'red');
            startVisualizer(stream);
            
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.addEventListener('dataavailable', event => audioChunks.push(event.data));
            mediaRecorder.addEventListener('stop', () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                stream.getTracks().forEach(track => track.stop());
                startConversationTurn(audioBlob);
            });
            mediaRecorder.start();
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
            stopVisualizer();
            setAgentStatus('Processing...', 'blue');
        }
    }
    
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

    // --- Conversational Turn Logic ---
    async function startConversationTurn(audioBlob) {
        const selected_voice_id = voiceSelect.value;
        if (!selected_voice_id) return alert('Please select a voice for the agent.');

        const formData = new FormData();
        formData.append("audio_file", audioBlob, "recording.wav");
        
        try {
            setAgentStatus('Thinking...', 'blue');
            userTranscriptionContainer.textContent = "";
            userTranscriptionContainer.classList.add('hidden');
            aiResponseContainer.textContent = "";
            aiResponseContainer.classList.add('hidden');
            
            const response = await fetch(`/agent/chat/${sessionId}?voice_id=${selected_voice_id}`, { method: 'POST', body: formData });
            const result = await response.json();

            if (result.user_transcription) {
                userTranscriptionContainer.textContent = `You: "${result.user_transcription}"`;
                userTranscriptionContainer.classList.remove('hidden');
            }

            const audioPlayer = document.createElement('audio');
            
            if (!response.ok) {
                console.error("Server returned an error:", result.error);
                aiResponseContainer.textContent = `Error: ${result.error || 'Unknown server error'}`;
                aiResponseContainer.classList.remove('hidden');
                setAgentStatus('Error', 'gray');
            }
            
            if (result.ai_response_text) {
                aiResponseContainer.textContent = `Aether: "${result.ai_response_text}"`;
                aiResponseContainer.classList.remove('hidden');
            }

            if (result.ai_response_audio_url) {
                audioPlayer.src = result.ai_response_audio_url;
                audioContainer.innerHTML = '';
                // audioContainer.appendChild(audioPlayer); // Don't show controls
                audioPlayer.play();
                setAgentStatus('Speaking...', 'green');

                audioPlayer.addEventListener('ended', () => {
                    setAgentStatus('Ready', 'gray');
                });
            } else if (!response.ok) {
                 // Error already handled
            } else {
                setAgentStatus('Ready', 'gray');
            }

        } catch (error) {
            console.error("A network error occurred:", error);
            aiResponseContainer.textContent = `Network error: ${error.message}`;
            aiResponseContainer.classList.remove('hidden');
            setAgentStatus('Error', 'gray');
        }
    }

    // --- Visualizer Functions ---
    function startVisualizer(stream) {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        analyser.fftSize = 256;
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        visualizerContainer.style.display = 'block';
        draw(dataArray, bufferLength);
    }

    function stopVisualizer() {
        if (animationFrameId) cancelAnimationFrame(animationFrameId);
        if (canvasCtx) canvasCtx.clearRect(0, 0, canvas.width, canvas.height);
        visualizerContainer.style.display = 'none';
    }

    function draw(dataArray, bufferLength) {
        animationFrameId = requestAnimationFrame(() => draw(dataArray, bufferLength));
        analyser.getByteFrequencyData(dataArray);
        canvasCtx.clearRect(0, 0, canvas.width, canvas.height);
        const barWidth = (canvas.width / bufferLength) * 1.5;
        let barHeight;
        let x = 0;
        for (let i = 0; i < bufferLength; i++) {
            barHeight = dataArray[i] / 2;
            const gradient = canvasCtx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
            gradient.addColorStop(0, '#a855f7');
            gradient.addColorStop(1, '#6366f1');
            canvasCtx.fillStyle = gradient;
            canvasCtx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
            x += barWidth + 2;
        }
    }
});
