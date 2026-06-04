import React, { useState, useEffect } from "react";
import "./Sidebar.css";

const Sidebar = ({ user, onLogout, currentSession, onSessionSelect, onNewSession }) => {
  const [sessions, setSessions] = useState([]);
  const [isOpen, setIsOpen] = useState(true);

  // Load sessions from localStorage
  useEffect(() => {
    const savedSessions = localStorage.getItem(`trace_sessions_${user}`);
    if (savedSessions) {
      setSessions(JSON.parse(savedSessions));
    }
  }, [user]);

  // Save sessions to localStorage whenever they change
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem(`trace_sessions_${user}`, JSON.stringify(sessions));
    }
  }, [sessions, user]);

  // Add current session to history
  useEffect(() => {
    if (currentSession && currentSession.jobId) {
      setSessions(prev => {
        // Check if session already exists
        const exists = prev.some(s => s.jobId === currentSession.jobId);
        if (exists) {
          // Update existing session
          return prev.map(s =>
            s.jobId === currentSession.jobId
              ? { ...s, ...currentSession, lastAccessed: new Date().toISOString() }
              : s
          );
        } else {
          // Add new session
          const newSession = {
            ...currentSession,
            id: Date.now().toString(),
            createdAt: new Date().toISOString(),
            lastAccessed: new Date().toISOString()
          };
          return [newSession, ...prev];
        }
      });
    }
  }, [currentSession]);

  const handleSessionClick = (session) => {
    onSessionSelect(session);
  };

  const handleDeleteSession = (sessionId, e) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.id !== sessionId));

    // If deleting current session, clear it
    if (currentSession?.id === sessionId) {
      onNewSession();
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const getTruncatedFileName = (fileName) => {
    if (!fileName) return "Untitled Session";
    if (fileName.length > 25) {
      return fileName.substring(0, 25) + "...";
    }
    return fileName;
  };

  return (
    <>
      <button
        className={`sidebar-toggle ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title={isOpen ? "Close sidebar" : "Open sidebar"}
      >
        {isOpen ? '✕' : '☰'}
      </button>

      <div className={`sidebar ${isOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <div className="sidebar-user">
            <div className="sidebar-avatar">{user[0].toUpperCase()}</div>
            <div className="sidebar-user-info">
              <span className="sidebar-username">{user}</span>
              <span className="sidebar-user-label">User</span>
            </div>
          </div>

          <button className="new-session-btn" onClick={onNewSession}>
            <span className="plus-icon">+</span>
            New Session
          </button>
        </div>

        <div className="sessions-list">
          <div className="sessions-header">
            <h3>Sessions</h3>
            <span className="session-count">{sessions.length}</span>
          </div>

          {sessions.length === 0 ? (
            <div className="no-sessions">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                <path d="M9 2L7.17 4H4C2.9 4 2 4.9 2 6V18C2 19.1 2.9 20 4 20H20C21.1 20 22 19.1 22 18V6C22 4.9 21.1 4 20 4H16.83L15 2H9Z" stroke="currentColor" strokeWidth="1.5"/>
                <circle cx="12" cy="12" r="3.5" stroke="currentColor" strokeWidth="1.5"/>
              </svg>
              <p>No sessions yet</p>
              <span>Upload a file to start</span>
            </div>
          ) : (
            <div className="sessions-scroll">
              {sessions.map(session => (
                <div
                  key={session.id}
                  className={`session-item ${currentSession?.id === session.id ? 'active' : ''}`}
                  onClick={() => handleSessionClick(session)}
                >
                  <div className="session-icon">
                    📄
                  </div>
                  <div className="session-info">
                    <div className="session-name">
                      {getTruncatedFileName(session.fileName)}
                    </div>
                    <div className="session-meta">
                      <span className="session-time">{formatDate(session.lastAccessed)}</span>
                      {session.jobId && (
                        <span className="session-job-id">
                          {session.jobId.substring(0, 8)}...
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    className="delete-session-btn"
                    onClick={(e) => handleDeleteSession(session.id, e)}
                    title="Delete session"
                  >
                    🗑️
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <button className="logout-btn-sidebar" onClick={onLogout}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M9 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M16 17L21 12L16 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M21 12H9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Logout
          </button>
        </div>
      </div>
    </>
  );
};

export default Sidebar;
