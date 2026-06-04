import React, { useState, useEffect, useRef } from 'react';
import './ChatInterface.css';
import './download-styles.css';

const ChatInterface = ({ jobId }) => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [ws, setWs] = useState(null);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!jobId) return;

    const websocket = new WebSocket(`ws://localhost:8000/ws/${jobId}`);

    websocket.onopen = () => {
      console.log('WebSocket connected');
      setWs(websocket);
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('WebSocket message:', data);

      if (data.type === 'status_update') {
        setJobStatus(data);
        addSystemMessage(`Status: ${data.current_step} (${data.progress}%)`);
      }
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    websocket.onclose = () => {
      console.log('WebSocket disconnected');
    };

    // Keep alive ping
    const pingInterval = setInterval(() => {
      if (websocket.readyState === WebSocket.OPEN) {
        websocket.send('ping');
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      websocket.close();
    };
  }, [jobId]);

  // Poll for job status
  useEffect(() => {
    if (!jobId) return;

    const pollStatus = async () => {
      try {
        const response = await fetch(`http://localhost:8000/job/${jobId}`);
        const data = await response.json();
        setJobStatus(data);

        if (data.status === 'COMPLETED' && templates.length === 0) {
          loadTemplates();
        }
      } catch (error) {
        console.error('Error polling status:', error);
      }
    };

    pollStatus();
    const interval = setInterval(pollStatus, 5000);

    return () => clearInterval(interval);
  }, [jobId, templates.length]);

  const loadTemplates = async () => {
    try {
      const response = await fetch(`http://localhost:8000/templates/${jobId}`);
      const data = await response.json();
      console.log(data)
      if (data.template_files && data.template_files.length > 0) {
        setTemplates(data.template_files);
        addSystemMessage(
          `Found ${data.template_files.length} templates! Click below to download.`
        );
      }
    } catch (error) {
      console.error('Error loading templates:', error);
    }
  };

  const addSystemMessage = (text) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        type: 'system',
        text,
        timestamp: new Date(),
      },
    ]);
  };

  const addUserMessage = (text) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        type: 'user',
        text,
        timestamp: new Date(),
      },
    ]);
  };

  const addAssistantMessage = (text, data = {}) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now(),
        type: 'assistant',
        text,
        data,
        timestamp: new Date(),
      },
    ]);
  };
  const addDownloadMessage = (template) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now() + Math.random(),
        type: 'download',
        template: template,
        timestamp: new Date(),
      },
    ]);
  };
  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !jobId) return;

    const userMsg = inputMessage;
    setInputMessage('');
    addUserMessage(userMsg);
    setIsLoading(true);

    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_id: jobId,
          message: userMsg,
        }),
      });

      const data = await response.json();

      // Check if job is still processing
      if (data.status && data.status !== 'COMPLETED') {
        addAssistantMessage(
          `Your file is still being processed (Status: ${data.status}). Please wait a moment while I analyze your data. I'll be ready to chat once processing is complete! 🔄`
        );
      } else {
        // Check if clarification confirmation response
        if (data.clarification_confirmed) {
          addAssistantMessage(data.assistant_response);
          // Automatically trigger the transformation
          const previousMsg = messages[messages.length - 2]; // Get the clarification message
          if (previousMsg?.data?.pendingTransformation) {
            executeTransformation(previousMsg.data.pendingTransformation);
          }
        } else {
          addAssistantMessage(data.assistant_response, {
            isTransformation: data.is_transformation,
            transformationType: data.transformation_type,
            isDownloadRequest: data.is_download_request,
            downloads: data.downloads,
            clarificationNeeded: data.clarification_needed,
            clarificationQuestions: data.clarification_questions,
            pendingTransformation: data.is_transformation ? userMsg : null
          });

          // If it's a download request, show download cards
          if (data.is_download_request && data.downloads) {
            data.downloads.forEach((template) => {
              addDownloadMessage(template);
            });
          }
        }
      }
    } catch (error) {
      addAssistantMessage(`Error: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const executeTransformation = async (transformation) => {
    addSystemMessage(`Executing transformation: ${transformation}`);

    try {
      const response = await fetch('http://localhost:8000/transform', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_id: jobId,
          transformation,
        }),
      });

      const data = await response.json();
      addSystemMessage(
        'Transformation queued! This will take a few minutes. I\'ll update you when it\'s done.'
      );

      // Poll for transformation completion
      const pollTransformation = async () => {
        const jobResponse = await fetch(`http://localhost:8000/job/${jobId}`);
        const jobData = await jobResponse.json();

        if (jobData.transformed_path) {
          // Transformation completed!
          const templateDownloads = jobData.results?.template_downloads || [];
          if (templateDownloads.length > 0) {
              addSystemMessage(
                `✅ Transformation complete! Your data has been separated into ${templateDownloads.length} template files.\n\n` +
                `Click the download buttons below to get your files! 📥`
              );

              // Add each template download as a message with download button
              templateDownloads.forEach((template) => {
                addDownloadMessage(template);
              });
            } else {
              addSystemMessage(
                `✅ Transformation complete! Your data has been processed.\n\n` +
                `📊 Transformed data is ready at: ${jobData.transformed_path}`
              );
            }

          // Reload templates in case they changed
          loadTemplates();
          return true;
        }
        return false;
      };

      // Poll every 5 seconds for up to 10 minutes
      let attempts = 0;
      const maxAttempts = 120; // 10 minutes

      const pollInterval = setInterval(async () => {
        attempts++;

        const completed = await pollTransformation();

        if (completed || attempts >= maxAttempts) {
          clearInterval(pollInterval);

          if (attempts >= maxAttempts) {
            addSystemMessage('⏱️  Transformation is taking longer than expected. Please refresh to check status.');
          }
        }
      }, 5000);

    } catch (error) {
      addAssistantMessage(`Error executing transformation: ${error.message}`);
    }
  };

  const suggestedQuestions = [
    'What templates did you find?',
    'Download the template files',
    'Convert distance from meters to kilometers',
    'Show me data quality issues',
  ];

  return (
    <div className="chat-interface">
      {/* Status Bar */}
      {jobStatus && (
        <div className={`status-bar status-${jobStatus.status?.toLowerCase()}`}>
          <div className="status-content">
            <span className="status-label">Status:</span>
            <span className="status-value">{jobStatus.status}</span>
            {jobStatus.current_step && (
              <>
                <span className="status-separator">•</span>
                <span className="status-step">{jobStatus.current_step}</span>
              </>
            )}
            {jobStatus.progress !== undefined && (
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${jobStatus.progress}%` }}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Templates Section */}
      {templates.length > 0 && (
        <div className="templates-section">
          <h3>📊 Generated Templates</h3>
          <div className="template-cards">
            {templates.map((template, idx) => (
              <div key={idx} className="template-card">
                <div className="template-icon">📄</div>
                <div className="template-info">
                  <h4>{template.name}</h4>
                  <span className="template-type">{template.type}</span>
                </div>
                <a
                  href={template.url}
                  download
                  className="download-btn"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  ⬇️ Download
                </a>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="messages-container">
        {messages.length === 0 && jobStatus?.status !== 'COMPLETED' && (
          <div className="welcome-message processing">
            <div className="processing-icon">⏳</div>
            <h2>Processing Your Excel File...</h2>
            <p>
              I'm analyzing your data, detecting templates, and clustering columns.
              This usually takes a few minutes depending on file size.
            </p>
            <div className="processing-status">
              <p><strong>Current Status:</strong> {jobStatus?.status || 'Initializing'}</p>
              {jobStatus?.current_step && (
                <p><strong>Step:</strong> {jobStatus.current_step}</p>
              )}
              {jobStatus?.progress !== undefined && (
                <p><strong>Progress:</strong> {jobStatus.progress}%</p>
              )}
            </div>
            <p className="wait-message">Please wait... I'll be ready to chat once processing is complete! ☕</p>
          </div>
        )}

        {messages.length === 0 && jobStatus?.status === 'COMPLETED' && (
          <div className="welcome-message">
            <h2>👋 Hi! I'm your Excel Analysis Assistant</h2>
            <p>
              I've processed your file and detected patterns. You can ask me
              questions or request transformations!
            </p>
            <div className="suggested-questions">
              <p>Try asking:</p>
              {suggestedQuestions.map((q, idx) => (
                <button
                  key={idx}
                  className="suggestion-btn"
                  onClick={() => {
                    setInputMessage(q);
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.type}`}>
            <div className="message-avatar">
              {msg.type === 'user' ? '👤' :
               msg.type === 'system' ? '⚙️' :
               msg.type === 'download' ? '📥' : '🤖'}
            </div>
            <div className="message-content">
              {msg.type === 'download' ? (
                <div className="download-card">
                  <div className="download-info">
                    <h4>📄 {msg.template.template_name || msg.template.name}</h4>
                    <p>{msg.template.size_mb ? `${msg.template.size_mb} MB` : `${msg.template.column_count || 0} columns`}</p>
                  </div>
                  <a
                    href={msg.template.url}
                    download={msg.template.name}
                    className="download-btn-inline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    ⬇️ Download Excel
                  </a>
                </div>
              ) : (
                <>
                  <p style={{ whiteSpace: 'pre-line' }}>{msg.text}</p>

                  {/* Show clarification questions if present */}
                  {msg.data?.clarificationNeeded && msg.data?.clarificationQuestions && (
                    <div className="clarification-box" style={{
                      marginTop: '10px',
                      padding: '12px',
                      backgroundColor: '#fff3cd',
                      borderRadius: '8px',
                      borderLeft: '4px solid #ffc107'
                    }}>
                      <strong>Please clarify:</strong>
                      <ol style={{ marginTop: '8px', paddingLeft: '20px' }}>
                        {msg.data.clarificationQuestions.slice(0, 3).map((q, idx) => (
                          <li key={idx} style={{ marginBottom: '6px' }}>{q}</li>
                        ))}
                      </ol>
                      <p style={{ marginTop: '12px', fontSize: '0.9em', color: '#666' }}>
                        💡 Reply with "proceed" to continue anyway, or answer the questions above.
                      </p>
                    </div>
                  )}

                  {msg.data?.isTransformation && !msg.data?.clarificationNeeded && (
                    <button
                      className="execute-btn"
                      onClick={() => executeTransformation(msg.text)}
                    >
                      ✨ Execute Transformation
                    </button>
                  )}
                </>
              )}
              <span className="message-time">
                {msg.timestamp.toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="message message-assistant">
            <div className="message-avatar">🤖</div>
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="input-area">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
          placeholder={
            jobStatus?.status === 'COMPLETED'
              ? "Ask a question or request a transformation..."
              : "Processing file... please wait"
          }
          disabled={!jobStatus || jobStatus.status !== 'COMPLETED'}
        />
        <button
          onClick={handleSendMessage}
          disabled={!inputMessage.trim() || isLoading || jobStatus?.status !== 'COMPLETED'}
          className="send-btn"
        >
          ➤
        </button>
      </div>
    </div>
  );
};

export default ChatInterface;
