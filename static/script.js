document.addEventListener('DOMContentLoaded', () => {

    // Get references to the HTML elements we need
    const textInput = document.getElementById('text-input');
    const generateButton = document.getElementById('generate-button');
    const audioContainer = document.getElementById('audio-container');

    // Add a 'click' event listener to the button
    generateButton.addEventListener('click', async () => {
        const text = textInput.value.trim();

        // Check if the user entered any text
        if (!text) {
            alert('Please enter some text.');
            return;
        }

        // Disable the button and show a "loading" state to prevent multiple clicks
        generateButton.disabled = true;
        generateButton.textContent = 'Generating...';
        audioContainer.innerHTML = ''; // Clear any previous audio player

        try {
            // Send the text to our backend '/generate-speech' endpoint
            const response = await fetch('/generate-speech', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ text: text }),
            });

            // Check if the network request itself was successful
            if (!response.ok) {
                throw new Error('Network response was not ok.');
            }

            // Get the JSON data from the response (e.g., {"audio_url": "..."})
            const data = await response.json();

            // Check if our server returned an error message (like API key failure)
            if (data.error) {
                throw new Error(data.error);
            }

            // If we get a successful response with an audio URL
            if (data.audio_url) {
                // Create a new HTML <audio> element
                const audioPlayer = document.createElement('audio');
                audioPlayer.src = data.audio_url;
                audioPlayer.controls = true; // Show the default audio controls (play, pause, volume)
                audioPlayer.autoplay = true; // Automatically start playing the audio

                // Add the new audio player to our container div
                audioContainer.appendChild(audioPlayer);
            }

        } catch (error) {
            // If anything goes wrong, show an alert and log the error to the console
            console.error('Error:', error);
            alert('Failed to generate audio. Please try again. ' + error.message);
        } finally {
            // Re-enable the button and reset its text, whether the request succeeded or failed
            generateButton.disabled = false;
            generateButton.textContent = 'Generate Audio';
        }
    });
});
