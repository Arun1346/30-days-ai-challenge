document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded. Aether Voice script is running.");

    // --- TEXT-TO-SPEECH FUNCTIONALITY ---
    const textInput = document.getElementById('text-input');
    const generateButton = document.getElementById('generate-button');
    const audioContainer = document.getElementById('audio-container');

    if (!textInput || !generateButton || !audioContainer) {
        console.error("TTS elements not found! Please check the IDs in your index.html file.");
        return;
    }

    generateButton.addEventListener('click', async () => {
        console.log("Generate Audio button clicked.");
        const text = textInput.value.trim();
        if (!text) return alert('Please enter some text.');
        
        const originalButtonText = generateButton.innerHTML;
        generateButton.disabled = true;
        generateButton.innerHTML = 'Generating...';
        audioContainer.innerHTML = '';

        try {
            const response = await fetch('/generate-speech', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text }),
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

    if (!startButton || !stopButton || !echoAudioContainer || !transcriptionContainer || !canvas) {
        console.error("Echo Bot elements not found! Please check the IDs in your index.html file.");
        return;
    }
    
    const canvasCtx = canvas.getContext('2d');
    let audioCtx;
    let analyser;
    let animationFrameId;
    let mediaRecorder;
    let audioChunks = [];

    startButton.addEventListener('click', async () => {
        console.log("Start Recording button clicked.");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            startVisualizer(stream);

            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.addEventListener('dataavailable', event => audioChunks.push(event.data));
            mediaRecorder.addEventListener('stop', () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                transcribeAudio(audioBlob);
                const audioUrl = URL.createObjectURL(audioBlob);
                const audioPlayer = document.createElement('audio');
                audioPlayer.src = audioUrl;
                audioPlayer.controls = true;
                audioPlayer.classList.add('w-full', 'mt-4');
                echoAudioContainer.innerHTML = '';
                echoAudioContainer.appendChild(audioPlayer);
                audioPlayer.play();
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
        console.log("Stop Recording button clicked.");
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            stopVisualizer();
            startButton.disabled = false;
            stopButton.disabled = true;
            startButton.textContent = "Start Recording";
        }
    });

    async function transcribeAudio(audioBlob) {
        const formData = new FormData();
        formData.append("audio_file", audioBlob, "recording.wav");
        try {
            transcriptionContainer.textContent = "Transcribing...";
            const response = await fetch('/transcribe/file', { method: 'POST', body: formData });
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const result = await response.json();
            if (result.error) throw new Error(result.error);
            transcriptionContainer.textContent = result.transcription;
        } catch (error) {
            console.error("Transcription failed:", error);
            transcriptionContainer.textContent = `Transcription failed: ${error.message}`;
        }
    }

    function startVisualizer(stream) {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
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
            gradient.addColorStop(0, '#a855f7'); // Purple
            gradient.addColorStop(1, '#6366f1'); // Blue

            canvasCtx.fillStyle = gradient;
            canvasCtx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);

            x += barWidth + 2;
        }
    }
});
