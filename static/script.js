document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM fully loaded. Aether Voice script is running.");

    // --- NEW: Fetch and populate voices on page load ---
    const ttsVoiceSelect = document.getElementById('tts-voice-select');
    const echoVoiceSelect = document.getElementById('echo-voice-select');
    
    async function loadVoices() {
        try {
            const response = await fetch('/voices');
            const data = await response.json();
            if (data.error || !data.voices) {
                throw new Error('Could not load voices.');
            }
            
            // Clear the 'loading' option
            ttsVoiceSelect.innerHTML = '';
            echoVoiceSelect.innerHTML = '';

            // Populate both dropdowns with the fetched voices
            data.voices.forEach(voice => {
                const option1 = document.createElement('option');
                option1.value = voice.voice_id;
                option1.textContent = `${voice.name} (${voice.labels.gender})`;
                ttsVoiceSelect.appendChild(option1);

                const option2 = document.createElement('option');
                option2.value = voice.voice_id;
                option2.textContent = `${voice.name} (${voice.labels.gender})`;
                echoVoiceSelect.appendChild(option2);
            });
        } catch (error) {
            console.error("Failed to load voices:", error);
            ttsVoiceSelect.innerHTML = '<option>Failed to load voices</option>';
            echoVoiceSelect.innerHTML = '<option>Failed to load voices</option>';
        }
    }
    await loadVoices();
    // --------------------------------------------------


    // --- TEXT-TO-SPEECH FUNCTIONALITY ---
    const textInput = document.getElementById('text-input');
    const generateButton = document.getElementById('generate-button');
    const audioContainer = document.getElementById('audio-container');

    generateButton.addEventListener('click', async () => {
        const text = textInput.value.trim();
        const voice_id = ttsVoiceSelect.value; // Get selected voice
        if (!text) return alert('Please enter some text.');
        if (!voice_id) return alert('Please select a voice.');
        
        const originalButtonText = generateButton.innerHTML;
        generateButton.disabled = true;
        generateButton.innerHTML = 'Generating...';
        audioContainer.innerHTML = '';

        try {
            const response = await fetch('/generate-speech', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // Send text AND voice_id to the backend
                body: JSON.stringify({ text: text, voice_id: voice_id }),
            });
            if (!response.ok) throw new Error('Network response was not ok.');
            const data = await response.json();
            if (data.error) throw new Error(data.error);
            if (data.audio_url) {
                const audioPlayer = document.createElement('audio');
                audioPlayer.src = data.audio_url;
                audioPlayer.controls = true;
                audioPlayer.autoplay = true;
                audioPlayer.classList.add('w-full', 'mt-4');
                audioContainer.appendChild(audioPlayer);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to generate audio. ' + error.message);
        } finally {
            generateButton.disabled = false;
            generateButton.innerHTML = originalButtonText;
        }
    });

    // --- ECHO BOT & VISUALIZER ---
    const startButton = document.getElementById('start-recording');
    const stopButton = document.getElementById('stop-recording');
    const echoAudioContainer = document.getElementById('echo-audio-container');
    const transcriptionContainer = document.getElementById('transcription-container');
    const canvas = document.getElementById('visualizer');
    
    const canvasCtx = canvas.getContext('2d');
    let audioCtx, analyser, animationFrameId, mediaRecorder, audioChunks = [];

    startButton.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            startVisualizer(stream);

            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.addEventListener('dataavailable', event => audioChunks.push(event.data));
            mediaRecorder.addEventListener('stop', () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                transcribeAndEcho(audioBlob);
                audioChunks = [];
            });

            mediaRecorder.start();
            startButton.disabled = true;
            stopButton.disabled = false;
            startButton.textContent = "Recording...";

        } catch (error) {
            console.error("Error accessing microphone:", error);
            alert("Could not access microphone. Please ensure you grant permission.");
        }
    });

    stopButton.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            stopVisualizer();
            startButton.disabled = false;
            stopButton.disabled = true;
            startButton.textContent = "Start Recording";
        }
    });

    async function transcribeAndEcho(audioBlob) {
        const voice_id = echoVoiceSelect.value; // Get selected voice
        if (!voice_id) return alert('Please select a voice for the echo.');

        const formData = new FormData();
        formData.append("audio_file", audioBlob, "recording.wav");
        
        try {
            transcriptionContainer.textContent = "Transcribing & generating echo...";
            // Send the voice_id as a query parameter
            const response = await fetch(`/tts/echo?voice_id=${voice_id}`, { method: 'POST', body: formData });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const result = await response.json();
            if (result.error) throw new Error(result.error);
            transcriptionContainer.textContent = result.transcription || "No transcription available.";
            if (result.audio_url) {
                const audioPlayer = document.createElement('audio');
                audioPlayer.src = result.audio_url;
                audioPlayer.controls = true;
                audioPlayer.autoplay = true;
                audioPlayer.classList.add('w-full', 'mt-4');
                echoAudioContainer.innerHTML = '';
                echoAudioContainer.appendChild(audioPlayer);
            }
        } catch (error) {
            console.error("Echo failed:", error);
            transcriptionContainer.textContent = `Echo failed: ${error.message}`;
        }
    }

    // (Visualizer functions remain the same)
    function startVisualizer(stream) {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        analyser.fftSize = 256;
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        draw(dataArray, bufferLength);
    }

    function stopVisualizer() {
        cancelAnimationFrame(animationFrameId);
        canvasCtx.clearRect(0, 0, canvas.width, canvas.height);
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
