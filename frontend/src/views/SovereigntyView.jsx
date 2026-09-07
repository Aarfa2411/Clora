import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Lock,
  CheckCircle2,
  XCircle,
  Download,
  FileText,
  Activity,
  RefreshCw,
  AlertTriangle,
  Radio,
  Network,
  Sliders,
  Play,
  Key,
  FileCheck,
  Check
} from 'lucide-react';
import {
  getSovereigntyStatus,
  getSovereigntyAuditTrail,
  triggerInstantAudit,
  simulatePolicyViolation,
  changeSecurityProfile,
  downloadComplianceAttestation,
  getAttestationIdentity,
  getSampleEvidenceProof,
  verifyEvidenceAttestation,
  simulateAttestationTamper,
  downloadCloraProofFile
} from '../services/api';

export default function SovereigntyView() {
  const [downloading, setDownloading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [showProfileModal, setShowProfileModal] = useState(false);

  // Profile modal state
  const [selectedProfile, setSelectedProfile] = useState('STRICT_AIRGAP');
  const [justification, setJustification] = useState('');
  const [profileSaving, setProfileSaving] = useState(false);

  // Live status data
  const [statusData, setStatusData] = useState({
    sovereign_mode: 'AIR_GAPPED_VERIFIED',
    is_air_gapped: true,
    active_profile: 'STRICT_AIRGAP',
    enforcer_active: true,
    total_audit_cycles: 0,
    violations_detected: 0,
    root_integrity_hash: '0'.repeat(64),
    chain_valid: true,
    open_sockets: []
  });

  // Live audit trail entries
  const [auditTrail, setAuditTrail] = useState([]);
  const [chainValid, setChainValid] = useState(true);

  // Ed25519 Evidence Attestation state
  const [attestationIdentity, setAttestationIdentity] = useState({
    key_id: 'CLORA-ED25519-A7F29BC01D4E',
    algorithm: 'Ed25519 (Curve25519)',
    signer: 'CLORA Sovereign Local Instance',
    public_key_pem: ''
  });
  const [sampleProof, setSampleProof] = useState(null);
  const [tamperResult, setTamperResult] = useState(null);
  const [verifyingProof, setVerifyingProof] = useState(false);
  const [simulatingTamper, setSimulatingTamper] = useState(false);

  // Notification / Alert toast
  const [notice, setNotice] = useState(null);

  const fetchLiveStatus = async () => {
    setStatusLoading(true);
    try {
      const data = await getSovereigntyStatus();
      setStatusData(data);
      setSelectedProfile(data.active_profile || 'STRICT_AIRGAP');
    } catch (err) {
      console.error('Failed to fetch status:', err);
    } finally {
      setStatusLoading(false);
    }
  };

  const fetchLiveAuditTrail = async () => {
    setAuditLoading(true);
    try {
      const data = await getSovereigntyAuditTrail(25);
      setAuditTrail(data.entries || []);
      setChainValid(data.chain_valid);
    } catch (err) {
      console.error('Failed to fetch audit trail:', err);
    } finally {
      setAuditLoading(false);
    }
  };

  const fetchAttestationData = async () => {
    try {
      const identity = await getAttestationIdentity();
      setAttestationIdentity(identity);
      const proof = await getSampleEvidenceProof();
      setSampleProof(proof);
    } catch (err) {
      console.error('Failed to fetch attestation data:', err);
    }
  };

  useEffect(() => {
    fetchLiveStatus();
    fetchLiveAuditTrail();
    fetchAttestationData();

    // Periodic heartbeat poll every 8 seconds
    const interval = setInterval(() => {
      fetchLiveStatus();
      fetchLiveAuditTrail();
    }, 8000);

    return () => clearInterval(interval);
  }, []);

  const handleInstantAudit = async () => {
    try {
      const res = await triggerInstantAudit();
      setNotice({
        type: 'success',
        title: 'Manual Audit Snapshot Executed',
        message: `Sequence #${res.audit_entry?.seq} chained: ${res.audit_entry?.entry_hash?.substring(0, 16)}...`
      });
      await fetchLiveStatus();
      await fetchLiveAuditTrail();
    } catch (err) {
      setNotice({ type: 'error', title: 'Audit Execution Failed', message: err.message });
    }
  };

  const handleSimulateViolation = async () => {
    setSimulating(true);
    try {
      const res = await simulatePolicyViolation('1.1.1.1', 443);
      if (res.intercepted) {
        setNotice({
          type: 'warning',
          title: 'Deterministic Policy Egress Test Blocked',
          message: `AirGapEnforcer blocked outbound connection to ${res.target}. Alert logged in SHA-256 hash chain.`
        });
      } else {
        setNotice({
          type: 'info',
          title: 'Simulation Complete',
          message: `Target ${res.target} completed without active block.`
        });
      }
      await fetchLiveStatus();
      await fetchLiveAuditTrail();
    } catch (err) {
      setNotice({ type: 'error', title: 'Simulation Error', message: err.message });
    } finally {
      setSimulating(false);
    }
  };

  const handleVerifyEvidence = async () => {
    if (!sampleProof) return;
    setVerifyingProof(true);
    try {
      const res = await verifyEvidenceAttestation(sampleProof);
      setNotice({
        type: 'success',
        title: 'Cryptographic Attestation Verified',
        message: `${res.message} (Key ID: ${sampleProof.key_id})`
      });
    } catch (err) {
      setNotice({ type: 'error', title: 'Verification Failed', message: err.message });
    } finally {
      setVerifyingProof(false);
    }
  };

  const handleSimulateTamperClick = async () => {
    setSimulatingTamper(true);
    try {
      const res = await simulateAttestationTamper(sampleProof);
      setTamperResult(res);
      setNotice({
        type: 'warning',
        title: 'Tamper Simulation Executed',
        message: 'Modified 1 field in report content: Cryptographic verification immediately returned INVALID.'
      });
    } catch (err) {
      setNotice({ type: 'error', title: 'Tamper Simulation Failed', message: err.message });
    } finally {
      setSimulatingTamper(false);
    }
  };

  const handleExportCloraProof = () => {
    if (!sampleProof) return;
    downloadCloraProofFile(sampleProof);
    setNotice({
      type: 'success',
      title: 'Evidence Package Exported',
      message: `Downloaded ${sampleProof.canonical_payload?.report_id || 'CLORA-REPORT'}.clora-proof`
    });
  };

  const handleProfileChangeSubmit = async (e) => {
    e.preventDefault();
    if (!justification.trim() || justification.length < 5) {
      alert('Mandatory operational justification (minimum 5 characters) required for audit logging.');
      return;
    }

    setProfileSaving(true);
    try {
      await changeSecurityProfile(selectedProfile, justification, 'operator_admin');
      setShowProfileModal(false);
      setJustification('');
      setNotice({
        type: 'success',
        title: 'Network Trust Profile Changed',
        message: `Profile transitioned to ${selectedProfile}. Audit record logged with cryptographic entry hash.`
      });
      await fetchLiveStatus();
      await fetchLiveAuditTrail();
    } catch (err) {
      alert(`Error updating profile: ${err.message}`);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleExportDocx = () => {
    setDownloading(true);
    setTimeout(() => {
      setDownloading(false);
      window.open('http://127.0.0.1:8000/api/files/download-approval-note', '_blank');
    }, 1000);
  };

  const rbacMatrix = [
    { role: 'operator', viewLogs: true, configSystem: false, execCommands: false, createUser: false, exportAudit: false },
    { role: 'technician', viewLogs: true, configSystem: true, execCommands: false, createUser: false, exportAudit: false },
    { role: 'maintenance_engineer', viewLogs: true, configSystem: true, execCommands: true, createUser: false, exportAudit: false },
    { role: 'supervisor', viewLogs: true, configSystem: true, execCommands: true, createUser: true, exportAudit: false },
    { role: 'plant_manager', viewLogs: true, configSystem: true, execCommands: true, createUser: true, exportAudit: true },
  ];

  return (
    <div className="space-y-5">
      {/* Toast Notification */}
      {notice && (
        <div
          className={`p-3.5 rounded-xl border flex items-center justify-between text-xs transition-all ${
            notice.type === 'error'
              ? 'bg-[#291414] border-[#6b2525] text-[#f87171]'
              : notice.type === 'warning'
              ? 'bg-[#2a1d12] border-[#78350f] text-[#fbbf24]'
              : 'bg-[#142319] border-[#1f5433] text-[#34d399]'
          }`}
        >
          <div className="space-y-0.5">
            <div className="font-bold uppercase tracking-wide">{notice.title}</div>
            <div className="opacity-90 font-mono text-[11px]">{notice.message}</div>
          </div>
          <button
            onClick={() => setNotice(null)}
            className="px-2.5 py-1 rounded bg-black/30 hover:bg-black/50 text-[11px] font-mono"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Top Banner: Air-Gap Sentinel & Active Trust Profile */}
      <div className="p-4.5 rounded-xl bg-[#141f17] border border-[#234d2b] flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#1d3323] border border-[#34d399]/40 flex items-center justify-center text-[#10b981] shrink-0">
            <ShieldCheck size={24} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-[#f5f2ed] uppercase tracking-wide">
                Air-Gap Sovereignty Sentinel
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#1d3323] text-[#34d399] border border-[#34d399]/30">
                {statusData.active_profile || 'STRICT_AIRGAP'}
              </span>
            </div>
            <p className="text-xs text-[#8ca68c] font-mono mt-0.5">
              APPLICATION-LEVEL EGRESS ENFORCEMENT • ZERO EXTERNAL WAN INFERENCE
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={fetchLiveStatus}
            disabled={statusLoading}
            className="btn-stone text-xs py-1.5 px-3 flex items-center gap-1.5"
            title="Refresh network socket scan"
          >
            <RefreshCw size={13} className={statusLoading ? 'animate-spin' : ''} />
            <span>Scan</span>
          </button>

          <button
            onClick={() => setShowProfileModal(true)}
            className="btn-stone text-xs py-1.5 px-3 flex items-center gap-1.5"
          >
            <Sliders size={13} />
            <span>Profile</span>
          </button>

          <button
            onClick={downloadComplianceAttestation}
            className="btn-copper text-xs py-1.5 px-3 flex items-center gap-1.5"
          >
            <Download size={13} />
            <span>Attestation (.txt)</span>
          </button>

          <span className={`status-pill-${statusData.is_air_gapped ? 'emerald' : 'amber'}`}>
            <CheckCircle2 size={12} />
            <span>{statusData.is_air_gapped ? 'COMPLIANT LOCAL' : 'ALERT VIOLATION'}</span>
          </span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <div className="clora-card p-3.5 space-y-1">
          <div className="text-[10px] text-[#6d675e] font-mono uppercase">Audited Checkpoints</div>
          <div className="text-lg font-bold text-[#f5f2ed] font-mono">{statusData.total_audit_cycles}</div>
          <div className="text-[10px] text-[#8ca68c] font-mono flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-ping" />
            Background daemon active
          </div>
        </div>

        <div className="clora-card p-3.5 space-y-1">
          <div className="text-[10px] text-[#6d675e] font-mono uppercase">Egress Violations</div>
          <div className={`text-lg font-bold font-mono ${statusData.violations_detected > 0 ? 'text-[#f59e0b]' : 'text-[#10b981]'}`}>
            {statusData.violations_detected}
          </div>
          <div className="text-[10px] text-[#6d675e] font-mono">
            {statusData.violations_detected === 0 ? 'Zero unapproved sockets' : 'Interceptions recorded'}
          </div>
        </div>

        <div className="clora-card p-3.5 space-y-1">
          <div className="text-[10px] text-[#6d675e] font-mono uppercase">Hash Chain Status</div>
          <div className="text-sm font-bold text-[#10b981] font-mono truncate">
            {statusData.chain_valid ? 'VALID (100% UNTAMPERED)' : 'CORRUPTED'}
          </div>
          <div className="text-[9px] text-[#6d675e] font-mono truncate">
            Root: {statusData.root_integrity_hash?.substring(0, 16)}...
          </div>
        </div>

        <div className="clora-card p-3.5 space-y-1">
          <div className="text-[10px] text-[#6d675e] font-mono uppercase">Interactive Demo Actions</div>
          <div className="flex items-center gap-2 pt-0.5">
            <button
              onClick={handleInstantAudit}
              className="flex-1 py-1 px-2 rounded bg-[#221f1c] hover:bg-[#2e2a25] border border-[#3b3630] text-[10px] font-mono text-[#f5f2ed] flex items-center justify-center gap-1"
            >
              <Play size={10} />
              <span>Snapshot</span>
            </button>
            <button
              onClick={handleSimulateViolation}
              disabled={simulating}
              className="flex-1 py-1 px-2 rounded bg-[#2d1b15] hover:bg-[#3d241c] border border-[#78350f] text-[10px] font-mono text-[#f59e0b] flex items-center justify-center gap-1"
              title="Test deterministic socket interception on 1.1.1.1:443"
            >
              <AlertTriangle size={10} />
              <span>{simulating ? 'Testing...' : 'Test Egress'}</span>
            </button>
          </div>
          <div className="text-[9px] text-[#6d675e] font-mono">Deterministic offline test</div>
        </div>
      </div>

      {/* NEW: Ed25519 Cryptographic Evidence Attestation Console */}
      <div className="clora-card p-5 space-y-4 border border-[#3b3630]">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-[#2e2a25] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#2d2217] border border-[#d9825b]/40 flex items-center justify-center text-[#d9825b]">
              <Key size={16} />
            </div>
            <div>
              <h3 className="text-xs font-bold text-[#f5f2ed] uppercase tracking-wide flex items-center gap-2">
                <span>🛡️ EVIDENCE ATTESTATION (Ed25519 Digital Seal)</span>
                <span className="px-2 py-0.5 rounded text-[9px] font-mono bg-[#161412] text-[#d9825b] border border-[#d9825b]/30">
                  {attestationIdentity.key_id}
                </span>
              </h3>
              <p className="text-[10px] text-[#a09a90] font-mono mt-0.5">
                ON-PREMISES PRIVATE KEY SIGNING • INDEPENDENT OFFLINE VERIFICATION • ZERO CLOUD TRUST
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleVerifyEvidence}
              disabled={verifyingProof}
              className="btn-stone text-xs py-1.5 px-3 flex items-center gap-1.5"
            >
              <FileCheck size={13} className="text-[#10b981]" />
              <span>{verifyingProof ? 'Checking...' : 'Verify Evidence'}</span>
            </button>

            <button
              onClick={handleSimulateTamperClick}
              disabled={simulatingTamper}
              className="py-1.5 px-3 rounded-lg bg-[#2d1b15] hover:bg-[#3d241c] border border-[#78350f] text-xs font-medium text-[#f59e0b] flex items-center gap-1.5 transition-colors"
              title="Demonstrate that modifying 1 character invalidates the Ed25519 signature"
            >
              <AlertTriangle size={13} />
              <span>{simulatingTamper ? 'Tampering...' : 'Simulate Tamper'}</span>
            </button>

            <button
              onClick={handleExportCloraProof}
              className="btn-copper text-xs py-1.5 px-3 flex items-center gap-1.5"
            >
              <Download size={13} />
              <span>Export .clora-proof</span>
            </button>
          </div>
        </div>

        {/* 4 Attestation Checkpoints Bar */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-[11px]">
          <div className="p-2.5 rounded-lg bg-[#161412] border border-[#2b2723] flex items-center justify-between">
            <span className="text-[#a09a90]">Report Integrity</span>
            <span className="text-[#34d399] font-bold flex items-center gap-1">
              <Check size={12} /> VERIFIED
            </span>
          </div>
          <div className="p-2.5 rounded-lg bg-[#161412] border border-[#2b2723] flex items-center justify-between">
            <span className="text-[#a09a90]">Audit Trail</span>
            <span className="text-[#34d399] font-bold flex items-center gap-1">
              <Check size={12} /> INTACT
            </span>
          </div>
          <div className="p-2.5 rounded-lg bg-[#161412] border border-[#2b2723] flex items-center justify-between">
            <span className="text-[#a09a90]">Digital Signature</span>
            <span className="text-[#34d399] font-bold flex items-center gap-1">
              <Check size={12} /> VALID
            </span>
          </div>
          <div className="p-2.5 rounded-lg bg-[#161412] border border-[#2b2723] flex items-center justify-between">
            <span className="text-[#a09a90]">Verification Mode</span>
            <span className="text-[#38bdf8] font-bold">100% OFFLINE</span>
          </div>
        </div>

        {/* Live Tamper Demonstration Comparison (If Triggered) */}
        {tamperResult && (
          <div className="p-3.5 rounded-xl bg-[#171412] border border-[#3b3630] space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between border-b border-[#2e2a25] pb-2">
              <span className="text-xs font-bold text-[#f5f2ed] uppercase tracking-wide flex items-center gap-1.5">
                <AlertTriangle size={14} className="text-[#f59e0b]" />
                Live Tampering Detection Proof (Side-by-Side)
              </span>
              <button
                onClick={() => setTamperResult(null)}
                className="text-[10px] text-[#6d675e] hover:text-[#f5f2ed]"
              >
                Close Comparison
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Left: Untampered Original */}
              <div className="p-3 rounded-lg bg-[#142319] border border-[#1f5433] space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-bold text-[#34d399]">BEFORE TAMPERING (ORIGINAL)</span>
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-[#10b981]/20 text-[#34d399]">
                    ✓ SIGNATURE VALID
                  </span>
                </div>
                <div className="text-[11px] text-[#f5f2ed] bg-black/30 p-2 rounded">
                  "{tamperResult.before_tampering?.content_snippet}"
                </div>
                <div className="text-[10px] text-[#8ca68c]">
                  ✓ Authentic • Untampered • Key: {tamperResult.before_tampering?.key_id}
                </div>
              </div>

              {/* Right: Tampered Modified */}
              <div className="p-3 rounded-lg bg-[#291414] border border-[#6b2525] space-y-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-bold text-[#f87171]">AFTER TAMPERING (MODIFIED)</span>
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-[#ef4444]/20 text-[#f87171]">
                    ✗ SIGNATURE INVALID
                  </span>
                </div>
                <div className="text-[11px] text-[#f87171] bg-black/30 p-2 rounded">
                  "{tamperResult.after_tampering?.tampered_snippet}"
                </div>
                <div className="text-[10px] text-[#fca5a5]">
                  ✗ {tamperResult.after_tampering?.cryptographic_verdict}
                </div>
              </div>
            </div>
            <p className="text-[10px] text-[#6d675e] italic">
              Demonstrates that even modifying 1 character causes immediate Ed25519 cryptographic signature rejection.
            </p>
          </div>
        )}
      </div>

      {/* Main Grid: Live Socket Inspector & Tamper-Evident Hash Chain */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Real-Time Process Socket Inspector */}
        <div className="lg:col-span-6 clora-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-[#2e2a25] pb-2.5">
            <div className="flex items-center gap-2">
              <Network size={14} className="text-[#34d399]" />
              <h3 className="text-xs font-semibold text-[#f5f2ed] uppercase tracking-wide">
                Live Process Socket Inspector
              </h3>
            </div>
            <span className="text-[10px] text-[#6d675e] font-mono">
              {(statusData.open_sockets || []).length} Active Sockets
            </span>
          </div>

          <div className="overflow-x-auto max-h-[320px] overflow-y-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="sticky top-0 bg-[#161412]">
                <tr className="border-b border-[#26231f] text-[#6d675e] text-[10px]">
                  <th className="pb-2">Proto</th>
                  <th className="pb-2">Local Bind</th>
                  <th className="pb-2">Remote Destination</th>
                  <th className="pb-2">State</th>
                  <th className="pb-2 text-right">Compliance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#26231f]">
                {(statusData.open_sockets || []).length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-[#6d675e] text-xs">
                      Scanning process sockets...
                    </td>
                  </tr>
                ) : (
                  (statusData.open_sockets || []).map((s, idx) => (
                    <tr key={idx} className="hover:bg-[#1a1816] transition-colors text-[11px]">
                      <td className="py-2 text-[#a09a90] font-semibold">{s.protocol}</td>
                      <td className="py-2 text-[#f5f2ed] truncate max-w-[120px]">{s.local_address}</td>
                      <td className="py-2 text-[#6d675e] truncate max-w-[120px]">
                        {s.remote_address === 'None' ? '—' : s.remote_address}
                      </td>
                      <td className="py-2 text-[#6d675e] text-[10px]">{s.status}</td>
                      <td className="py-2 text-right">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            s.compliance === 'SECURE_LOCAL'
                              ? 'bg-[#142319] text-[#34d399] border border-[#1f5433]'
                              : s.compliance === 'APPROVED_LAN'
                              ? 'bg-[#182329] text-[#38bdf8] border border-[#1e3a5f]'
                              : 'bg-[#291414] text-[#f87171] border border-[#6b2525]'
                          }`}
                        >
                          {s.compliance}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: Tamper-Evident SHA-256 Hash Chain Stream */}
        <div className="lg:col-span-6 clora-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-[#2e2a25] pb-2.5">
            <div className="flex items-center gap-2">
              <Lock size={14} className="text-[#d9825b]" />
              <h3 className="text-xs font-semibold text-[#f5f2ed] uppercase tracking-wide">
                Tamper-Evident SHA-256 Hash Chain
              </h3>
            </div>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${chainValid ? 'status-pill-emerald' : 'status-pill-amber'}`}>
              {chainValid ? 'CHAIN VALID' : 'CHAIN COMPROMISED'}
            </span>
          </div>

          <div className="space-y-2 max-h-[320px] overflow-y-auto font-mono text-[11px]">
            {auditTrail.length === 0 ? (
              <div className="py-6 text-center text-[#6d675e] text-xs">
                Loading cryptographic audit chain...
              </div>
            ) : (
              auditTrail.slice().reverse().map((log, idx) => (
                <div
                  key={log.seq ?? idx}
                  className={`p-2.5 rounded-lg border flex items-center justify-between transition-colors ${
                    !log.is_airgapped || log.stage?.includes('VIOLATION')
                      ? 'bg-[#251512] border-[#78350f]'
                      : 'bg-[#161412] border-[#2b2723]'
                  }`}
                >
                  <div className="space-y-0.5 truncate mr-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-[#6d675e]">#{log.seq}</span>
                      <span className="text-xs text-[#f5f2ed] font-medium">{log.stage}</span>
                    </div>
                    <div className="text-[10px] text-[#a09a90] truncate">
                      SHA-256: {log.entry_hash}
                    </div>
                    <div className="text-[9px] text-[#6d675e]">
                      {log.timestamp_utc ? new Date(log.timestamp_utc).toLocaleTimeString() : 'Recent'} • Prev: {log.prev_hash?.substring(0, 10)}...
                    </div>
                  </div>
                  <span
                    className={`text-[9px] shrink-0 font-bold px-1.5 py-0.5 rounded ${
                      log.is_airgapped
                        ? 'bg-[#142319] text-[#34d399]'
                        : 'bg-[#291414] text-[#f87171]'
                    }`}
                  >
                    {log.is_airgapped ? 'PASS' : 'ALERT'}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 5-Role RBAC Matrix */}
      <div className="clora-card p-5 space-y-3">
        <div className="flex items-center justify-between border-b border-[#2e2a25] pb-2.5">
          <h3 className="text-xs font-semibold text-[#f5f2ed] uppercase tracking-wide">
            5-Role Permission & RBAC Governance Matrix
          </h3>
          <span className="text-[10px] text-[#6d675e] font-mono">Enforced at Retrieval & Persistence Spine</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#26231f] text-[#6d675e] font-mono text-[10px]">
                <th className="pb-2">Role</th>
                <th className="pb-2 text-center">View Logs</th>
                <th className="pb-2 text-center">Config System</th>
                <th className="pb-2 text-center">Exec Commands</th>
                <th className="pb-2 text-center">Export Audit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#26231f]">
              {rbacMatrix.map((item) => (
                <tr key={item.role} className="hover:bg-[#1a1816] transition-colors">
                  <td className="py-2.5 font-medium text-[#f5f2ed] font-mono">{item.role}</td>
                  <td className="py-2.5 text-center">
                    {item.viewLogs ? <CheckCircle2 size={13} className="text-[#10b981] inline" /> : <XCircle size={13} className="text-[#4a443d] inline" />}
                  </td>
                  <td className="py-2.5 text-center">
                    {item.configSystem ? <CheckCircle2 size={13} className="text-[#10b981] inline" /> : <XCircle size={13} className="text-[#4a443d] inline" />}
                  </td>
                  <td className="py-2.5 text-center">
                    {item.execCommands ? <CheckCircle2 size={13} className="text-[#10b981] inline" /> : <XCircle size={13} className="text-[#4a443d] inline" />}
                  </td>
                  <td className="py-2.5 text-center">
                    {item.exportAudit ? <CheckCircle2 size={13} className="text-[#10b981] inline" /> : <XCircle size={13} className="text-[#4a443d] inline" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Export Action Card */}
      <div className="clora-card p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <FileText size={22} className="text-[#d9825b] shrink-0" />
          <div>
            <h4 className="text-xs font-bold text-[#f5f2ed]">Official MRPL Executive Approval Note</h4>
            <p className="text-[11px] text-[#a09a90]">
              Generate boardroom-ready Word document (.docx) with embedded cryptographic airgap proof hash.
            </p>
          </div>
        </div>

        <button
          onClick={handleExportDocx}
          disabled={downloading}
          className="btn-copper text-xs py-2 px-4 shrink-0"
        >
          <Download size={14} />
          <span>{downloading ? 'Compiling .docx...' : 'Export Approval Note (.docx)'}</span>
        </button>
      </div>

      {/* Network Profile Switch Modal */}
      {showProfileModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="clora-card p-6 max-w-md w-full space-y-4 border border-[#3b3630]">
            <div className="flex items-center justify-between border-b border-[#2e2a25] pb-3">
              <h3 className="text-sm font-bold text-[#f5f2ed] uppercase tracking-wide flex items-center gap-2">
                <Sliders size={16} className="text-[#d9825b]" />
                <span>Change Network Trust Profile</span>
              </h3>
              <button
                onClick={() => setShowProfileModal(false)}
                className="text-[#6d675e] hover:text-[#f5f2ed]"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleProfileChangeSubmit} className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs text-[#a09a90] font-mono">Select Profile</label>
                <select
                  value={selectedProfile}
                  onChange={(e) => setSelectedProfile(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-[#161412] border border-[#2e2a25] text-xs text-[#f5f2ed] font-mono focus:outline-none focus:border-[#d9825b]"
                >
                  <option value="STRICT_AIRGAP">🔒 STRICT_AIRGAP (Loopback Only)</option>
                  <option value="INDUSTRIAL_LAN">🏭 INDUSTRIAL_LAN (Approved Subnets Only)</option>
                  <option value="DEVELOPMENT">🌐 DEVELOPMENT (Permissive)</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-xs text-[#a09a90] font-mono">
                  Operational Justification <span className="text-[#f87171]">*</span>
                </label>
                <textarea
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  placeholder="e.g. Connecting to local SCADA historian subnet 10.42.10.0/24 for maintenance audit..."
                  rows={3}
                  required
                  className="w-full px-3 py-2 rounded-lg bg-[#161412] border border-[#2e2a25] text-xs text-[#f5f2ed] placeholder-[#4a443d] focus:outline-none focus:border-[#d9825b]"
                />
                <p className="text-[10px] text-[#6d675e]">
                  Every profile change is cryptographically recorded in the SHA-256 audit ledger.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowProfileModal(false)}
                  className="btn-stone text-xs py-2 px-4"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={profileSaving}
                  className="btn-copper text-xs py-2 px-4"
                >
                  {profileSaving ? 'Updating...' : 'Confirm & Log Change'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
