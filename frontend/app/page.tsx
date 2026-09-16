"use client";

import React, { useState, useEffect, useRef } from "react";
import Image from "next/image";
import {
  FileText,
  Upload,
  Globe,
  Sparkles,
  Play,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Download,
  Copy,
  Edit3,
  Layers,
  ShieldCheck,
  Zap,
  Activity,
  ChevronRight,
  Code,
  Eye,
  Settings,
  Database,
  Search,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SourceInfo {
  id: string;
  filename: string;
  source_type: string;
  size_bytes: number;
  char_count: number;
  extract_preview: string;
}

interface DeliverableOption {
  id: string;
  label: string;
  description: string;
  icon: any;
}

const DELIVERABLE_TYPES: DeliverableOption[] = [
  {
    id: "executive_summary",
    label: "Executive Briefing",
    description: "High-level strategic briefing with headline, findings & implications",
    icon: FileText,
  },
  {
    id: "advisory",
    label: "Security Advisory",
    description: "Formal situation assessment, watch items, and actionable guidance",
    icon: ShieldCheck,
  },
  {
    id: "linkedin_post",
    label: "LinkedIn Brief",
    description: "Engaging professional social post with hooks and hashtag suite",
    icon: Globe,
  },
  {
    id: "presentation",
    label: "Presentation Outline",
    description: "Structured slide outline deck with speaker notes (PPTX exportable)",
    icon: Layers,
  },
  {
    id: "x_thread",
    label: "X / Twitter Thread",
    description: "Numbered tweet sequence summarizing core findings",
    icon: Zap,
  },
  {
    id: "infographic",
    label: "Infographic Spec",
    description: "Visual sections, data callouts, and chart suggestions",
    icon: Eye,
  },
  {
    id: "video_package",
    label: "Video Script Package",
    description: "Scene-by-scene narration, timing, and visual recommendations",
    icon: Play,
  },
];

const PIPELINE_NODES = [
  { id: "ingest", label: "Ingest & Store" },
  { id: "extract", label: "Extract Chunks" },
  { id: "analyze", label: "Canonical Knowledge" },
  { id: "structure_knowledge", label: "Fact Modeling" },
  { id: "plan_outputs", label: "Deliverable Planning" },
  { id: "fan_in", label: "Parallel Generation" },
  { id: "consistency_check", label: "Validation Audits" },
  { id: "finalize", label: "Finalize & Persist" },
];

export default function TransformAIDashboard() {
  // Ingestion state
  const [ingestTab, setIngestTab] = useState<"file" | "text" | "url">("text");
  const [rawText, setRawText] = useState<string>(
    "CYBERSECURITY INCIDENT ASSESSMENT\n\nIncident Title: Project Atlas Credential Exposure\nDate: 12 September 2026\n\nSummary:\nA fictional technology organization detected suspicious authentication activity involving its internal employee portal.\n\nInitial investigation identified 47 potentially affected user accounts. The activity was first observed on 10 September 2026 at approximately 03:20 UTC.\n\nThe investigation found repeated authentication attempts from an unfamiliar external network. Security analysts temporarily disabled the affected accounts and forced password resets.\n\nNo evidence currently confirms that sensitive databases were accessed. The investigation remains ongoing."
  );
  const [urlInput, setUrlInput] = useState<string>("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);
  const [source, setSource] = useState<SourceInfo | null>(null);

  // Configuration state
  const [selectedOutputs, setSelectedOutputs] = useState<string[]>([
    "executive_summary",
    "advisory",
    "linkedin_post",
    "presentation",
  ]);
  const [config, setConfig] = useState({
    audience: "senior decision makers",
    tone: "advisory",
    detail_level: "standard",
    objective: "inform and recommend",
    content_style: "intelligence brief",
  });

  // Job & LangGraph execution state
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [currentNode, setCurrentNode] = useState<string | null>(null);
  const [executing, setExecuting] = useState<boolean>(false);
  const [jobData, setJobData] = useState<any>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Deliverables viewing & editing state
  const [activeOutputTab, setActiveOutputTab] = useState<string>("executive_summary");
  const [viewMode, setViewMode] = useState<"rendered" | "raw" | "edit">("rendered");
  const [editText, setEditText] = useState<string>("");
  const [savingEdit, setSavingEdit] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  // Auto-fetch job details on node state changes
  useEffect(() => {
    if (!jobId) return;

    let interval: ReturnType<typeof setInterval>;

    const fetchJobDetails = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
        if (res.ok) {
          const data = await res.json();
          setJobData(data);
          setJobStatus(data.status);
          setCurrentNode(data.current_node);
          if (data.status === "completed" || data.status === "failed") {
            setExecuting(false);
            clearInterval(interval);
          }
        }
      } catch (err) {
        console.error("Failed to fetch job status", err);
      }
    };

    fetchJobDetails();
    interval = setInterval(fetchJobDetails, 1000);
    return () => clearInterval(interval);
  }, [jobId]);

  // Connect SSE for real-time progress updates
  useEffect(() => {
    if (!jobId || !executing) return;

    const eventSource = new EventSource(`${API_BASE}/api/jobs/${jobId}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.current_node) setCurrentNode(data.current_node);
        if (data.status) setJobStatus(data.status);
        if (data.status === "completed" || data.status === "failed") {
          setExecuting(false);
          eventSource.close();
        }
      } catch (e) {
        console.error("SSE parse error", e);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [jobId, executing]);

  // Handle Source Creation
  const handleIngest = async () => {
    setUploading(true);
    setErrorMessage(null);
    try {
      let res;
      if (ingestTab === "text") {
        res = await fetch(`${API_BASE}/api/sources/text`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: rawText, filename: "pasted_report.txt" }),
        });
      } else if (ingestTab === "url") {
        res = await fetch(`${API_BASE}/api/sources/url`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: urlInput }),
        });
      } else if (ingestTab === "file" && uploadFile) {
        const formData = new FormData();
        formData.append("file", uploadFile);
        res = await fetch(`${API_BASE}/api/sources/upload`, {
          method: "POST",
          body: formData,
        });
      }

      if (!res || !res.ok) {
        const err = await res?.json();
        throw new Error(err?.detail || "Source ingestion failed");
      }

      const data = await res.json();
      setSource(data);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to ingest source content");
    } finally {
      setUploading(false);
    }
  };

  // Start Transformation Job
  const handleStartPipeline = async () => {
    if (!source) {
      setErrorMessage("Please ingest a source first.");
      return;
    }
    if (selectedOutputs.length === 0) {
      setErrorMessage("Please select at least one deliverable type.");
      return;
    }

    setExecuting(true);
    setErrorMessage(null);

    try {
      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: source.id,
          selected_outputs: selectedOutputs,
          config: config,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create transformation job");
      }

      const data = await res.json();
      setJobId(data.id);
      setJobStatus(data.status);
      setCurrentNode("queued");
      setActiveOutputTab(selectedOutputs[0]);
    } catch (err: any) {
      setExecuting(false);
      setErrorMessage(err.message || "Failed to start transformation job");
    }
  };

  // Regenerate Job
  const handleRegenerate = async () => {
    if (!jobId) return;
    setExecuting(true);
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/regenerate`, {
        method: "POST",
      });
      if (res.ok) {
        setJobStatus("queued");
        setCurrentNode("queued");
      }
    } catch (err) {
      console.error("Regeneration failed", err);
    }
  };

  // Save Inline Edits
  const handleSaveEdit = async () => {
    const currentOutput = jobData?.outputs?.find(
      (o: any) => o.output_type === activeOutputTab
    );
    if (!currentOutput) return;

    setSavingEdit(true);
    try {
      const res = await fetch(`${API_BASE}/api/outputs/${currentOutput.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content_markdown: editText }),
      });
      if (res.ok) {
        const updated = await res.json();
        setJobData((prev: any) => ({
          ...prev,
          outputs: prev.outputs.map((o: any) =>
            o.id === updated.id ? { ...o, ...updated } : o
          ),
        }));
        setViewMode("rendered");
      }
    } catch (err) {
      console.error("Failed to save output edit", err);
    } finally {
      setSavingEdit(false);
    }
  };

  // Copy Markdown to Clipboard
  const handleCopyMarkdown = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Toggle Deliverable Selection
  const toggleDeliverable = (id: string) => {
    setSelectedOutputs((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  // Active Output deliverable object
  const activeOutput = jobData?.outputs?.find(
    (o: any) => o.output_type === activeOutputTab
  );

  return (
    <div className="min-h-screen flex flex-col bg-[#D8D0C5]">

      {/* Header Bar */}
      <header className="sticky top-5 w-[90%] mx-auto rounded-2xl mb-10 z-50 bg-[#3F0D0C] px-6 py-4 flex items-center justify-between shadow-lg">

        <div className="flex items-center space-x-3">

          {/* <div className="w-10 h-10 rounded-xl glow-button flex items-center justify-center text-white shadow-lg">
          <Sparkles className="w-5 h-5 animate-pulse" />
        </div> */}

          <div>
            <h1 className="text-xl font-bold tracking-tight text-white bg-clip-text">
              TransformAI
            </h1>

            <p className="text-xs text-[#D9C4A9]">
              Canonical Knowledge & Multi-Deliverable Engine
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">

          <div className="hidden md:flex items-center space-x-2 bg-[#3F0D0C] border border-[#8D6F57] px-3 py-1.5 rounded-lg text-xs">

            <Activity className="w-3.5 h-3.5 text-[#D9B061]" />

            <span className="text-[#D9C4A9]">
              Status:
            </span>

            <span className="font-semibold text-[#D9B061]">
              {jobStatus ? jobStatus.toUpperCase() : "READY"}
            </span>
          </div>

          {jobId && (
            <div className="text-xs font-mono bg-[#3F0D0C] border border-[#8D6F57] px-3 py-1.5 rounded-lg text-[#D9C4A9]">
              JOB: {jobId.slice(0, 8)}...
            </div>
          )}
        </div>
      </header>


      {/* Hero Section */}
      <div className="flex w-full h-96">

        {/* Left Content */}
        <section className="w-1/2 bg-[#D8D0C5]">

          <h1 className="text-4xl text-[#8D6F57] font-bold px-28 pt-16">

            AI-Powered

            <br />

            <span className="text-7xl text-[#D9B061]">
              Content
            </span>

            <br />

            <span className="text-[#3F0D0C]">
              Transformation Engine
            </span>

          </h1>

          <p className="px-28 pt-6 text-[#8D6F57]">
            Transform complex information into accurate, targeted and verified
            communications - from one source to many trusted formats.
          </p>

        </section>


        {/* Right Image */}
        <section className="relative w-1/2 h-full flex items-center justify-center">

          <Image
            src="/hero-image.png"
            alt="hero image"
            width={700}
            height={700}
            className="absolute w-190 h-auto left-[45%] top-[35%] object-contain -translate-x-1/2 -translate-y-1/2"
          />

        </section>

      </div>


      {/* Main Content Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-8">

        {/* Error Alert */}
        {errorMessage && (

          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 flex items-start space-x-3 text-red-700 text-sm">

            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />

            <div>
              <span className="font-semibold">
                Pipeline Error:
              </span>

              {" "}

              {errorMessage}

            </div>

          </div>

        )}


        {/* STEP 1 & STEP 2 GRID */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">


          {/* STEP 1: SOURCE INGESTION */}
          <section className="lg:col-span-6 bg-white rounded-2xl p-6 flex flex-col justify-between border border-[#D9C4A9] shadow-sm">

            <div>

              <div className="flex items-center space-x-3 mb-4">

                <div className="w-8 h-8 rounded-lg bg-[#D9C4A9] border border-[#D9B061] flex items-center justify-center text-[#3F0D0C]">

                  <Database className="w-4 h-4" />

                </div>


                <div>

                  <h2 className="text-lg font-semibold text-[#3F0D0C]">
                    Step 1: Source Ingestion
                  </h2>

                  <p className="text-xs text-[#8D6F57]">
                    Upload documents, paste raw text, or ingest web URLs
                  </p>

                </div>

              </div>


              {/* Ingestion Type Tabs */}
              <div className="flex border-b border-[#D9C4A9] mb-4 space-x-4">

                <button
                  onClick={() => setIngestTab("text")}
                  className={`pb-2 text-sm font-medium transition-colors border-b-2 ${ingestTab === "text"
                    ? "border-[#D9B061] text-[#3F0D0C]"
                    : "border-transparent text-[#8D6F57] hover:text-[#3F0D0C]"
                    }`}
                >
                  Raw Text
                </button>


                <button
                  onClick={() => setIngestTab("file")}
                  className={`pb-2 text-sm font-medium transition-colors border-b-2 ${ingestTab === "file"
                    ? "border-[#D9B061] text-[#3F0D0C]"
                    : "border-transparent text-[#8D6F57] hover:text-[#3F0D0C]"
                    }`}
                >
                  File Upload (PDF/TXT/DOCX)
                </button>


                <button
                  onClick={() => setIngestTab("url")}
                  className={`pb-2 text-sm font-medium transition-colors border-b-2 ${ingestTab === "url"
                    ? "border-[#D9B061] text-[#3F0D0C]"
                    : "border-transparent text-[#8D6F57] hover:text-[#3F0D0C]"
                    }`}
                >
                  URL Scraping
                </button>

              </div>


              {/* Ingestion Controls */}
              {ingestTab === "text" && (

                <textarea
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  rows={7}
                  placeholder="Paste report text here..."
                  className="w-full bg-[#D8D0C5] border border-[#D9C4A9] rounded-xl p-3 text-sm text-[#3F0D0C] focus:outline-none focus:border-[#D9B061] font-mono resize-none"
                />

              )}


              {ingestTab === "file" && (

                <div className="border-2 border-dashed border-[#D9C4A9] rounded-xl p-8 text-center hover:border-[#D9B061] transition-colors">

                  <Upload className="w-10 h-10 mx-auto text-[#8D6F57] mb-3" />


                  <input
                    type="file"
                    accept=".pdf,.txt,.docx"
                    onChange={(e) =>
                      setUploadFile(e.target.files?.[0] || null)
                    }
                    className="hidden"
                    id="file-upload-input"
                  />


                  <label
                    htmlFor="file-upload-input"
                    className="cursor-pointer text-sm text-[#3F0D0C] font-medium hover:underline"
                  >
                    Click to choose file
                  </label>


                  {uploadFile && (

                    <div className="mt-3 text-xs text-[#8D6F57] font-mono">

                      Selected: {uploadFile.name} (
                      {(uploadFile.size / 1024).toFixed(1)} KB)

                    </div>

                  )}

                </div>

              )}


              {ingestTab === "url" && (

                <div className="space-y-3">

                  <input
                    type="url"
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="https://example.com/intelligence-report"
                    className="w-full bg-white border border-[#D9C4A9] rounded-xl p-3 text-sm text-[#3F0D0C] focus:outline-none focus:border-[#D9B061]"
                  />


                  <p className="text-xs text-[#8D6F57]">
                    Trafilatura web extractor will parse clean article text and metadata.
                  </p>

                </div>

              )}

            </div>


            {/* Ingest Action Button & Active Source Card */}
            <div className="mt-6 space-y-4">

              <button
                onClick={handleIngest}
                disabled={uploading}
                className="w-full py-2.5 px-4 bg-[#3F0D0C] hover:bg-[#8D6F57] text-white font-medium rounded-xl border border-[#3F0D0C] transition-colors flex items-center justify-center space-x-2 text-sm disabled:opacity-50"
              >

                {uploading ? (

                  <>

                    <RefreshCw className="w-4 h-4 animate-spin text-[#D9B061]" />

                    <span>
                      Extracting Source...
                    </span>

                  </>

                ) : (

                  <>

                    <Database className="w-4 h-4 text-[#D9B061]" />

                    <span>
                      Ingest & Extract Source
                    </span>

                  </>

                )}

              </button>


              {source && (

                <div className="bg-[#D8D0C5] border border-[#D9B061] rounded-xl p-3 flex items-center justify-between text-xs">

                  <div className="flex items-center space-x-2">

                    <CheckCircle2 className="w-4 h-4 text-[#8D6F57] shrink-0" />

                    <div className="truncate">

                      <span className="font-semibold text-[#3F0D0C]">
                        {source.filename}
                      </span>

                      <span className="text-[#8D6F57] ml-2">

                        ({source.char_count} chars, {source.source_type})

                      </span>

                    </div>

                  </div>


                  <span className="font-mono text-[#3F0D0C] text-[10px] bg-[#D9C4A9] px-2 py-0.5 rounded">

                    ID: {source.id.slice(0, 8)}

                  </span>

                </div>

              )}

            </div>

          </section>



          {/* STEP 2: OUTPUT SELECTION & CONFIGURATION */}
          <section className="lg:col-span-6 bg-white rounded-2xl p-6 flex flex-col justify-between border border-[#D9C4A9] shadow-sm">

            <div>

              <div className="flex items-center space-x-3 mb-4">

                <div className="w-8 h-8 rounded-lg bg-[#D9C4A9] border border-[#D9B061] flex items-center justify-center text-[#3F0D0C]">

                  <Settings className="w-4 h-4" />

                </div>


                <div>

                  <h2 className="text-lg font-semibold text-[#3F0D0C]">
                    Step 2: Deliverables & Configuration
                  </h2>

                  <p className="text-xs text-[#8D6F57]">
                    Select target communication outputs and prompt style settings
                  </p>

                </div>

              </div>


              {/* Deliverable Checkboxes */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">

                {DELIVERABLE_TYPES.map((item) => {

                  const isSelected = selectedOutputs.includes(item.id);
                  const Icon = item.icon;

                  return (

                    <div
                      key={item.id}
                      onClick={() => toggleDeliverable(item.id)}
                      className={`cursor-pointer rounded-xl p-3 border transition-all flex items-start space-x-3 ${isSelected
                        ? "bg-[#D8D0C5] border-[#D9B061] shadow-md"
                        : "bg-white border-[#D9C4A9] hover:border-[#8D6F57]"
                        }`}
                    >

                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => { }}
                        className="mt-1 rounded text-[#3F0D0C] focus:ring-[#D9B061] bg-white border-[#8D6F57]"
                      />


                      <div>

                        <div className="flex items-center space-x-1.5">

                          <Icon className="w-3.5 h-3.5 text-[#8D6F57]" />

                          <h4 className="text-xs font-semibold text-[#3F0D0C]">
                            {item.label}
                          </h4>

                        </div>


                        <p className="text-[11px] text-[#8D6F57] mt-1 leading-tight">
                          {item.description}
                        </p>

                      </div>

                    </div>

                  );

                })}

              </div>


              {/* Config Form Options */}
              <div className="grid grid-cols-2 gap-3 text-xs">

                <div>

                  <label className="block text-[#8D6F57] mb-1">
                    Target Audience
                  </label>

                  <input
                    type="text"
                    value={config.audience}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        audience: e.target.value
                      })
                    }
                    className="w-full bg-white border border-[#D9C4A9] rounded-lg p-2 text-[#3F0D0C] focus:outline-none focus:border-[#D9B061]"
                  />

                </div>


                <div>

                  <label className="block text-[#8D6F57] mb-1">
                    Tone
                  </label>

                  <select
                    value={config.tone}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        tone: e.target.value
                      })
                    }
                    className="w-full bg-white border border-[#D9C4A9] rounded-lg p-2 text-[#3F0D0C] focus:outline-none focus:border-[#D9B061]"
                  >

                    <option value="advisory">
                      Advisory
                    </option>

                    <option value="formal">
                      Formal
                    </option>

                    <option value="urgent">
                      Urgent
                    </option>

                    <option value="public">
                      Public
                    </option>

                    <option value="neutral">
                      Neutral
                    </option>

                  </select>

                </div>

              </div>

            </div>


            {/* Execute Pipeline Primary CTA */}
            <div className="mt-6">

              <button
                onClick={handleStartPipeline}
                disabled={executing || !source}
                className="w-full py-3.5 px-6 bg-[#3F0D0C] hover:bg-[#8D6F57] text-white font-semibold rounded-xl transition-all flex items-center justify-center space-x-3 text-base shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
              >

                {executing ? (

                  <>

                    <RefreshCw className="w-5 h-5 animate-spin text-[#D9B061]" />

                    <span>
                      LangGraph Pipeline Running...
                    </span>

                  </>

                ) : (

                  <>

                    <Play className="w-5 h-5 fill-current text-[#D9B061]" />

                    <span>
                      Start Transformation Pipeline
                    </span>

                  </>

                )}

              </button>

            </div>

          </section>

        </div>

        {/* STEP 3: LIVE LANGGRAPH EXECUTION PIPELINE STEPPER */}
        <section className="rounded-2xl bg-white p-6 border border-[#D9C4A9] shadow-sm">

          <div className="flex items-center justify-between mb-4">

            <h3 className="text-sm font-semibold text-[#3F0D0C] flex items-center space-x-2">

              <Activity className="w-4 h-4 text-[#D9B061]" />

              <span>
                LangGraph Execution Pipeline Nodes
              </span>

            </h3>


            {currentNode && (

              <span className="text-xs font-mono bg-[#D8D0C5] border border-[#D9B061] text-[#3F0D0C] px-2.5 py-1 rounded-full">

                Node: {currentNode}

              </span>

            )}

          </div>


          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">

            {PIPELINE_NODES.map((node, index) => {

              const isActive = currentNode === node.id;

              const isPast =
                jobStatus === "completed" ||
                (
                  currentNode &&
                  PIPELINE_NODES.findIndex(
                    (n) => n.id === currentNode
                  ) > index
                );


              return (

                <div
                  key={node.id}
                  className={`p-3 rounded-xl border text-center transition-all flex flex-col items-center justify-center space-y-1.5 ${isActive
                      ? "border-[#D9B061] bg-[#D8D0C5] text-[#3F0D0C] shadow-lg"
                      : isPast
                        ? "bg-[#D9C4A9] border-[#8D6F57] text-[#3F0D0C]"
                        : "bg-white border-[#D9C4A9] text-[#8D6F57]"
                    }`}
                >

                  <span className="text-[10px] font-mono opacity-60">
                    0{index + 1}
                  </span>

                  <span className="text-xs font-medium leading-tight">
                    {node.label}
                  </span>


                  {isActive && (

                    <RefreshCw className="w-3 h-3 animate-spin text-[#D9B061]" />

                  )}


                  {isPast && (

                    <CheckCircle2 className="w-3 h-3 text-[#8D6F57]" />

                  )}

                </div>

              );

            })}

          </div>

        </section>



        {/* STEP 4 & STEP 5: RESULTS & VALIDATION DASHBOARD */}
        {jobData && jobData.outputs && jobData.outputs.length > 0 && (

          <section className="bg-white rounded-2xl p-6 border border-[#D9C4A9] space-y-6 shadow-sm">


            {/* Output Deliverable Selection Tabs */}
            <div className="flex flex-wrap items-center justify-between border-b border-[#D9C4A9] pb-4 gap-4">

              <div className="flex flex-wrap gap-2">

                {jobData.outputs.map((output: any) => {

                  const isActive =
                    activeOutputTab === output.output_type;

                  const isSuccess =
                    output.status === "succeeded" ||
                    output.status === "repaired";


                  return (

                    <button
                      key={output.id}
                      onClick={() => {

                        setActiveOutputTab(
                          output.output_type
                        );

                        setEditText(
                          output.content_markdown || ""
                        );

                      }}
                      className={`px-4 py-2 rounded-xl text-xs font-medium transition-all flex items-center space-x-2 ${isActive
                          ? "bg-[#3F0D0C] text-white shadow-lg"
                          : "bg-[#D8D0C5] border border-[#D9C4A9] text-[#8D6F57] hover:text-[#3F0D0C]"
                        }`}
                    >

                      <span className="capitalize">

                        {output.output_type.replace("_", " ")}

                      </span>


                      <span
                        className={`w-2 h-2 rounded-full ${isSuccess
                            ? "bg-[#D9B061]"
                            : "bg-red-400"
                          }`}
                      />

                    </button>

                  );

                })}

              </div>



              {/* View Mode Actions */}
              <div className="flex items-center space-x-2">


                <button
                  onClick={() => setViewMode("rendered")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${viewMode === "rendered"
                      ? "bg-[#3F0D0C] text-white"
                      : "text-[#8D6F57] hover:text-[#3F0D0C]"
                    }`}
                >
                  Preview
                </button>


                <button
                  onClick={() => setViewMode("raw")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${viewMode === "raw"
                      ? "bg-[#3F0D0C] text-white"
                      : "text-[#8D6F57] hover:text-[#3F0D0C]"
                    }`}
                >
                  Raw JSON
                </button>


                <button
                  onClick={() => {

                    setViewMode("edit");

                    setEditText(
                      activeOutput?.content_markdown || ""
                    );

                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${viewMode === "edit"
                      ? "bg-[#3F0D0C] text-white"
                      : "text-[#8D6F57] hover:text-[#3F0D0C]"
                    }`}
                >
                  Edit
                </button>

              </div>

            </div>



            {/* Selected Deliverable Details */}
            {activeOutput && (

              <div className="space-y-6">


                {/* Fact Keys Traceability Badges */}
                <div className="flex items-center justify-between text-xs">

                  <div className="flex items-center space-x-2">

                    <span className="text-[#8D6F57]">
                      Fact Keys Used:
                    </span>


                    {activeOutput.fact_keys_used &&
                      activeOutput.fact_keys_used.length > 0 ? (

                      activeOutput.fact_keys_used.map(
                        (key: string) => (

                          <span
                            key={key}
                            className="bg-[#D8D0C5] border border-[#D9B061] text-[#3F0D0C] px-2 py-0.5 rounded-md font-mono"
                          >
                            {key}
                          </span>

                        )
                      )

                    ) : (

                      <span className="text-[#8D6F57] italic">
                        None claimed
                      </span>

                    )}

                  </div>



                  <div className="flex items-center space-x-3">


                    {/* Copy Markdown Button */}
                    <button
                      onClick={() =>
                        handleCopyMarkdown(
                          activeOutput.content_markdown
                        )
                      }
                      className="px-3 py-1.5 bg-[#D8D0C5] hover:bg-[#D9C4A9] text-[#3F0D0C] border border-[#D9C4A9] rounded-lg text-xs flex items-center space-x-1.5 transition-colors"
                    >

                      <Copy className="w-3.5 h-3.5" />

                      <span>
                        {copied
                          ? "Copied!"
                          : "Copy Markdown"}
                      </span>

                    </button>



                    {/* PPTX Export Button for Presentation */}
                    {activeOutput.output_type === "presentation" && (

                      <a
                        href={`${API_BASE}/api/outputs/${activeOutput.id}/export/pptx`}
                        download
                        className="px-3 py-1.5 bg-[#3F0D0C] hover:bg-[#8D6F57] text-white rounded-lg text-xs flex items-center space-x-1.5 font-medium transition-colors shadow-md"
                      >

                        <Download className="w-3.5 h-3.5 text-[#D9B061]" />

                        <span>
                          Export PPTX Deck
                        </span>

                      </a>

                    )}

                  </div>

                </div>



                {/* View Content Panels */}
                {viewMode === "rendered" && (

                  <div className="bg-[#D8D0C5] border border-[#D9C4A9] rounded-xl p-6 text-[#3F0D0C] text-sm leading-relaxed font-sans whitespace-pre-wrap max-h-125 overflow-y-auto">

                    {activeOutput.content_markdown ||
                      "No markdown rendered."}

                  </div>

                )}



                {viewMode === "raw" && (

                  <pre className="bg-[#3F0D0C] border border-[#8D6F57] rounded-xl p-4 text-xs font-mono text-[#D9C4A9] max-h-125 overflow-y-auto">

                    {JSON.stringify(
                      activeOutput.content_json,
                      null,
                      2
                    )}

                  </pre>

                )}



                {viewMode === "edit" && (

                  <div className="space-y-3">

                    <textarea
                      value={editText}
                      onChange={(e) =>
                        setEditText(e.target.value)
                      }
                      rows={12}
                      className="w-full bg-[#D8D0C5] border border-[#D9C4A9] rounded-xl p-4 text-sm font-mono text-[#3F0D0C] focus:outline-none focus:border-[#D9B061]"
                    />


                    <div className="flex justify-end space-x-3">


                      <button
                        onClick={() =>
                          setViewMode("rendered")
                        }
                        className="px-4 py-2 bg-[#D8D0C5] text-[#3F0D0C] border border-[#D9C4A9] rounded-xl text-xs font-medium"
                      >
                        Cancel
                      </button>



                      <button
                        onClick={handleSaveEdit}
                        disabled={savingEdit}
                        className="px-4 py-2 bg-[#3F0D0C] hover:bg-[#8D6F57] text-white rounded-xl text-xs font-semibold flex items-center space-x-2"
                      >

                        {savingEdit && (

                          <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#D9B061]" />

                        )}

                        <span>
                          Save Inline Edit
                        </span>

                      </button>

                    </div>

                  </div>

                )}



                {/* VALIDATION HEALTH DASHBOARD */}
                {jobData.validations && (

                  <div className="border-t border-[#D9C4A9] pt-6">

                    <h4 className="text-xs font-semibold text-[#3F0D0C] uppercase tracking-wider mb-3 flex items-center space-x-2">

                      <ShieldCheck className="w-4 h-4 text-[#D9B061]" />

                      <span>
                        Validation Health Audits
                      </span>

                    </h4>


                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

                      {[
                        "consistency",
                        "grounding",
                        "quality"
                      ].map((checkType) => {

                        const reports =
                          jobData.validations.filter(
                            (v: any) =>
                              v.check_type === checkType &&
                              (
                                !v.output_id ||
                                v.output_id === activeOutput.id ||
                                v.details?.output_type ===
                                activeOutput.output_type
                              )
                          );


                        const allPassed =
                          reports.length > 0 &&
                          reports.every(
                            (r: any) => r.passed
                          );


                        return (

                          <div
                            key={checkType}
                            className="bg-[#D8D0C5] border border-[#D9C4A9] rounded-xl p-4 flex flex-col justify-between"
                          >

                            <div className="flex items-center justify-between mb-2">

                              <span className="text-xs font-semibold capitalize text-[#3F0D0C]">

                                {checkType} Check

                              </span>


                              {allPassed ? (

                                <span className="bg-[#D9C4A9] border border-[#D9B061] text-[#3F0D0C] text-[10px] px-2 py-0.5 rounded-full font-semibold">

                                  PASSED

                                </span>

                              ) : (

                                <span className="bg-[#3F0D0C] border border-[#8D6F57] text-[#D9B061] text-[10px] px-2 py-0.5 rounded-full font-semibold">

                                  WARNING

                                </span>

                              )}

                            </div>


                            <p className="text-[11px] text-[#8D6F57]">

                              {checkType === "consistency" &&
                                "Fact conflict verification"}

                              {checkType === "grounding" &&
                                "Canonical source traceability"}

                              {checkType === "quality" &&
                                "Payload structure validation"}

                            </p>

                          </div>

                        );

                      })}

                    </div>

                  </div>

                )}

              </div>

            )}



            {/* Regeneration Action */}
            <div className="flex justify-end pt-4">

              <button
                onClick={handleRegenerate}
                className="px-4 py-2 bg-[#3F0D0C] hover:bg-[#8D6F57] border border-[#3F0D0C] text-white rounded-xl text-xs font-medium flex items-center space-x-2 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5 text-[#D9B061]" />
                <span>
                  Regenerate All Deliverables
                </span>
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
