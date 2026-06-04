import React, { useState, useEffect } from "react";
import Sidebar from "../components/Sidebar/Sidebar";
import FileUpload from "../components/Upload/FileUpload";
import ChatInterface from "../components/Chat/ChatInterface";
import { getUser, logout } from "../utils/auth";
import "./Home.css";

const Home = () => {
  const [currentSession, setCurrentSession] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [user, setUser] = useState(null);

  // Get authenticated user
  useEffect(() => {
    const userData = getUser();
    if (userData) {
      setUser(userData);
    } else {
      logout(); // Redirect to login if no user
    }
  }, []);

  // Initialize from sessionStorage
  useEffect(() => {
    if (user) {
      const savedSession = sessionStorage.getItem(`currentSession_${user.user_id}`);
      if (savedSession) {
        try {
          const session = JSON.parse(savedSession);
          setCurrentSession(session);
          setShowChat(true);
        } catch (e) {
          console.error("Failed to parse session", e);
        }
      }
    }
  }, [user]);

  // Persist current session
  useEffect(() => {
    if (user && currentSession) {
      sessionStorage.setItem(`currentSession_${user.user_id}`, JSON.stringify(currentSession));
    } else if (user && !currentSession) {
      sessionStorage.removeItem(`currentSession_${user.user_id}`);
    }
  }, [currentSession, user]);

  const handleFileUploaded = (jobId, fileName) => {
    const newSession = {
      id: Date.now().toString(),
      jobId: jobId,
      fileName: fileName,
      createdAt: new Date().toISOString(),
      lastAccessed: new Date().toISOString()
    };
    setCurrentSession(newSession);
    setShowChat(true);
  };

  const handleNewSession = () => {
    setCurrentSession(null);
    setShowChat(false);
    if (user) {
      sessionStorage.removeItem(`currentSession_${user.user_id}`);
    }
  };

  const handleSessionSelect = (session) => {
    setCurrentSession(session);
    setShowChat(true);
  };

  const handleLogout = () => {
    logout(); // This will clear tokens and redirect to login
  };

  if (!user) {
    return (
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
      }}>
        <div style={{ color: "white", fontSize: "18px" }}>Loading...</div>
      </div>
    );
  }

  return (
    <div className="home-container">
      <Sidebar
        user={user.username || user.email}
        userEmail={user.email}
        userProfilePic={user.profile_picture}
        onLogout={handleLogout}
        currentSession={currentSession}
        onSessionSelect={handleSessionSelect}
        onNewSession={handleNewSession}
      />

      <div className="main-content">
        {!showChat ? (
          <div className="upload-section">
            <div className="hero">
              <h1>🚀 Excel Trace Agent</h1>
              <p className="tagline">
                Welcome back, {user.full_name || user.username}!
              </p>
              <p className="tagline">
                Process millions of rows with AI-powered analysis
              </p>
              <div className="features">
                <div className="feature">
                  ✨ Smart template detection
                </div>
                <div className="feature">
                  🔄 Natural language transformations
                </div>
                <div className="feature">
                  📊 Instant data insights
                </div>
              </div>
            </div>
            <FileUpload onFileUploaded={handleFileUploaded} />
          </div>
        ) : (
          <div className="chat-section">
            <div className="chat-header">
              <div className="chat-header-left">
                {currentSession && (
                  <div className="session-info-header">
                    <span className="session-file-name">{currentSession.fileName}</span>
                    <span className="session-job-badge">{currentSession.jobId?.substring(0, 8)}...</span>
                  </div>
                )}
              </div>
            </div>
            <ChatInterface jobId={currentSession?.jobId} />
          </div>
        )}
      </div>
    </div>
  );
};

export default Home;
