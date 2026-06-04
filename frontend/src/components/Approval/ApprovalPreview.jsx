import React, { useState, useEffect } from 'react';
import './ApprovalPreview.css';

const ApprovalPreview = ({ previewId, onDecision }) => {
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rejectionReason, setRejectionReason] = useState('');
  const [showCode, setShowCode] = useState(false);

  useEffect(() => {
    loadPreview();
  }, [previewId]);

  const loadPreview = async () => {
    try {
      const response = await fetch(`http://localhost:8000/approvals/${previewId}`);
      const data = await response.json();
      setPreview(data);
    } catch (error) {
      console.error('Error loading preview:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    try {
      const response = await fetch('http://localhost:8000/approvals/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preview_id: previewId,
          decision: 'approve'
        })
      });

      const result = await response.json();
      if (onDecision) onDecision('approved', result);
    } catch (error) {
      console.error('Error approving:', error);
    }
  };

  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      alert('Please provide a reason for rejection');
      return;
    }

    try {
      const response = await fetch('http://localhost:8000/approvals/decide', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          preview_id: previewId,
          decision: 'reject',
          rejection_reason: rejectionReason
        })
      });

      const result = await response.json();
      if (onDecision) onDecision('rejected', result);
    } catch (error) {
      console.error('Error rejecting:', error);
    }
  };

  if (loading) {
    return (
      <div className="approval-preview loading">
        <div className="spinner"></div>
        <p>Loading transformation preview...</p>
      </div>
    );
  }

  if (!preview) {
    return <div className="approval-preview error">Preview not found</div>;
  }

  const { request, changes, safety, execution, warnings } = preview;

  return (
    <div className="approval-preview">
      {/* Header */}
      <div className="preview-header">
        <h2>🔍 Transformation Preview</h2>
        <span className={`confidence-badge confidence-${request.confidence > 0.8 ? 'high' : 'medium'}`}>
          {Math.round(request.confidence * 100)}% confidence
        </span>
      </div>

      {/* User Request */}
      <div className="preview-section">
        <h3>📝 Your Request</h3>
        <div className="request-text">{request.original_text}</div>
        <div className="request-meta">
          <span className="intent-badge">{request.intent}</span>
          <span className="complexity-badge">{request.complexity}</span>
        </div>
      </div>

      {/* What Will Happen */}
      <div className="preview-section">
        <h3>🔄 What Will Happen</h3>
        <p className="summary">{changes.summary}</p>

        <div className="steps">
          <h4>Steps:</h4>
          <ol>
            {changes.steps.map((step, idx) => (
              <li key={idx}>{step}</li>
            ))}
          </ol>
        </div>
      </div>

      {/* Impact Analysis */}
      <div className="preview-section impact">
        <h3>📊 Impact Analysis</h3>

        <div className="impact-grid">
          <div className="impact-item">
            <label>Input Rows:</label>
            <span>{changes.input.rows.toLocaleString()}</span>
          </div>
          <div className="impact-item">
            <label>Output Rows:</label>
            <span>{typeof changes.output.rows === 'number' ? changes.output.rows.toLocaleString() : changes.output.rows}</span>
          </div>
          <div className="impact-item">
            <label>Columns Used:</label>
            <span>{changes.input.columns_used.length}</span>
          </div>
          <div className="impact-item">
            <label>New Columns:</label>
            <span className="highlight">{changes.output.new_columns.length}</span>
          </div>
        </div>

        {changes.output.new_columns.length > 0 && (
          <div className="new-columns">
            <h5>New Columns:</h5>
            <ul>
              {changes.output.new_columns.map((col, idx) => (
                <li key={idx}><code>{col}</code></li>
              ))}
            </ul>
          </div>
        )}

        {changes.output.modified_columns.length > 0 && (
          <div className="modified-columns warning">
            <h5>⚠️ Modified Columns (original values will be lost):</h5>
            <ul>
              {changes.output.modified_columns.map((col, idx) => (
                <li key={idx}><code>{col}</code></li>
              ))}
            </ul>
          </div>
        )}

        <div className="reversibility">
          {changes.data_impact.reversible ? (
            <span className="reversible">✓ Reversible (creates new columns)</span>
          ) : (
            <span className="not-reversible">⚠️ Not reversible (modifies existing data)</span>
          )}
        </div>
      </div>

      {/* Warnings */}
      {warnings && warnings.length > 0 && (
        <div className="preview-section warnings">
          <h3>⚠️ Warnings</h3>
          {warnings.map((warning, idx) => (
            <div key={idx} className={`warning-item severity-${warning.severity.toLowerCase()}`}>
              <div className="warning-header">
                <span className="warning-type">{warning.type}</span>
                <span className="warning-severity">{warning.severity}</span>
              </div>
              <p className="warning-message">{warning.message}</p>
              <p className="warning-recommendation">💡 {warning.recommendation}</p>
            </div>
          ))}
        </div>
      )}

      {/* Safety */}
      <div className="preview-section safety">
        <h3>🛡️ Safety & Quality</h3>
        <ul>
          {safety.edge_cases_handled.map((item, idx) => (
            <li key={idx}>✓ {item}</li>
          ))}
          <li>✓ {safety.null_handling}</li>
          <li>✓ {safety.type_conversions}</li>
        </ul>
      </div>

      {/* Execution Details */}
      <div className="preview-section execution">
        <h3>⚡ Execution Details</h3>
        <div className="execution-grid">
          <div className="execution-item">
            <label>⏱️ Estimated Time:</label>
            <span>{execution.estimated_time}</span>
          </div>
          <div className="execution-item">
            <label>💰 Estimated Cost:</label>
            <span>{execution.estimated_cost}</span>
          </div>
          <div className="execution-item">
            <label>🖥️ Workers:</label>
            <span>{execution.recommended_workers}</span>
          </div>
        </div>
      </div>

      {/* Code Preview (Optional) */}
      <div className="preview-section code">
        <button
          className="toggle-code-btn"
          onClick={() => setShowCode(!showCode)}
        >
          {showCode ? '▼' : '▶'} View Generated Code
        </button>

        {showCode && (
          <pre className="code-block">
            <code>{preview.code_preview.code}</code>
          </pre>
        )}
      </div>

      {/* Action Buttons */}
      <div className="preview-actions">
        <div className="reject-section">
          <textarea
            className="rejection-reason"
            placeholder="Reason for rejection (optional)..."
            value={rejectionReason}
            onChange={(e) => setRejectionReason(e.target.value)}
            rows={2}
          />
          <button className="btn-reject" onClick={handleReject}>
            ✗ Reject
          </button>
        </div>

        <button className="btn-approve" onClick={handleApprove}>
          ✓ Approve & Execute
        </button>
      </div>

      {/* Footer Info */}
      <div className="preview-footer">
        <p>
          ℹ️ This transformation will be executed on AWS Glue. You can track progress in real-time.
        </p>
        <p className="approval-expires">
          ⏰ This approval request expires in 1 hour
        </p>
      </div>
    </div>
  );
};

export default ApprovalPreview;
