document.addEventListener('DOMContentLoaded', async () => {
    console.log("🎙️ Day 22 - FINAL WORKING Audio Playback System");
    
    // Global variables
    window.audioChunks = [];
    window.currentTurnAudio = null;
    window.audioContext = null;
    let isPlayingAudio = false;
    
    // WebSocket Connection
    let ws;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    
    // Initialize Web Audio API
    async function initAudioContext() {
        if (!window.audioContext || window.audioContext.state === 'closed') {
            try {
                window.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: 44100
                });
                console.log(`✅ AudioContext initialized: ${window.audioContext.state}`);
            } catch (error) {
                console.error('❌ AudioContext init failed:', error);
                throw error;
            }
        }
        
        if (window.audioContext.state === 'suspended') {
            try {
                await window.audioContext.resume();
                console.log('🔊 AudioContext resumed');
            } catch (error) {
                console.warn('⚠️ AudioContext resume failed:', error);
            }
        }
        
        return window.audioContext;
    }
    
    // Murf-style base64 to Uint8Array conversion
    function base64ToUint8Array(base64) {
        const binary = atob(base64);
        const len = binary.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        return bytes;
    }
    
    // Create WAV header (from Murf reference)
    function createWavHeader(dataLength, sampleRate = 44100, numChannels = 1, bitDepth = 16) {
        const blockAlign = (numChannels * bitDepth) / 8;
        const byteRate = sampleRate * blockAlign;
        const buffer = new ArrayBuffer(44);
        const view = new DataView(buffer);
        
        function writeStr(offset, str) {
            for (let i = 0; i < str.length; i++) {
                view.setUint8(offset + i, str.charCodeAt(i));
            }
        }
        
        writeStr(0, "RIFF");
        view.setUint32(4, 36 + dataLength, true);
        writeStr(8, "WAVE");
        writeStr(12, "fmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, byteRate, true);
        view.setUint16(32, blockAlign, true);
        view.setUint16(34, bitDepth, true);
        writeStr(36, "data");
        view.setUint32(40, dataLength, true);
        
        return new Uint8Array(buffer);
    }
    
    // Combine WAV chunks (Murf reference approach)
    function playCombinedWavChunks(base64Chunks) {
        const pcmData = [];
        
        for (let i = 0; i < base64Chunks.length; i++) {
            const bytes = base64ToUint8Array(base64Chunks[i]);
            
            if (i === 0) {
                pcmData.push(bytes.slice(44)); // skip header in first chunk
            } else {
                pcmData.push(bytes); // entire chunk is raw PCM
            }
        }
        
        // Combine all PCM chunks
        const totalPcm = new Uint8Array(pcmData.reduce((sum, c) => sum + c.length, 0));
        let offset = 0;
        for (const part of pcmData) {
            totalPcm.set(part, offset);
            offset += part.length;
        }
        
        const wavHeader = createWavHeader(totalPcm.length);
        const finalWav = new Uint8Array(wavHeader.length + totalPcm.length);
        finalWav.set(wavHeader, 0);
        finalWav.set(totalPcm, wavHeader.length);
        
        return finalWav.buffer; // Return ArrayBuffer for decodeAudioData
    }
    
    // Play complete audio buffer
    function playCompleteAudio(audioBuffer) {
        if (!window.audioContext || !audioBuffer) {
            console.error('❌ Missing audio context or buffer');
            return;
        }

        try {
            console.log(`🔊 PLAYING AUDIO: ${audioBuffer.duration.toFixed(3)}s, ${audioBuffer.numberOfChannels}ch, ${audioBuffer.sampleRate}Hz`);
            
            const source = window.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            
            const gainNode = window.audioContext.createGain();
            source.connect(gainNode);
            gainNode.connect(window.audioContext.destination);
            
            gainNode.gain.setValueAtTime(0.7, window.audioContext.currentTime);
            
            source.start(0);
            isPlayingAudio = true;
            
            source.onended = () => {
                console.log(`✅ Audio playback completed successfully`);
                isPlayingAudio = false;
                setAgentStatus('Turn Detection + LLM Ready', 'green');
            };
            
            source.onerror = (error) => {
                console.error('❌ Audio source error:', error);
                isPlayingAudio = false;
                setAgentStatus('❌ Playback Error', 'red');
            };
            
        } catch (error) {
            console.error('❌ playCompleteAudio error:', error);
            setAgentStatus('❌ Playback Error', 'red');
        }
    }
    
    // MURF-STYLE audio chunk handler
    async function handleAudioChunk(data) {
        console.log(`🎵 RECEIVED AUDIO CHUNK for turn ${data.turn_number}`);
        console.log(`📊 Chunk size: ${data.audio_data ? data.audio_data.length : 0} chars`);
        console.log(`🏁 Final: ${data.final}`);

        // Initialize audio context
        try {
            await initAudioContext();
        } catch (error) {
            console.error('❌ Audio context error:', error);
            setAgentStatus('❌ Audio Context Error', 'red');
            return;
        }

        // Initialize turn tracking
        if (!window.currentTurnAudio || window.currentTurnAudio.turn !== data.turn_number) {
            window.currentTurnAudio = { 
                turn: data.turn_number, 
                base64Chunks: [],
                validChunks: 0
            };
            console.log(`🎯 NEW TURN: Starting audio accumulation for turn ${data.turn_number}`);
            setAgentStatus('🎵 Receiving Audio...', 'blue');
        }

        // Collect non-empty chunks
        if (data.audio_data && data.audio_data.length > 0) {
            window.currentTurnAudio.base64Chunks.push(data.audio_data);
            window.currentTurnAudio.validChunks++;
            console.log(`📦 VALID CHUNK: ${window.currentTurnAudio.validChunks} chunks accumulated`);
        }

        // Process when final OR empty chunk (Murf completion signal)
        if (data.final || (data.audio_data !== undefined && data.audio_data.length === 0)) {
            console.log("="+"=".repeat(80));
            console.log(`🎵 PROCESSING COMPLETE AUDIO - MURF STYLE`);
            console.log(`📊 Total base64 chunks: ${window.currentTurnAudio.base64Chunks.length}`);
            
            if (window.currentTurnAudio.base64Chunks.length === 0) {
                console.error(`❌ No audio chunks to process for turn ${data.turn_number}`);
                setAgentStatus('❌ No Audio Data', 'red');
                return;
            }
            
            setAgentStatus('🔄 Processing Audio (Murf Style)...', 'orange');
            
            try {
                // Use Murf's approach: combine chunks into single WAV
                const combinedWav = playCombinedWavChunks(window.currentTurnAudio.base64Chunks);
                console.log(`✅ Combined WAV created: ${combinedWav.byteLength} bytes`);
                
                // Decode the combined WAV
                console.log(`🔄 Decoding combined WAV...`);
                const audioBuffer = await window.audioContext.decodeAudioData(combinedWav);
                
                if (!audioBuffer || audioBuffer.length === 0) {
                    throw new Error('Empty decoded buffer');
                }
                
                console.log(`✅ DECODE SUCCESS:`);
                console.log(`   Duration: ${audioBuffer.duration.toFixed(3)}s`);
                console.log(`   Channels: ${audioBuffer.numberOfChannels}`);
                console.log(`   Sample Rate: ${audioBuffer.sampleRate}Hz`);
                
                // Store success
                window.audioChunks.push({
                    turn: data.turn_number,
                    chunks: window.currentTurnAudio.validChunks,
                    duration: audioBuffer.duration,
                    success: true,
                    timestamp: new Date().toISOString()
                });
                
                // Play immediately
                setAgentStatus('🔊 Playing Audio...', 'green');
                playCompleteAudio(audioBuffer);
                
                displaySystemMessage(`🎵 Playing: ${audioBuffer.duration.toFixed(1)}s (${window.currentTurnAudio.validChunks} chunks)`);
                
            } catch (error) {
                console.error(`❌ AUDIO PROCESSING FAILED:`);
                console.error(`   Error: ${error.name} - ${error.message}`);
                
                setAgentStatus('❌ Audio Decode Failed', 'red');
                displaySystemMessage(`❌ Audio failed: ${error.message}`);
                
                window.audioChunks.push({
                    turn: data.turn_number,
                    chunks: window.currentTurnAudio.validChunks,
                    success: false,
                    error: error.message,
                    timestamp: new Date().toISOString()
                });
            }
            
            console.log("="+"=".repeat(80));
            
            // Reset
            setTimeout(() => {
                window.currentTurnAudio = null;
                if (!isPlayingAudio) {
                    setAgentStatus('Turn Detection + LLM Ready', 'green');
                }
            }, 1000);
        }
    }

    function handleAudioStreamingComplete(data) {
        console.log(`🎵 Audio streaming complete for turn ${data.turn_number}`);
        console.log(`📊 Server reported ${data.total_chunks} total chunks`);
        
        // Trigger final processing if not already done
        if (window.currentTurnAudio && window.currentTurnAudio.base64Chunks.length > 0) {
            handleAudioChunk({ 
                turn_number: data.turn_number, 
                audio_data: "", 
                final: true 
            });
        }
    }

    // Global debug functions
    window.inspectAudio = function() {
        console.log("🔍 AUDIO INSPECTION:");
        console.log(`📊 Total attempts: ${window.audioChunks.length}`);
        console.log(`🎵 AudioContext: ${window.audioContext ? window.audioContext.state : 'null'}`);
        console.log(`▶️ Playing: ${isPlayingAudio}`);
        console.log(`🎯 Current turn:`, window.currentTurnAudio);
        
        window.audioChunks.forEach((attempt, i) => {
            const status = attempt.success ? '✅' : '❌';
            console.log(`${status} Turn ${attempt.turn}: ${attempt.chunks} chunks, ${attempt.duration ? attempt.duration.toFixed(3) : 'N/A'}s`);
            if (attempt.error) console.log(`   Error: ${attempt.error}`);
        });
        
        return { audioChunks: window.audioChunks, currentTurn: window.currentTurnAudio };
    };

    window.testAudio = function() {
        console.log("🧪 Testing audio...");
        initAudioContext().then(() => {
            const oscillator = window.audioContext.createOscillator();
            const gainNode = window.audioContext.createGain();
            oscillator.connect(gainNode);
            gainNode.connect(window.audioContext.destination);
            oscillator.frequency.value = 440;
            gainNode.gain.setValueAtTime(0.1, window.audioContext.currentTime);
            oscillator.start();
            oscillator.stop(window.audioContext.currentTime + 0.5);
            console.log("🔊 Test tone should play");
        });
    };
    
    // WebSocket connection
    function connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
        
        ws.onopen = () => {
            console.log("✅ WebSocket connected");
            setAgentStatus('Turn Detection + LLM Ready', 'green');
            reconnectAttempts = 0;
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                switch (data.type) {
                    case 'connection_established':
                        setAgentStatus('Turn Detection + LLM Active', 'green');
                        displaySystemMessage("Audio system ready!");
                        break;
                        
                    case 'partial_transcript':
                        displayPartialTranscription(data.text);
                        setAgentStatus('🎤 User Speaking...', 'blue');
                        break;
                        
                    case 'final_transcript':
                    case 'turn_completed':
                    case 'turn_updated':
                        displayFinalTranscription(data.text || data.final_transcript, data.turn_number);
                        updateOrAddTurnInHistory(data);
                        break;
                        
                    case 'llm_streaming_start':
                        setAgentStatus('🤖 AI Thinking...', 'orange');
                        break;
                        
                    case 'llm_chunk':
                        setAgentStatus('🤖 AI Responding...', 'purple');
                        break;
                        
                    case 'llm_streaming_complete':
                        setAgentStatus('🎵 Generating Audio...', 'blue');
                        displaySystemMessage(`AI: ${data.full_response.substring(0, 100)}...`);
                        break;
                        
                    case 'audio_chunk':
                        handleAudioChunk(data);
                        break;
                        
                    case 'audio_streaming_complete':
                        handleAudioStreamingComplete(data);
                        break;
                        
                    case 'llm_error':
                        setAgentStatus('❌ LLM Error', 'red');
                        break;
                        
                    case 'error':
                        setAgentStatus(`❌ ${data.message}`, 'red');
                        break;
                        
                    case 'session_begin':
                        displaySystemMessage("Session started - speak naturally!");
                        break;
                        
                    default:
                        console.log(`📨 Unhandled: ${data.type}`, data);
                }
            } catch (e) {
                console.log("📨 Raw message:", event.data);
            }
        };
        
        ws.onclose = () => {
            setAgentStatus('Disconnected', 'gray');
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                setTimeout(connectWebSocket, 3000);
            }
        };
        
        ws.onerror = (error) => {
            console.error("❌ WebSocket error:", error);
        };
    }

    connectWebSocket();

    // Recording and UI setup
    let isRecording = false;
    let recordingAudioContext;
    let processor;

    const voiceSelect = document.getElementById('voice-select');
    const recordButton = document.getElementById('record-button');
    const recordIcon = document.getElementById('record-icon');
    const stopIcon = document.getElementById('stop-icon');
    const agentStatus = document.getElementById('agent-status');
    const currentTurnContainer = document.getElementById('current-turn-container');
    const turnHistoryContainer = document.getElementById('turn-history-container');
    const systemMessagesContainer = document.getElementById('system-messages');

    // Load voices
    async function loadVoices() {
        try {
            const response = await fetch('/voices');
            const data = await response.json();
            
            voiceSelect.innerHTML = '';
            data.voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.voice_id;
                option.textContent = `${voice.name} (${voice.labels.gender || 'N/A'})`;
                voiceSelect.appendChild(option);
            });
            console.log(`✅ Loaded ${data.voices.length} voices`);
        } catch (error) {
            console.error("❌ Voice loading failed:", error);
        }
    }

    await loadVoices();

    // Recording button
    recordButton.addEventListener('click', async () => {
        if (isRecording) {
            stopRecording();
        } else {
            await startRecording();
        }
    });

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
                throw new Error("WebSocket not connected");
            }

            await initAudioContext();

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
            setAgentStatus('🎙️ Recording...', 'red');
            clearCurrentTurn();

            recordingAudioContext = new (window.AudioContext || window.webkitAudioContext)({ 
                sampleRate: 16000 
            });
            
            const source = recordingAudioContext.createMediaStreamSource(stream);
            processor = recordingAudioContext.createScriptProcessor(4096, 1, 1);

            processor.onaudioprocess = (event) => {
                if (isRecording && ws && ws.readyState === WebSocket.OPEN) {
                    const inputData = event.inputBuffer.getChannelData(0);
                    const int16Data = convertFloat32ToInt16(inputData);
                    ws.send(int16Data.buffer);
                }
            };

            source.connect(processor);
            processor.connect(recordingAudioContext.destination);
            window.currentStream = stream;

            console.log("🎙️ Recording started");

        } catch (error) {
            console.error("❌ Recording error:", error);
            alert(`Microphone error: ${error.message}`);
            isRecording = false;
            updateButtonUI(false);
            setAgentStatus('❌ Mic Error', 'red');
        }
    }

    function stopRecording() {
        if (!isRecording) return;
        
        isRecording = false;
        updateButtonUI(false);
        setAgentStatus('⏹️ Stopping...', 'orange');

        if (processor) {
            processor.disconnect();
            processor = null;
        }

        if (recordingAudioContext) {
            recordingAudioContext.close();
            recordingAudioContext = null;
        }

        if (window.currentStream) {
            window.currentStream.getTracks().forEach(track => track.stop());
            window.currentStream = null;
        }

        setTimeout(() => {
            if (!isPlayingAudio) {
                setAgentStatus('Turn Detection + LLM Ready', 'green');
            }
        }, 1000);
    }

    function updateButtonUI(recording) {
        if (recordIcon && stopIcon) {
            recordIcon.style.display = recording ? 'none' : 'block';
            stopIcon.style.display = recording ? 'block' : 'none';
            recordButton.classList.toggle('recording', recording);
        }
    }

    function setAgentStatus(message, color) {
        if (agentStatus) {
            agentStatus.textContent = message;
            agentStatus.className = `px-4 py-2 rounded-lg font-medium ${getColorClass(color)}`;
        }
    }

    function getColorClass(color) {
        const colors = {
            'green': 'bg-green-900/30 text-green-300 border border-green-600',
            'blue': 'bg-blue-900/30 text-blue-300 border border-blue-600',
            'red': 'bg-red-900/30 text-red-300 border border-red-600',
            'orange': 'bg-orange-900/30 text-orange-300 border border-orange-600',
            'purple': 'bg-purple-900/30 text-purple-300 border border-purple-600',
            'gray': 'bg-gray-900/30 text-gray-300 border border-gray-600'
        };
        return colors[color] || colors['gray'];
    }

    function displayPartialTranscription(text) {
        if (currentTurnContainer) {
            currentTurnContainer.innerHTML = `
                <div class="bg-blue-900/20 border border-blue-600 rounded-lg p-4">
                    <div class="flex items-center gap-2 mb-2">
                        <div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                        <span class="text-blue-300 font-medium">Speaking...</span>
                    </div>
                    <div class="text-gray-300">"${text}"</div>
                </div>
            `;
        }
    }

    function displayFinalTranscription(text, turnNumber) {
        if (currentTurnContainer) {
            currentTurnContainer.innerHTML = `
                <div class="bg-green-900/20 border border-green-600 rounded-lg p-4">
                    <div class="flex items-center gap-2 mb-2">
                        <div class="w-2 h-2 bg-green-500 rounded-full"></div>
                        <span class="text-green-300 font-medium">Turn ${turnNumber} Complete</span>
                    </div>
                    <div class="text-gray-300">"${text}"</div>
                </div>
            `;
        }
    }

    function clearCurrentTurn() {
        if (currentTurnContainer) {
            currentTurnContainer.innerHTML = `
                <div class="bg-gray-900/20 border border-gray-600 rounded-lg p-4">
                    <span class="text-gray-400">Start speaking to see real-time turn detection</span>
                </div>
            `;
        }
    }

    function updateOrAddTurnInHistory(data) {
        if (!turnHistoryContainer) return;

        let existingTurnElement = turnHistoryContainer.querySelector(`[data-turn-number="${data.turn_number}"]`);
        if (existingTurnElement) {
            const transcriptElement = existingTurnElement.querySelector('.transcript-text');
            if (transcriptElement) {
                transcriptElement.textContent = `"${data.text || data.final_transcript}"`;
            }
        } else {
            const turnElement = document.createElement('div');
            turnElement.className = 'turn-history-item bg-green-900/30 border border-green-600 rounded-lg p-4 mb-3';
            turnElement.setAttribute('data-turn-number', data.turn_number);
            turnElement.innerHTML = `
                <div class="flex items-center justify-between mb-2">
                    <span class="text-green-300 font-medium">Turn ${data.turn_number}</span>
                    <span class="text-xs text-gray-400">${new Date().toLocaleTimeString()}</span>
                </div>
                <div class="transcript-text text-gray-300">"${data.text || data.final_transcript}"</div>
            `;
            turnHistoryContainer.appendChild(turnElement);
            turnHistoryContainer.scrollTop = turnHistoryContainer.scrollHeight;
        }
    }

    function displaySystemMessage(message) {
        if (systemMessagesContainer) {
            const messageElement = document.createElement('div');
            messageElement.className = 'bg-gray-900/30 border border-gray-600 rounded-lg p-3 mb-2';
            messageElement.innerHTML = `
                <div class="flex items-center gap-2">
                    <div class="w-1.5 h-1.5 bg-gray-500 rounded-full"></div>
                    <span class="text-sm text-gray-400">${message}</span>
                    <span class="text-xs text-gray-500 ml-auto">${new Date().toLocaleTimeString()}</span>
                </div>
            `;
            systemMessagesContainer.appendChild(messageElement);
            systemMessagesContainer.scrollTop = systemMessagesContainer.scrollHeight;
        }
    }

    clearCurrentTurn();
    
    // Initialize audio on first click
    document.addEventListener('click', async () => {
        try {
            await initAudioContext();
            console.log('🔊 Audio ready for playback');
        } catch (error) {
            console.log('Audio will initialize when needed');
        }
    }, { once: true });
    
    console.log("✅ Day 22 - FINAL Audio System Ready");
    console.log("🔧 Debug commands: inspectAudio(), testAudio()");
});
