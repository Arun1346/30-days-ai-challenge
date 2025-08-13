document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM fully loaded. Aether Voice script is running.");

    // --- Session ID Management ---
    let sessionId = new URLSearchParams(window.location.search).get('session_id');
    if (!sessionId) {
        sessionId = Date.now().toString();
        // Use replaceState to avoid reloading the page, which would create a new session
        window.history.replaceState(null, '', `?session_id=${sessionId}`);
    }
    console.log("Current Session ID:", sessionId);

    // --- Get all DOM elements ---
    const ttsVoiceSelect = document.getElementById('tts-voice-select');
    const echoVoiceSelect = document.getElementById('echo-voice-select');
    const textInput = document.getElementById('text-input');
    const generateButton = document.getElementById('generate-button');
    const audioContainer = document.getElementById('audio-container');
    const startButton = document.getElementById('start-recording');
    const stopButton = document.getElementById('stop-recording');
    const echoAudioContainer = document.getElementById('echo-audio-container');
    const transcriptionContainer = document.getElementById('transcription-container');
    const agentStatus = document.getElementById('agent-status');
    const canvas = document.getElementById('visualizer');
    const visualizerContainer = document.querySelector('.voice_visualizer');
    
    const canvasCtx = canvas.getContext('2d');
    let audioCtx, analyser, animationFrameId, mediaRecorder, audioChunks = [];

    // --- Load Voices ---
    async function loadVoices() {
        try {
            const response = await fetch('/voices');
            if (!response.ok) throw new Error(`Failed to load voices: ${response.statusText}`);
            const data = await response.json();
            if (data.error || !data.voices) throw new Error(data.error || 'Voice data is invalid.');
            
            const populateSelect = (selectElement) => {
                selectElement.innerHTML = '';
                data.voices.forEach(voice => {
                    const option = document.createElement('option');
                    option.value = voice.voice_id;
                    option.textContent = `${voice.name} (${voice.labels.gender || 'N/A'})`;
                    selectElement.appendChild(option);
                });
            };
            populateSelect(ttsVoiceSelect);
            populateSelect(echoVoiceSelect);

        } catch (error) {
            console.error("Failed to load voices:", error);
            ttsVoiceSelect.innerHTML = '<option>Failed to load</option>';
            echoVoiceSelect.innerHTML = '<option>Failed to load</option>';
        }
    }
    await loadVoices();

    // --- Text-to-Speech ---
    generateButton.addEventListener('click', async () => {
        const text = textInput.value.trim();
        const voice_id = ttsVoiceSelect.value;
        if (!text || !voice_id) return alert('Please enter text and select a voice.');
        
        const originalButtonText = generateButton.innerHTML;
        generateButton.disabled = true;
        generateButton.innerHTML = 'Generating...';
        audioContainer.innerHTML = '';
        try {
            const response = await fetch('/generate-speech', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, voice_id: voice_id }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Network response was not ok.');
            
            if (data.audio_url) {
                const audioPlayer = document.createElement('audio');
                audioPlayer.src = data.audio_url;
                audioPlayer.controls = true;
                audioPlayer.autoplay = true;
                audioPlayer.classList.add('w-full', 'mt-4');
                audioContainer.appendChild(audioPlayer);
            }
        } catch (error) {
            alert('Failed to generate audio. ' + error.message);
        } finally {
            generateButton.disabled = false;
            generateButton.innerHTML = originalButtonText;
        }
    });

    // --- Conversational Agent ---
    function setAgentStatus(text, isRecording) {
        agentStatus.innerHTML = `<div class="status-dot ${isRecording ? 'status-dot-red' : 'status-dot-gray'}"></div><span>${text}</span>`;
    }

    startButton.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            startVisualizer(stream);
            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.addEventListener('dataavailable', event => audioChunks.push(event.data));
            mediaRecorder.addEventListener('stop', () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                startConversationTurn(audioBlob);
                audioChunks = [];
            });
            mediaRecorder.start();
            startButton.disabled = true;
            stopButton.disabled = false;
            setAgentStatus('Recording...', true);
        } catch (error) {
            alert("Could not access microphone.");
        }
    });

    stopButton.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            stopVisualizer();
            startButton.disabled = false;
            stopButton.disabled = true;
            setAgentStatus('Processing...', false);
        }
    });

    // --- CORRECTED CONVERSATIONAL FUNCTION FOR DAY 11 ---
    async function startConversationTurn(audioBlob) {
        const voice_id = echoVoiceSelect.value;
        if (!voice_id) return alert('Please select a voice for the agent.');

        const formData = new FormData();
        formData.append("audio_file", audioBlob, "recording.wav");
        
        try {
            setAgentStatus('Thinking...', false);
            transcriptionContainer.textContent = "Sending your voice to the AI...";
            
            const response = await fetch(`/agent/chat/${sessionId}?voice_id=${voice_id}`, { method: 'POST', body: formData });
            const result = await response.json();

            // Display transcription regardless of success or failure
            if (result.user_transcription) {
                transcriptionContainer.textContent = `You said: "${result.user_transcription}"`;
            }

            // The audio player will handle either the success audio or the error audio
            const audioPlayer = document.createElement('audio');
            audioPlayer.src = result.ai_response_audio_url;
            audioPlayer.controls = true;
            audioPlayer.autoplay = true;
            audioPlayer.classList.add('w-full', 'mt-4');
            echoAudioContainer.innerHTML = '';
            echoAudioContainer.appendChild(audioPlayer);

            // If the server response was not OK, it's an error.
            if (!response.ok) {
                console.error("Server returned an error:", result.error);
                transcriptionContainer.textContent += ` | Error: ${result.error}`;
                setAgentStatus('Error. Ready.', false);
                // On error, DO NOT auto-record again. Just reset the state.
                audioPlayer.addEventListener('ended', () => {
                    setAgentStatus('Error. Ready.', false);
                });
            } else if (result.ai_response_audio_url) {
                // Handle success case
                setAgentStatus('Speaking...', false);
                // Auto-record only on success
                audioPlayer.addEventListener('ended', () => {
                    console.log("AI finished speaking. Clicking start button for next turn.");
                    startButton.click(); 
                });
            } else {
                // This handles the case where the user was silent.
                console.log("User was silent, resetting to Ready state.");
                setAgentStatus('Ready', false);
            }

        } catch (error) {
            // This catch block now only handles network failures (e.g., server is down)
            console.error("A network error occurred:", error);
            transcriptionContainer.textContent = `A network error occurred: ${error.message}`;
            setAgentStatus('Error. Ready.', false);
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
        visualizerContainer.style.display = 'flex';
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
            barHeight = dataArray[i] / 2.5;
            const gradient = canvasCtx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
            gradient.addColorStop(0, '#a855f7');
            gradient.addColorStop(1, '#6366f1');
            canvasCtx.fillStyle = gradient;
            canvasCtx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
            x += barWidth + 2;
        }
    }
});
