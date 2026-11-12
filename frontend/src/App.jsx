import { useEffect, useRef, useState } from "react";
import "./App.css";

const API = "http://127.0.0.1:8000";

// Seconds of audio sent to the backend at a time.
// Longer chunks = fewer pauses and less skipped audio on a slow CPU.
const CHUNK_SECONDS = 10;

function App() {
  const [status, setStatus] = useState("Ready");
  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [audioFile, setAudioFile] = useState(null);
  const [translation, setTranslation] = useState([]);
  const [originalTranscript, setOriginalTranscript] = useState([]);
  const [detectedLanguage, setDetectedLanguage] = useState("");
  const [loading, setLoading] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [error, setError] = useState("");

  const [recordEnabled, setRecordEnabled] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState("");
  const [recordingName, setRecordingName] = useState("");

  const socketRef = useRef(null);
  const streamRef = useRef(null);
  const contextRef = useRef(null);
  const sourceRef = useRef(null);
  const processorRef = useRef(null);
  const gainRef = useRef(null);

  const audioBufferRef = useRef([]);
  const sampleCountRef = useRef(0);

  const startingRef = useRef(false);
  const stoppingRef = useRef(false);

  const recorderRef = useRef(null);
  const recordChunksRef = useRef([]);
  const recordEnabledRef = useRef(false);
  const recordingUrlRef = useRef("");

  useEffect(() => {
    let mounted = true;

    const checkBackend = async () => {
      try {
        const response = await fetch(`${API}/health`);

        if (!response.ok) throw new Error();

        if (mounted) setBackendStatus("Connected");
      } catch {
        if (mounted) setBackendStatus("Disconnected");
      }
    };

    checkBackend();
    const timer = setInterval(checkBackend, 5000);

    return () => {
      mounted = false;
      clearInterval(timer);
      cleanupAudio();
    };
  }, []);

  const startRecording = stream => {
    try {
      // Free the previous recording from memory
      if (recordingUrlRef.current) {
        URL.revokeObjectURL(recordingUrlRef.current);
        recordingUrlRef.current = "";
      }

      setRecordingUrl("");
      setRecordingName("");

      const audioTracks = stream.getAudioTracks();

      if (audioTracks.length === 0) return;

      const audioOnly = new MediaStream(audioTracks);

      const mimeType = MediaRecorder.isTypeSupported(
        "audio/webm;codecs=opus"
      )
        ? "audio/webm;codecs=opus"
        : "";

      const recorder = mimeType
        ? new MediaRecorder(audioOnly, { mimeType })
        : new MediaRecorder(audioOnly);

      recordChunksRef.current = [];

      recorder.ondataavailable = event => {
        if (event.data && event.data.size > 0) {
          recordChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const chunks = recordChunksRef.current;
        recordChunksRef.current = [];

        if (chunks.length === 0) return;

        const blob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm"
        });

        const url = URL.createObjectURL(blob);
        recordingUrlRef.current = url;

        const now = new Date();
        const pad = number => String(number).padStart(2, "0");

        const name =
          "meeting-audio-" +
          now.getFullYear() +
          pad(now.getMonth() + 1) +
          pad(now.getDate()) +
          "-" +
          pad(now.getHours()) +
          pad(now.getMinutes()) +
          pad(now.getSeconds()) +
          ".webm";

        setRecordingUrl(url);
        setRecordingName(name);
      };

      recorder.start(1000);
      recorderRef.current = recorder;
    } catch (err) {
      console.error("Recording could not start:", err);
      setError("Recording could not start: " + err.message);
    }
  };

  const stopRecording = () => {
    const recorder = recorderRef.current;
    recorderRef.current = null;

    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch (err) {
        console.error("Recording stop error:", err);
      }
    }
  };

  const cleanupAudio = () => {
    // Stop recording first so the last seconds are saved
    stopRecording();

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current.onaudioprocess = null;
      processorRef.current = null;
    }

    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    if (gainRef.current) {
      gainRef.current.disconnect();
      gainRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }

    if (contextRef.current) {
      contextRef.current.close().catch(() => {});
      contextRef.current = null;
    }

    audioBufferRef.current = [];
    sampleCountRef.current = 0;
  };

  const stopTranslation = () => {
    stoppingRef.current = true;
    startingRef.current = false;

    const socket = socketRef.current;
    socketRef.current = null;

    cleanupAudio();

    if (
      socket &&
      (socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING)
    ) {
      socket.close(1000, "Stopped by user");
    }

    setIsLive(false);
    setStatus("Stopped");
  };

  const startFileTranslation = async () => {
    if (!audioFile) {
      setError("Please select an audio file first.");
      return;
    }

    setLoading(true);
    setError("");
    setTranslation([]);
    setOriginalTranscript([]);
    setDetectedLanguage("");
    setStatus("Translating audio...");

    try {
      const formData = new FormData();
      formData.append("file", audioFile);

      const response = await fetch(`${API}/translate-audio`, {
        method: "POST",
        body: formData
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Translation failed.");
      }

      setDetectedLanguage(data.language_name || data.language);
      setOriginalTranscript(data.original_transcript || []);
      setTranslation(data.translation || []);
      setStatus("Translation completed");
    } catch (err) {
      setError(err.message);
      setStatus("Translation failed");
    } finally {
      setLoading(false);
    }
  };

  const startLiveTranslation = async () => {
    // Prevent multiple simultaneous start requests
    if (startingRef.current || socketRef.current) {
      return;
    }

    startingRef.current = true;
    stoppingRef.current = false;

    setError("");
    setTranslation([]);
    setOriginalTranscript([]);
    setDetectedLanguage("");
    setStatus("Requesting screen audio permission...");

    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true,
        systemAudio: "include",
        selfBrowserSurface: "exclude"
      });

      if (stoppingRef.current) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }

      streamRef.current = stream;

      if (stream.getAudioTracks().length === 0) {
        throw new Error(
          "No system audio received. Select Entire Screen and enable system audio."
        );
      }

      if (recordEnabledRef.current) {
        startRecording(stream);
      }

      const socket = new WebSocket(
        "ws://127.0.0.1:8000/ws/browser-live"
      );

      socket.binaryType = "arraybuffer";
      socketRef.current = socket;

      socket.onmessage = event => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "status") {
            setStatus(data.message);
          }

          if (data.type === "error") {
            setError(data.message);
          }

          if (data.type === "original_transcript") {
            setDetectedLanguage(
              data.language_name || data.language
            );

            setOriginalTranscript(previous => [
              ...previous,
              {
                start: data.start,
                end: data.end,
                text: data.text
              }
            ]);
          }

          if (data.type === "translation") {
            if (data.source_language_name) {
              setDetectedLanguage(data.source_language_name);
            }

            setTranslation(previous => [
              ...previous,
              {
                start: data.start,
                end: data.end,
                text: data.text
              }
            ]);
          }
        } catch (err) {
          console.error("Message error:", err);
          setError("Could not read a backend message.");
        }
      };

      socket.onerror = event => {
        console.error("WebSocket error:", event);
        setError("WebSocket connection error. Check the backend.");
      };

      socket.onclose = event => {
        console.log(
          "WebSocket closed:",
          "Code:", event.code,
          "Reason:", event.reason,
          "Clean:", event.wasClean
        );

        if (socketRef.current !== socket) {
          return;
        }

        socketRef.current = null;
        startingRef.current = false;

        cleanupAudio();
        setIsLive(false);

        if (!stoppingRef.current) {
          setStatus("Connection lost");

          setError(
            `Audio connection closed. Code: ${event.code}. Reason: ${
              event.reason || "No reason supplied"
            }.`
          );
        }
      };

      socket.onopen = async () => {
        try {
          if (stoppingRef.current) {
            socket.close(1000, "Stopped");
            return;
          }

          const context = new AudioContext({
            sampleRate: 16000
          });

          contextRef.current = context;
          await context.resume();

          if (context.sampleRate !== 16000) {
            throw new Error(
              `Audio sample rate is ${context.sampleRate} Hz, not 16000 Hz.`
            );
          }

          const source = context.createMediaStreamSource(stream);
          sourceRef.current = source;

          const processor = context.createScriptProcessor(
            4096,
            1,
            1
          );

          processorRef.current = processor;

          const gain = context.createGain();
          gain.gain.value = 0;
          gainRef.current = gain;

          audioBufferRef.current = [];
          sampleCountRef.current = 0;

          processor.onaudioprocess = event => {
            if (
              socket.readyState !== WebSocket.OPEN ||
              stoppingRef.current
            ) {
              return;
            }

            const samples = event.inputBuffer.getChannelData(0);
            const copy = new Float32Array(samples);

            audioBufferRef.current.push(copy);
            sampleCountRef.current += copy.length;

            const targetSamples = 16000 * CHUNK_SECONDS;

            if (sampleCountRef.current >= targetSamples) {
              const combined = new Float32Array(
                sampleCountRef.current
              );

              let offset = 0;

              for (const part of audioBufferRef.current) {
                combined.set(part, offset);
                offset += part.length;
              }

              // Avoid sending if the connection is no longer open
              if (socket.readyState === WebSocket.OPEN) {
                socket.send(combined.buffer);
              }

              audioBufferRef.current = [];
              sampleCountRef.current = 0;
            }
          };

          source.connect(processor);
          processor.connect(gain);
          gain.connect(context.destination);

          startingRef.current = false;
          setIsLive(true);
          setStatus("Listening to system audio...");
        } catch (err) {
          console.error("Audio setup error:", err);

          setError("Audio setup failed: " + err.message);
          startingRef.current = false;

          cleanupAudio();

          if (socketRef.current === socket) {
            socketRef.current = null;
          }

          socket.close(1011, "Audio setup failed");
          setIsLive(false);
        }
      };

      stream.getVideoTracks()[0]?.addEventListener(
        "ended",
        () => {
          if (socketRef.current === socket) {
            stopTranslation();
          }
        },
        { once: true }
      );

    } catch (err) {
      console.error("Live translation start error:", err);

      cleanupAudio();
      startingRef.current = false;

      setError(err.message);
      setStatus("Audio capture failed");
      setIsLive(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-logo">S</div>
          <div>
            <h2>SAIL Meeting Translator</h2>
            <p>Internal Meeting Assistance System</p>
          </div>
        </div>

        <div className="connection">
          <span className="status-dot"></span>
          Backend: {backendStatus}
        </div>
      </header>

      <main className="main">
        <section className="welcome">
          <span className="eyebrow">MEETING WORKSPACE</span>
          <h1>Understand every meeting.</h1>
          <p>
            Translate meeting speech into English using locally
            processed speech recognition.
          </p>
        </section>

        <section className="controls card">
          <h3>Meeting controls</h3>
          <p className="muted">
            Supported languages include Hindi, Bengali and Korean.
            Language detection is automatic.
          </p>

          <div className="control-row">
            <input
              type="file"
              accept="audio/*"
              onChange={event => {
                setAudioFile(event.target.files[0] || null);
                setError("");
              }}
            />

            <button
              className="start-button"
              onClick={startFileTranslation}
              disabled={loading || isLive}
            >
              {loading ? "Translating..." : "Translate File"}
            </button>

            <button
              className="start-button"
              onClick={startLiveTranslation}
              disabled={isLive || loading || startingRef.current}
            >
              {isLive ? "Listening..." : "Start Live Translation"}
            </button>

            <button
              className="stop-button"
              onClick={stopTranslation}
              disabled={!isLive && !startingRef.current}
            >
              Stop
            </button>
          </div>

          <label className="record-option">
            <input
              type="checkbox"
              checked={recordEnabled}
              disabled={isLive}
              onChange={event => {
                setRecordEnabled(event.target.checked);
                recordEnabledRef.current = event.target.checked;
              }}
            />{" "}
            Also record meeting audio (saved on this computer only)
          </label>

          {recordingUrl && (
            <div className="recording-box">
              <p className="status-text">
                Recording saved: <strong>{recordingName}</strong>
              </p>
              <audio controls src={recordingUrl}></audio>
              <p>
                <a
                  className="download-link"
                  href={recordingUrl}
                  download={recordingName}
                >
                  Download recording
                </a>
              </p>
            </div>
          )}

          {audioFile && (
            <p className="status-text">
              Selected file: <strong>{audioFile.name}</strong>
            </p>
          )}

          <p className="status-text">
            Current status: <strong>{status}</strong>
          </p>

          {error && (
            <p className="status-text">{error}</p>
          )}
        </section>

        <div className="transcript-grid">
          <section className="transcript card">
            <div className="section-heading">
              <div>
                <h3>Original Transcript</h3>
                <p className="muted">
                  Detected language:{" "}
                  <strong>
                    {detectedLanguage || "Waiting for speech..."}
                  </strong>
                </p>
              </div>
              <span className="live-label">● ORIGINAL</span>
            </div>

            <div className="transcript-area">
              {originalTranscript.length > 0 ? (
                originalTranscript.map((segment, index) => (
                  <p key={index}>
                    <strong>
                      [{segment.start}s - {segment.end}s]
                    </strong>{" "}
                    {segment.text}
                  </p>
                ))
              ) : (
                <>
                  <div className="empty-icon">Aa</div>
                  <h4>Original speech will appear here</h4>
                  <p>Waiting for recognised speech.</p>
                </>
              )}
            </div>
          </section>

          <section className="transcript card">
            <div className="section-heading">
              <div>
                <h3>English Translation</h3>
                <p className="muted">
                  Translated meeting speech
                </p>
              </div>
              <span className="live-label">● ENGLISH</span>
            </div>

            <div className="transcript-area">
              {translation.length > 0 ? (
                translation.map((segment, index) => (
                  <p key={index}>
                    <strong>
                      [{segment.start}s - {segment.end}s]
                    </strong>{" "}
                    {segment.text}
                  </p>
                ))
              ) : (
                <>
                  <div className="empty-icon">Aa</div>
                  <h4>English translation will appear here</h4>
                  <p>Waiting for translation.</p>
                </>
              )}
            </div>
          </section>
        </div>

        <section className="features">
          <div className="feature card">
            <span className="feature-icon">01</span>
            <h3>Local processing</h3>
            <p>Designed for approved internal infrastructure.</p>
          </div>

          <div className="feature card">
            <span className="feature-icon">02</span>
            <h3>Multilingual translation</h3>
            <p>Hindi, Bengali, Korean and other supported languages.</p>
          </div>

          <div className="feature card">
            <span className="feature-icon">03</span>
            <h3>Meeting transcript</h3>
            <p>Display recognised speech alongside English translation.</p>
          </div>
        </section>

        <footer>
          SAIL Meeting Translator · Development Prototype
        </footer>
      </main>
    </div>
  );
}

export default App;