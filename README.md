<div align="center">

# ⚡ TransformAI

### Turn one source into an entire communication package.

**TransformAI is a multi-deliverable AI knowledge transformation engine that ingests source material, builds canonical knowledge, and transforms it into multiple audience-ready deliverables through a LangGraph-powered workflow.**

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C3C3C?style=for-the-badge)](https://www.langchain.com/langgraph)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)

<br/>

**🚀 One Source → 🧠 Canonical Knowledge → ⚙️ AI Transformation → 📦 Multiple Deliverables**

<br/>

[Features](#-what-is-transformai) •
[Architecture](#-architecture) •
[Deliverables](#-deliverables) •
[Tech Stack](#-tech-stack) •
[Setup](#-getting-started) •
[Roadmap](#-roadmap)

</div>

---

## 🧠 What is TransformAI?

TransformAI solves a simple but expensive problem:

> **Why create the same information again and again for different audiences and platforms?**

A single source such as a **PDF, text document, or URL** can contain valuable information, but communicating that information often requires creating multiple versions manually.

TransformAI creates a structured knowledge representation from the source and uses it as the foundation for generating multiple deliverables.

### Instead of:

```text
PDF
 ↓
Read it
 ↓
Write summary
 ↓
Write advisory
 ↓
Create LinkedIn post
 ↓
Create X thread
 ↓
Make presentation
 ↓
Make infographic
 ↓
Write video script

                 ┌──────────────────────┐
                 │      SOURCE INPUT    │
                 │ PDF / Text / URL     │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │       INGEST         │
                 │ Extract & Normalize  │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │       ANALYZE        │
                 │ Knowledge + Facts    │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │    PLAN OUTPUTS      │
                 │ Audience + Objective │
                 └──────────┬───────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
          Summary       Advisory      LinkedIn
              │             │             │
              ├─────────────┼─────────────┤
              │             │             │
              ▼             ▼             ▼
          X Thread     Presentation   Infographic
                            │
                            ▼
                      Video Package
                            │
                            ▼
                 ┌──────────────────────┐
                 │    VALIDATION        │
                 │ Consistency          │
                 │ Grounding            │
                 │ Quality              │
                 └──────────┬───────────┘
                            │
                     ┌──────▼──────┐
                     │   REPAIR    │
                     │ Failed      │
                     │ Outputs     │
                     └──────┬──────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   FINAL DELIVERABLES│
                 └──────────────────────┘
