import React, { useState } from 'react';
import {
  UploadCloud,
  FileText,
  FileSpreadsheet,
  Cpu,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Plus,
  RefreshCw,
  Eye,
  X,
  Sparkles,
  Sliders,
  Check,
  Table as TableIcon,
  Layers
} from 'lucide-react';
import { fetchOcrPreview, reprocessOcr } from '../services/api';

export default function DataSourcesView() {
  const [isUploading, setIsUploading] = useState(false);
  const [activeTab, setActiveTab] = useState('all');
  const [selectedFileForOcr, setSelectedFileForOcr] = useState(null);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);

  const [files, setFiles] = useState([
    {
      id: 'f_digital',
      name: 'sample_inspection_digital.pdf',
      type: 'pdf',
      extractionMethod: 'native_text',
      status: 'INDEXED (DIGITAL)',
      statusType: 'indexed',
      ocrConfidence: 100.0,
      skewAngle: '0.0°',
      pages: 1,
      chunks: 3,
      needsReview: false,
      rbac: ['maintenance_engineer', 'supervisor'],
      sha: 'SHA-256: 4202f58b...',
      size: '3.9 KB',
      tablesCount: 2
    },
    {
      id: 'f_scanned',
      name: 'sample_inspection_scanned.pdf',
      type: 'pdf',
      extractionMethod: 'ocr_fallback',
      status: 'OCR VERIFIED (SCANNED)',
      statusType: 'scanned_ocr',
      ocrConfidence: 94.2,
      skewAngle: '0.0°',
      pages: 1,
      chunks: 4,
      needsReview: false,
      rbac: ['maintenance_engineer', 'supervisor', 'plant_manager'],
      sha: 'SHA-256: ea215d5e...',
      size: '404.3 KB',
      tablesCount: 2
    },
    {
      id: 'f_hybrid',
      name: 'sulzer_p102_manual_hybrid.pdf',
      type: 'pdf',
      extractionMethod: 'hybrid',
      status: 'HYBRID EXTRACTED',
      statusType: 'hybrid',
      ocrConfidence: 89.4,
      skewAngle: '-1.2°',
      pages: 3,
      chunks: 18,
      needsReview: false,
      rbac: ['maintenance_engineer', 'supervisor'],
      sha: 'SHA-256: 8f23c91a...',
      size: '1.4 MB',
      tablesCount: 3
    },
    {
      id: 'f_degraded',
      name: 'degraded_carbon_copy_log.pdf',
      type: 'pdf',
      extractionMethod: 'ocr_fallback',
      status: 'NEEDS HUMAN REVIEW',
      statusType: 'review_needed',
      ocrConfidence: 56.8,
      skewAngle: '+3.5°',
      pages: 1,
      chunks: 2,
      needsReview: true,
      rbac: ['maintenance_engineer', 'supervisor'],
      sha: 'SHA-256: b387c911...',
      size: '312.0 KB',
      tablesCount: 1
    },
    {
      id: 'f_csv',
      name: 'equipment_maintenance.csv',
      type: 'csv',
      extractionMethod: 'duckdb',
      status: 'DUCKDB READY',
      statusType: 'duckdb',
      ocrConfidence: null,
      skewAngle: null,
      pages: 1,
      chunks: 64,
      needsReview: false,
      rbac: ['supervisor', 'plant_manager'],
      sha: 'SHA-256: 7706c372...',
      size: '5.7 KB (60 rows)',
      tablesCount: 1
    },
    {
      id: 'f_vision',
      name: 'PID_Cooling_Circuit_P101.png',
      type: 'vision',
      extractionMethod: 'vlm_vision',
      status: 'VLM DIAGRAM PARSED',
      statusType: 'vision',
      ocrConfidence: 96.0,
      skewAngle: '0.0°',
      pages: 1,
      chunks: 8,
      needsReview: false,
      rbac: ['maintenance_engineer', 'supervisor'],
      sha: 'SHA-256: 2ea4c376...',
      size: '2.1 MB',
      tablesCount: 1
    }
  ]);

  const handleSimulatedUpload = () => {
    setIsUploading(true);
    setTimeout(() => {
      setFiles(prev => [
        {
          id: `f_${Date.now()}`,
          name: 'HEX301_Scanned_Log_2026.pdf',
          type: 'pdf',
          extractionMethod: 'ocr_fallback',
          status: 'OCR VERIFIED (SCANNED)',
          statusType: 'scanned_ocr',
          ocrConfidence: 92.8,
          skewAngle: '+0.5°',
          pages: 2,
          chunks: 12,
          needsReview: false,
          rbac: ['maintenance_engineer'],
          sha: 'SHA-256: c3b91a02...',
          size: '620.4 KB',
          tablesCount: 1
        },
        ...prev
      ]);
      setIsUploading(false);
    }, 1200);
  };

  const handleOpenOcrInspector = (file) => {
    setSelectedFileForOcr(file);
  };

  const handleApproveReview = () => {
    if (!selectedFileForOcr) return;
    setFiles(prev =>
      prev.map(f =>
        f.id === selectedFileForOcr.id
          ? { ...f, needsReview: false, status: 'OCR VERIFIED (APPROVED)', statusType: 'scanned_ocr', ocrConfidence: 85.0 }
          : f
      )
    );
    setSelectedFileForOcr(prev => ({ ...prev, needsReview: false, status: 'OCR VERIFIED (APPROVED)', ocrConfidence: 85.0 }));
  };

  const handleReprocess = async () => {
    setReprocessing(true);
    setTimeout(() => {
      setFiles(prev =>
        prev.map(f =>
          f.id === selectedFileForOcr.id
            ? { ...f, needsReview: false, ocrConfidence: 93.5, skewAngle: '0.0°', status: 'OCR RE-INDEXED (HIGH-RES)', statusType: 'scanned_ocr' }
            : f
        )
      );
      setSelectedFileForOcr(prev => ({
        ...prev,
        needsReview: false,
        ocrConfidence: 93.5,
        skewAngle: '0.0°',
        status: 'OCR RE-INDEXED (HIGH-RES)'
      }));
      setReprocessing(false);
    }, 1400);
  };

  const filteredFiles = files.filter(f => {
    if (activeTab === 'scanned') return f.extractionMethod === 'ocr_fallback' || f.extractionMethod === 'hybrid';
    if (activeTab === 'review') return f.needsReview;
    if (activeTab === 'telemetry') return f.type === 'csv';
    return true;
  });

  return (
    <div className="space-y-5">
      {/* View Header */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[11px] font-mono font-bold tracking-widest text-[#6d675e] uppercase">
            KNOWLEDGE • DUAL-ENGINE OCR INGESTION
          </span>
          <h1 className="text-xl font-display font-bold text-[#f5f2ed]">
            Data Sources & OCR Extraction Hub
          </h1>
        </div>
        <button
          onClick={handleSimulatedUpload}
          className="btn-copper text-xs py-1.5 px-3.5 flex items-center gap-1.5"
        >
          <Plus size={14} />
          <span>Ingest Scanned or Digital PDF</span>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Drag-and-Drop Ingestion Zone */}
        <div className="lg:col-span-5 clora-card p-5 space-y-4 flex flex-col justify-between">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-[#f5f2ed] uppercase tracking-wide flex items-center gap-2">
              <span>Local Document & OCR Ingestion</span>
              <span className="text-[9px] px-2 py-0.5 rounded bg-[#2a241e] text-[#d9825b] font-mono font-bold">
                DUAL-ENGINE ACTIVE
              </span>
            </h3>
            <p className="text-[11px] text-[#a09a90]">
              Automatically auto-triages digital text streams, scanned raster sheets, and embedded stamps with zero external network egress.
            </p>
          </div>

          {/* Upload Drop Target */}
          <div
            onClick={handleSimulatedUpload}
            className="border-2 border-dashed border-[#3b3630] hover:border-[#d9825b] rounded-xl p-7 flex flex-col items-center justify-center text-center space-y-3 bg-[#151312] cursor-pointer transition-all group"
          >
            <div className="w-12 h-12 rounded-full bg-[#201d1a] border border-[#3b3630] flex items-center justify-center text-[#d9825b] group-hover:scale-110 transition-transform">
              <UploadCloud size={24} />
            </div>
            <div className="space-y-1">
              <div className="text-xs font-semibold text-[#f5f2ed]">
                {isUploading ? 'Deskewing & OCR Vector Indexing...' : 'Drag and drop files here'}
              </div>
              <div className="text-[10px] text-[#6d675e]">
                Scanned PDFs, Photocopies, Digital Manuals, P&ID Schematics, CSV
              </div>
            </div>
          </div>

          {/* OCR Pipeline Specs */}
          <div className="space-y-2">
            <div className="p-3 rounded-xl bg-[#1a1715] border border-[#2e2a25] space-y-1.5 text-[11px]">
              <div className="flex items-center justify-between text-[#d9825b] font-semibold text-[10px] uppercase font-mono">
                <span>OCR Pipeline Diagnostics</span>
                <span className="text-[#10b981]">Engine: Tesseract v5 + PyMuPDF</span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center pt-1 font-mono text-[10px]">
                <div className="p-1.5 rounded bg-[#201d1a] border border-[#3b3630]">
                  <div className="text-[#6d675e]">PREPROCESS</div>
                  <div className="text-[#f5f2ed] font-semibold">Deskew + CLAHE</div>
                </div>
                <div className="p-1.5 rounded bg-[#201d1a] border border-[#3b3630]">
                  <div className="text-[#6d675e]">HITL THRESHOLD</div>
                  <div className="text-[#f5f2ed] font-semibold">&lt; 60% Review</div>
                </div>
                <div className="p-1.5 rounded bg-[#201d1a] border border-[#3b3630]">
                  <div className="text-[#6d675e]">TABLE RECON</div>
                  <div className="text-[#f5f2ed] font-semibold">2D Baselines</div>
                </div>
              </div>
            </div>

            {/* Security Badge */}
            <div className="p-3 rounded-xl bg-[#161f18] border border-[#234529] flex items-center gap-3">
              <ShieldCheck size={18} className="text-[#10b981] shrink-0" />
              <div className="space-y-0.5">
                <div className="text-[11px] font-semibold text-[#10b981]">
                  100% AIR-GAPPED • ON-PREMISE OCR PIPELINE
                </div>
                <div className="text-[10px] text-[#8ca68c]">
                  All raster processing, deskewing, and OCR inference execute locally on the host machine.
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Data Table */}
        <div className="lg:col-span-7 clora-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-[#2e2a25] pb-2.5">
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-semibold text-[#f5f2ed] uppercase tracking-wide">
                Ingested Documents & Telemetry ({filteredFiles.length})
              </h3>
            </div>
            {/* Filter Tabs */}
            <div className="flex items-center gap-1 bg-[#1a1715] p-1 rounded-lg border border-[#2e2a25]">
              <button
                onClick={() => setActiveTab('all')}
                className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                  activeTab === 'all' ? 'bg-[#2a241e] text-[#d9825b] font-semibold' : 'text-[#6d675e] hover:text-[#a09a90]'
                }`}
              >
                All
              </button>
              <button
                onClick={() => setActiveTab('scanned')}
                className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                  activeTab === 'scanned' ? 'bg-[#2a241e] text-[#d9825b] font-semibold' : 'text-[#6d675e] hover:text-[#a09a90]'
                }`}
              >
                Scanned & Hybrid
              </button>
              <button
                onClick={() => setActiveTab('review')}
                className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                  activeTab === 'review' ? 'bg-[#2a241e] text-[#d9825b] font-semibold' : 'text-[#6d675e] hover:text-[#a09a90]'
                }`}
              >
                Needs Review
              </button>
            </div>
          </div>

          <div className="divide-y divide-[#26231f]">
            {filteredFiles.map((file) => (
              <div key={file.id} className="py-3 px-1.5 flex items-center justify-between hover:bg-[#1b1917] rounded-lg transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-[#201d1a] border border-[#3b3630] flex items-center justify-center text-[#d9825b] shrink-0">
                    {file.type === 'csv' ? (
                      <FileSpreadsheet size={15} className="text-[#10b981]" />
                    ) : file.type === 'vision' ? (
                      <Cpu size={15} className="text-[#38bdf8]" />
                    ) : (
                      <FileText size={15} className="text-[#d9825b]" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-[#f5f2ed] truncate flex items-center gap-2">
                      <span>{file.name}</span>
                      {file.needsReview && (
                        <span className="px-1.5 py-0.2 text-[9px] bg-[#3a1a16] text-[#ef4444] border border-[#5c241c] rounded font-mono font-bold animate-pulse">
                          REVIEW REQUIRED
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-[#6d675e] flex items-center gap-2 mt-0.5">
                      <span>{file.size}</span>
                      <span>•</span>
                      <span className="font-mono text-[#a09a90]">{file.sha}</span>
                      {file.skewAngle && (
                        <>
                          <span>•</span>
                          <span className="text-[#8ca68c] font-mono">Skew: {file.skewAngle}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <div className="flex flex-col items-end gap-1">
                    {file.statusType === 'indexed' && (
                      <span className="status-pill-sage">{file.status}</span>
                    )}
                    {file.statusType === 'scanned_ocr' && (
                      <span className="status-pill-copper flex items-center gap-1">
                        <Sparkles size={10} />
                        <span>{file.status}</span>
                      </span>
                    )}
                    {file.statusType === 'hybrid' && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#1e293b] text-[#38bdf8] border border-[#0284c7]">
                        {file.status}
                      </span>
                    )}
                    {file.statusType === 'review_needed' && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#3b1c18] text-[#f87171] border border-[#991b1b] flex items-center gap-1">
                        <AlertTriangle size={10} />
                        <span>CONFIDENCE &lt; 60%</span>
                      </span>
                    )}
                    {file.statusType === 'duckdb' && (
                      <span className="status-pill-emerald">{file.status}</span>
                    )}
                    {file.statusType === 'vision' && (
                      <span className="status-pill-copper">{file.status}</span>
                    )}

                    <div className="flex items-center gap-2 text-[9px] font-mono text-[#6d675e]">
                      {file.ocrConfidence !== null && (
                        <span className={file.ocrConfidence < 60 ? 'text-[#ef4444]' : 'text-[#10b981]'}>
                          {file.ocrConfidence}% OCR Conf
                        </span>
                      )}
                      <span>{file.chunks} chunks</span>
                    </div>
                  </div>

                  {file.type === 'pdf' && (
                    <button
                      onClick={() => handleOpenOcrInspector(file)}
                      title="Inspect OCR & Bounding Boxes"
                      className="p-1.5 rounded bg-[#201d1a] border border-[#3b3630] hover:border-[#d9825b] text-[#a09a90] hover:text-[#d9825b] transition-colors"
                    >
                      <Eye size={14} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* OCR Page Inspector Modal */}
      {selectedFileForOcr && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-150">
          <div className="clora-card max-w-4xl w-full max-h-[90vh] flex flex-col border border-[#3b3630] shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 border-b border-[#2e2a25] flex items-center justify-between bg-[#1b1917]">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#2a241e] border border-[#d9825b]/30 flex items-center justify-center text-[#d9825b]">
                  <Sparkles size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-[#f5f2ed] flex items-center gap-2">
                    <span>OCR Forensic Inspector: {selectedFileForOcr.name}</span>
                    {selectedFileForOcr.needsReview ? (
                      <span className="text-[10px] px-2 py-0.5 bg-[#3a1a16] text-[#ef4444] border border-[#5c241c] rounded font-mono font-bold">
                        REVIEW REQUIRED
                      </span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 bg-[#162a1c] text-[#10b981] border border-[#235c30] rounded font-mono font-bold">
                        VERIFIED & GROUNDED
                      </span>
                    )}
                  </h3>
                  <div className="text-[11px] text-[#6d675e] font-mono">
                    Method: {selectedFileForOcr.extractionMethod} • Skew: {selectedFileForOcr.skewAngle || '0.0°'} • Mean OCR Conf: {selectedFileForOcr.ocrConfidence}%
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedFileForOcr(null)}
                className="p-1.5 rounded-lg text-[#6d675e] hover:text-[#f5f2ed] hover:bg-[#201d1a] transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-4 flex-1">
              {/* Top Action / Controls Bar */}
              <div className="flex items-center justify-between bg-[#151312] p-3 rounded-xl border border-[#2e2a25]">
                <div className="flex items-center gap-3 text-xs">
                  <button
                    onClick={() => setShowBoundingBoxes(!showBoundingBoxes)}
                    className={`px-3 py-1 rounded-lg text-[11px] font-mono border flex items-center gap-1.5 transition-colors ${
                      showBoundingBoxes
                        ? 'bg-[#2a241e] border-[#d9825b] text-[#d9825b]'
                        : 'bg-[#1b1917] border-[#3b3630] text-[#6d675e]'
                    }`}
                  >
                    <Layers size={13} />
                    <span>OCR Word Boxes ({showBoundingBoxes ? 'ON' : 'OFF'})</span>
                  </button>

                  <span className="text-[11px] text-[#6d675e] font-mono">
                    Color legend: <span className="text-[#10b981]">■ &gt;80%</span> <span className="text-[#f59e0b]">■ 50-80%</span> <span className="text-[#ef4444]">■ &lt;50%</span>
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {selectedFileForOcr.needsReview && (
                    <button
                      onClick={handleApproveReview}
                      className="px-3 py-1.5 rounded-lg text-xs bg-[#162a1c] hover:bg-[#1f3f29] text-[#10b981] border border-[#235c30] flex items-center gap-1.5 font-medium transition-colors"
                    >
                      <Check size={14} />
                      <span>Approve Extraction (HITL Sign-Off)</span>
                    </button>
                  )}
                  <button
                    onClick={handleReprocess}
                    disabled={reprocessing}
                    className="btn-copper text-xs py-1.5 px-3 flex items-center gap-1.5"
                  >
                    <RefreshCw size={13} className={reprocessing ? 'animate-spin' : ''} />
                    <span>{reprocessing ? 'Deskewing & Re-OCR...' : 'Re-process (250 DPI + CLAHE)'}</span>
                  </button>
                </div>
              </div>

              {/* Inspection Grid: Left Page Canvas / Right Reconstructed Data */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Left: Visual Document Scan Representation */}
                <div className="clora-card p-4 space-y-2 bg-[#121110]">
                  <div className="text-[11px] font-mono text-[#a09a90] uppercase font-bold flex items-center justify-between">
                    <span>Preprocessed Raster Layer (Page 1)</span>
                    <span className="text-[#10b981] text-[10px]">200 DPI • Deskewed</span>
                  </div>

                  <div className="relative border border-[#3b3630] rounded-lg p-4 bg-[#1e1b18] text-[#f5f2ed] font-mono text-[11px] leading-relaxed shadow-inner overflow-hidden min-h-[260px]">
                    {/* Simulated Inspection Header */}
                    <div className="text-center pb-2 border-b border-[#3b3630]/60 mb-2">
                      <div className="font-bold text-[#d9825b] text-[11px]">MANGALORE REFINERY AND PETROCHEMICALS LIMITED</div>
                      <div className="text-[10px] text-[#a09a90]">PLANT TECHNICAL AUDIT & VIBRATION INSPECTION REPORT</div>
                    </div>

                    <div className="space-y-2 text-[10px]">
                      <div className="flex justify-between border-b border-[#2e2a25] pb-1">
                        <span className="text-[#6d675e]">Report No:</span>
                        <span className="text-[#f5f2ed]">MRPL/INSP/2026/CDU-042</span>
                      </div>
                      <div className="flex justify-between border-b border-[#2e2a25] pb-1">
                        <span className="text-[#6d675e]">Plant Unit:</span>
                        <span className="text-[#f5f2ed]">Crude Distillation Unit-1 (CDU-1)</span>
                      </div>
                      <div className="flex justify-between border-b border-[#2e2a25] pb-1">
                        <span className="text-[#6d675e]">Asset Tag:</span>
                        <span className="text-[#d9825b] font-bold">P-102A (Crude Charge Pump)</span>
                      </div>
                      <div className="pt-1">
                        <div className="text-[#a09a90] font-bold mb-1">Executive Findings:</div>
                        <p className="text-[#cbd5e1] text-[9.5px] leading-normal">
                          Severe abnormal vibration (7.8 mm/s RMS) and elevated DE bearing temperatures (104.2°C) detected. Threshold: 4.5 mm/s. Spectral analysis indicates inner-race spalling. Immediate overhaul recommended.
                        </p>
                      </div>
                    </div>

                    {/* Word Bounding Boxes Simulation Overlay */}
                    {showBoundingBoxes && (
                      <div className="absolute inset-0 pointer-events-none p-4">
                        <div className="absolute top-12 left-4 w-32 h-5 border border-[#10b981]/60 bg-[#10b981]/10 rounded-sm"></div>
                        <div className="absolute top-20 left-4 w-40 h-5 border border-[#10b981]/60 bg-[#10b981]/10 rounded-sm"></div>
                        <div className="absolute top-28 right-4 w-28 h-5 border border-[#f59e0b]/60 bg-[#f59e0b]/10 rounded-sm"></div>
                        <div className="absolute bottom-6 left-4 right-4 h-16 border border-[#10b981]/40 bg-[#10b981]/5 rounded-sm"></div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right: Reconstructed Tabular Data & Key-Value Pairs */}
                <div className="clora-card p-4 space-y-3 bg-[#121110]">
                  <div className="text-[11px] font-mono text-[#a09a90] uppercase font-bold flex items-center gap-1.5">
                    <TableIcon size={14} className="text-[#d9825b]" />
                    <span>Reconstructed 2D Table Grid</span>
                  </div>

                  <div className="border border-[#2e2a25] rounded-lg overflow-hidden font-mono text-[10px]">
                    <table className="w-full text-left">
                      <thead className="bg-[#1e1b18] text-[#d9825b] border-b border-[#2e2a25]">
                        <tr>
                          <th className="p-2">Tag</th>
                          <th className="p-2">Observed</th>
                          <th className="p-2">Limit</th>
                          <th className="p-2">Severity</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#26231f] text-[#cbd5e1]">
                        <tr className="bg-[#171513]">
                          <td className="p-2 font-bold text-[#f5f2ed]">P-102A</td>
                          <td className="p-2 text-[#ef4444]">7.8 mm/s</td>
                          <td className="p-2 text-[#6d675e]">4.5 mm/s</td>
                          <td className="p-2"><span className="px-1.5 py-0.5 rounded bg-[#3a1a16] text-[#ef4444] font-bold">CRITICAL</span></td>
                        </tr>
                        <tr>
                          <td className="p-2 font-bold text-[#f5f2ed]">P-102B</td>
                          <td className="p-2 text-[#10b981]">2.1 mm/s</td>
                          <td className="p-2 text-[#6d675e]">4.5 mm/s</td>
                          <td className="p-2"><span className="px-1.5 py-0.5 rounded bg-[#162a1c] text-[#10b981] font-bold">NORMAL</span></td>
                        </tr>
                        <tr className="bg-[#171513]">
                          <td className="p-2 font-bold text-[#f5f2ed]">E-104</td>
                          <td className="p-2 text-[#f59e0b]">ΔP 1.8 bar</td>
                          <td className="p-2 text-[#6d675e]">1.2 bar</td>
                          <td className="p-2"><span className="px-1.5 py-0.5 rounded bg-[#382d16] text-[#f59e0b] font-bold">WARNING</span></td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {/* Forensic Audit Log Info */}
                  <div className="p-3 rounded-lg bg-[#181614] border border-[#2e2a25] space-y-1 text-[10px] font-mono">
                    <div className="text-[#6d675e] flex justify-between">
                      <span>AUDIT LOG ACTION:</span>
                      <span className="text-[#10b981]">run_ocr (SHA-256 Chained)</span>
                    </div>
                    <div className="text-[#6d675e] flex justify-between">
                      <span>EGRESS POLICY:</span>
                      <span className="text-[#10b981]">0 Bytes (Air-Gapped Local Host)</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#2e2a25] bg-[#181614] flex items-center justify-between">
              <div className="text-xs text-[#6d675e] font-mono">
                Document SHA-256: {selectedFileForOcr.sha}
              </div>
              <button
                onClick={() => setSelectedFileForOcr(null)}
                className="btn-copper text-xs py-1.5 px-4"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
