import React, { useState, useRef } from "react";
import axios from "axios";
import "./FileUpload.css";

const FileUpload = ({ onFileUploaded }) => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = (selectedFile) => {
    setError(null);

    // Validate file type
    if (!selectedFile.name.match(/\.(xlsx|xls)$/i)) {
      setError("Please upload an Excel file (.xlsx or .xls)");
      return;
    }

    // Validate file size (max 500MB)
    const maxSize = 500 * 1024 * 1024;
    if (selectedFile.size > maxSize) {
      setError("File size exceeds 500MB limit");
      return;
    }

    setFile(selectedFile);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect(droppedFile);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const upload = async () => {
    if (!file) {
      setError("Please select a file first");
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post(
        "http://localhost:8000/upload",
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
          onUploadProgress: (progressEvent) => {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            console.log(`Upload progress: ${percentCompleted}%`);
          },
        }
      );

      // Notify parent component with job_id and fileName
      if (onFileUploaded) {
        onFileUploaded(response.data.job_id, file.name);
      }
    } catch (err) {
      console.error("Upload error:", err);
      setError(
        err.response?.data?.detail ||
          "Upload failed. Please try again."
      );
      setUploading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  return (
    <div className="file-upload-container">
      <div
        className={`drop-zone ${dragOver ? "drag-over" : ""} ${
          file ? "has-file" : ""
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls"
          onChange={(e) => handleFileSelect(e.target.files[0])}
          style={{ display: "none" }}
        />

        {!file ? (
          <div className="drop-zone-content">
            <div className="upload-icon">📁</div>
            <h3>Drop your Excel file here</h3>
            <p>or click to browse</p>
            <div className="file-requirements">
              <span>✓ Supports .xlsx and .xls</span>
              <span>✓ Up to 500MB</span>
              <span>✓ Millions of rows supported</span>
            </div>
          </div>
        ) : (
          <div className="file-info">
            <div className="file-icon">📊</div>
            <div className="file-details">
              <h4>{file.name}</h4>
              <p>{formatFileSize(file.size)}</p>
            </div>
            <button
              className="remove-btn"
              onClick={(e) => {
                e.stopPropagation();
                setFile(null);
              }}
            >
              ✕
            </button>
          </div>
        )}
      </div>

      {error && <div className="error-message">⚠️ {error}</div>}

      {file && !uploading && (
        <button className="upload-btn" onClick={upload}>
          🚀 Start Processing
        </button>
      )}

      {uploading && (
        <div className="uploading-state">
          <div className="spinner"></div>
          <p>Uploading and processing your file...</p>
          <p className="upload-note">
            This may take a few minutes for large files
          </p>
        </div>
      )}
    </div>
  );
};

export default FileUpload;