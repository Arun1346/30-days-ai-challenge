// Wait for the HTML content to be fully loaded before running the script
document.addEventListener('DOMContentLoaded', () => {

    // --- DAY 3: TEXT-TO-SPEECH FUNCTIONALITY ---
    const textInput = document.getElementById('text-input');
    const generateButton = document.getElementById('generate-button');
    const audioContainer = document.getElementById('audio-container');

    generateButton.addEventListener('click', async () => {
        const text = textInput.value.trim();
        if (!text) {
            alert('Please enter some text.');
            return;
        }
        generateButton.disabled = true;
        generateButton.textContent = 'Generating...';
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
                audioContainer.appendChild(audioPlayer);
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to generate audio. ' + error.message);
        } finally {
            generateButton.disabled = false;
            generateButton.textContent = 'Generate Audio';
        }
    });

    // --- DAY 4: ECHO BOT FUNCTIONALITY ---
    const startButton = document.getElementById('start-recording');
    const stopButton = document.getElementById('stop-recording');
    const echoAudioContainer = document.getElementById('echo-audio-container');
    
    let mediaRecorder;
    let audioChunks = [];

    // START RECORDING
    startButton.addEventListener('click', async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            
            mediaRecorder.addEventListener('dataavailable', event => {
                audioChunks.push(event.data);
            });

            mediaRecorder.addEventListener('stop', () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioUrl = URL.createObjectURL(audioBlob);
                
                // --- DIAGNOSTIC LOGGING ---
                console.log("Recording stopped. Setting loading message.");
                
                echoAudioContainer.innerHTML = '<p>Loading audio...</p>';

                const audioPlayer = document.createElement('audio');
                audioPlayer.src = audioUrl;
                audioPlayer.controls = true;
                
                audioPlayer.addEventListener('loadedmetadata', () => {
                    // --- DIAGNOSTIC LOGGING ---
                    console.log("Audio metadata loaded. Displaying player.");
                    
                    echoAudioContainer.innerHTML = '';
                    echoAudioContainer.appendChild(audioPlayer);
                    audioPlayer.play();
                });

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

    // STOP RECORDING
    stopButton.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
            startButton.disabled = false;
            stopButton.disabled = true;
            startButton.textContent = "Start Recording";
        }
    });
});
