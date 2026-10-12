# page.jsx

// /mnt/MyDocuments/new_analyzer/migration-service/migration_analysis_api_latest/app/page.jsx
"use client";

import React, { useState } from 'react';

const CodeConversionTool = () => {
  const [formData, setFormData] = useState({
    sourceTech: 'VB.NET',
    targetTech: 'C#',
    sourcePath: '/mnt/MyDocuments/new_analyzer/migration-service/migration_analysis_api_latest/input/19/Fast-Food-Management-System-master'
  });
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [output, setOutput] = useState(null);
  const [summary, setSummary] = useState('');
  const [reportData, setReportData] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    if (errors[name]) setErrors(prev => ({ ...prev, [name]: '' }));
  };

  const validate = () => {
    const newErrors = {};
    if (!formData.sourceTech.trim()) newErrors.sourceTech = "Source technology is required";
    if (!formData.targetTech.trim()) newErrors.targetTech = "Target technology is required";
    if (!formData.sourcePath.trim()) newErrors.sourcePath = "Source folder path is required";
    return newErrors;
  };

  const handleRun = async (e) => {
    e.preventDefault();
    const validationErrors = validate();
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      setOutput(null);
      return;
    }

    setIsLoading(true);
    setOutput(null);

    try {
      const response = await fetch('/api/vbnet/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sourcePath: formData.sourcePath,
          migrationId: 'fast-food-demo'
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.error || 'Analysis failed');
      }

      const data = await response.json();

      setSummary(data.summary);
      setReportData(data.metrics);
      setOutput(data.report);

    } catch (error) {
      setSummary(`Analysis failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const downloadOutput = () => {
    if (!output) return;
    const blob = new Blob([output], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'vbnet_analysis_report.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      {/* ✅ Added heading */}
      <div style={{ textAlign: 'center', marginBottom: '24px' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: '700', color: '#1a1c26', margin: 0 }}>
          VB.NET Project Health Analyzer
        </h1>
      </div>

      {/* Configuration Card */}
      <div className="migration-card">
        <div>
          <div className="migration-label">ANALYSIS CONFIGURATION</div>
          <div className="migration-name">Define Analysis Parameters</div>
        </div>
        <div className="migration-right">
          <div>
            <div className="migration-label">Source Technology</div>
            <input
              type="text"
              id="sourceTech"
              name="sourceTech"
              value={formData.sourceTech}
              onChange={handleChange}
              placeholder="e.g., VB.NET"
              className={errors.sourceTech ? 'input-error' : ''}
              style={{
                width: '100%',
                padding: '12px 16px',
                border: '2px solid #e0e0e0',
                borderRadius: '8px',
                fontSize: '16px',
                fontWeight: '800',
                color: '#1a1c26',
                boxSizing: 'border-box'
              }}
            />
            {errors.sourceTech && <span className="error-text">{errors.sourceTech}</span>}
          </div>

          <div>
            <div className="migration-label">Target Technology</div>
            <input
              type="text"
              id="targetTech"
              name="targetTech"
              value={formData.targetTech}
              onChange={handleChange}
              placeholder="e.g., C#"
              className={errors.targetTech ? 'input-error' : ''}
              style={{
                width: '100%',
                padding: '12px 16px',
                border: '2px solid #e0e0e0',
                borderRadius: '8px',
                fontSize: '16px',
                fontWeight: '800',
                color: '#1a1c26',
                boxSizing: 'border-box'
              }}
            />
            {errors.targetTech && <span className="error-text">{errors.targetTech}</span>}
          </div>

          <div>
            <div className="migration-label">Source Folder Path</div>
            <input
              type="text"
              id="sourcePath"
              name="sourcePath"
              value={formData.sourcePath}
              onChange={handleChange}
              placeholder="/path/to/vbnet/project"
              className={errors.sourcePath ? 'input-error' : ''}
              style={{
                width: '100%',
                padding: '12px 16px',
                border: '2px solid #e0e0e0',
                borderRadius: '8px',
                fontSize: '16px',
                fontWeight: '800',
                color: '#1a1c26',
                boxSizing: 'border-box'
              }}
            />
            {errors.sourcePath && <span className="error-text">{errors.sourcePath}</span>}
          </div>
        </div>
      </div>

      {/* Run Button */}
      <button
        onClick={handleRun}
        disabled={isLoading}
        className="start-btn"
        style={{
          width: '100%',
          justifyContent: 'center',
          padding: '16px 24px',
          fontSize: '16px',
          marginTop: '20px'
        }}
      >
        {isLoading ? 'Analyzing...' : 'Run Analysis'}
      </button>

      {/* Output Section */}
      {output && (
        <div className="artifacts-card" style={{ marginTop: '30px' }}>
          <div className="section-eyebrow">Analysis OUTPUT</div>
          <h2 className="section-title">Analysis Report</h2>

          <div className="artifact-item">
            <div className="artifact-top">
              <div className="artifact-icon">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#C2410C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="8" y1="13" x2="16" y2="13" />
                  <line x1="8" y1="17" x2="16" y2="17" />
                  <line x1="8" y1="9" x2="10" y2="9" />
                </svg>
              </div>
              <span className="generated-badge">Generated</span>
            </div>
            <div className="artifact-code">REPORT.txt</div>
            <div className="artifact-desc">Detailed Analysis report with changes and statistics</div>

            {/* Output Preview */}
            <div className="artifact-item" style={{
              background: '#f8f8fa',
              padding: '16px',
              borderRadius: '8px',
              marginTop: '16px',
              maxHeight: '200px',
              overflowY: 'auto',
              fontFamily: 'monospace',
              fontSize: '14px',
              whiteSpace: 'pre-wrap'
            }}>
              {output}
            </div>

            {/* Download Button */}
            <button
              onClick={downloadOutput}
              className="view-btn"
              style={{
                marginTop: '16px',
                background: '#C2410C',
                color: 'white',
                border: 'none'
              }}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download Report
            </button>
          </div>

          {/* Summary Section */}
          <div className="status-card" style={{ marginTop: '24px' }}>
            <div className="status-icon" style={{ background: '#C2410C' }}>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
            </div>
            <div className="status-text">
              <div className="status-title">Analysis Summary</div>
              <div className="status-desc">{summary}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CodeConversionTool;
