# Orrery (then "Cognition Cycles") — External Landscape & Market Viability Report

**Date:** August 6, 2026
**Prepared for:** Kirk LaSalle
**Scope:** Where does this project sit relative to existing open-source repos, commercial products, and academic prior art? Is there a market for it?
**Method:** Live web/GitHub/arXiv retrieval + direct inspection of this repository's source tree.

> ℹ️ **Rename note.** This report was written under the project's original name, *Cognition Cycles*. Its §"Naming collision" finding was **acted on**: the project was renamed to **Orrery** and the package moved from `src/` to `orrery/`. The analysis below is preserved as written; only file links have been repointed.

> ⚠️ **Note on the prior document.** [market_research_audit.md](market_research_audit.md) contains figures (e.g. "$5.1B in 2024 to $47.2B by 2030, CAGR 44.8%") that are **not traceable to any published source**. This report replaces those with cited, verifiable numbers. The old file should be superseded or annotated before it is ever shown externally.

---

## 1. Bottom Line Up Front

| Question | Answer |
| :--- | :--- |
| Is there anything like this? | **Yes — extensively.** The 4-phase loop, hierarchical tiers, checkpoint/rollback, and self-critique gate are each mature, independently-shipped concepts. None of them are novel in 2026. |
| Is the *combination* novel? | **Partially.** The specific packaging (explicit Meta/Macro/Meso/Micro naming + numeric critique threshold + disk checkpoints as a single opinionated framework) is uncommon, but it is a *repackaging*, not an invention. |
| Is there a market? | **Yes, and it is large and growing fast** (see §4). But it is a *crowded, well-capitalized* market where the incumbents already ship the core differentiators claimed here. |
| Can this repo compete today? | **No.** At ~1,200 lines with stubbed handlers and simulated adapters, it is a **scaffold/prototype**, not a framework. It competes on ideas, not on code. |
| Best strategic path | Reposition from "framework that replaces LangGraph/CrewAI" to a **narrow, defensible layer on top of them** — see §7. |

---

## 2. What This Repository Actually Is (Ground Truth)

Measured directly from the source tree:

| Area | Lines | Reality Check |
| :--- | ---: | :--- |
| `orrery/core/` (dispatcher, state, critique, types) | 378 | Working state machine; handlers are placeholder implementations. |
| `orrery/cycles/` (meta/macro/meso/micro) | 411 | Tier classes with delegation; largely structural. |
| `orrery/adapters/` (openclaw, hermes, windows_os) | 173 | **Simulated** — no real network, LLM, or OS calls. |
| `tests/` | 226 | 4 test files; no coverage gate enforced. |
| `examples/` | 99 | Single demo script. |
| **Total** | **~1,200** | — |

Key architectural observations relevant to positioning:

- `CycleDispatcher._default_execution_handler` marks every action `success=True` unconditionally — the critique gate can never fail on default handlers, so backtracking is currently unexercised in the happy path.
- Checkpoints serialize `StateContext` to JSON on local disk. No concurrency control, no encryption, no retention policy, no distributed store.
- `θ_critique = 0.70` is a hardcoded magic constant with no empirical derivation or benchmark backing it.
- There is no LLM integration at all. The "System 1 / Temp 0.7 vs System 2 / Temp 0.1" claim in the docs is **aspirational, not implemented**.

This gap between documentation claims and shipped code is the single biggest credibility risk in any external conversation.

---

## 3. Competitive Landscape

### 3.1 Direct Open-Source Comparables

| Project | Stars (Aug 2026) | Overlap with Cognition Cycles |
| :--- | ---: | :--- |
| **[LangGraph](https://github.com/langchain-ai/langgraph)** (LangChain Inc.) | **39.0k**, 43K dependents, 556 releases | **Near-total overlap.** Explicitly a "low-level orchestration framework for building stateful agents." Ships durable execution, checkpointing (`langgraph-checkpoint-postgres` / `-sqlite`), time-travel/replay, subgraphs (= hierarchical tiers), human-in-the-loop interrupts, and short+long-term memory. Its **Deep Agents** package adds planning + subagents + filesystem. Used in production by Klarna, Replit, Elastic. |
| **[CrewAI](https://github.com/crewAIInc/crewAI)** | **56.7k**, 19K dependents | Crews (autonomous role-based agents) + **Flows** (event-driven, structured state, `@router` conditional branching). README explicitly lists **"checkpointing"** and hierarchical process with a manager agent that delegates and validates results. 100k+ certified developers. |
| **[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)** | — (AutoGen successor) | AutoGen (**60.3k stars**) is now in **maintenance mode**; MAF 1.0 is the enterprise-ready replacement with stable APIs, LTS commitment, multi-agent orchestration, A2A + MCP interop. |
| **[OpenAI Agents SDK](https://github.com/openai/openai-agents-python)** | **28.4k**, 114 releases | Agents-as-tools, handoffs, guardrails (= critique gates), sessions (= state persistence), human-in-the-loop, built-in tracing, sandbox agents for long-horizon work. |
| **[Reflexion](https://github.com/noahshinn/reflexion)** (NeurIPS 2023) | 3.2k | The canonical self-critique-and-retry loop. Cognition Cycles' `SelfCritiqueEngine` + backtracking is a re-implementation of this pattern. |
| **[LATS](https://github.com/lapisrocks/LanguageAgentTreeSearch)** (arXiv 2310.04406) | — | MCTS over agent trajectories with LM value functions and self-reflection — a strictly more powerful search/backtrack mechanism than linear rewind. |

**Assessment:** LangGraph is the direct competitor and it wins on every axis Cognition Cycles claims as a differentiator. A GitHub repository search for the specific concept combination ("hierarchical cognitive cycle agent framework checkpoint backtracking") returns **0 repositories** — but that reflects unusual *phrasing*, not an unoccupied *capability niche*.

### 3.2 Academic Prior Art (Critical — Predates the Framing by Decades)

| Prior Art | Relevance |
| :--- | :--- |
| **[LIDA](https://en.wikipedia.org/wiki/LIDA_(cognitive_architecture))** (Franklin, U. Memphis) | Literally built on **"cognitive cycles"** — iterated at ~10 Hz, explicitly described as *"the 'atoms' of cognition of which higher-level cognitive processes are composed."* Phases: understanding → consciousness → action selection. **The core term and the hierarchical-composition thesis are 20+ years old.** |
| **[Soar](https://en.wikipedia.org/wiki/Soar_(cognitive_architecture))** (Laird/Newell/Rosenbloom, 1983) | Impasse-driven **Universal Subgoaling** creates recursive substates — i.e. automatic hierarchical task decomposition with clean result propagation and substate teardown. Explicitly maps its processing levels to **Kahneman System 1 / System 2** — the exact framing used in [docs/architecture.md](docs/architecture.md). |
| **[CoALA](https://arxiv.org/abs/2309.02427)** — *Cognitive Architectures for Language Agents* (Sumers, Yao, Narasimhan, Griffiths; TMLR) | The canonical modern framework for exactly this idea: modular memory, structured action space, generalized decision procedure. **This is the paper any technical reviewer will cite when they see Cognition Cycles.** |
| **HTN Planning** | Meta→Macro→Meso→Micro is a 4-level hierarchical task network with fixed granularity. |

**Assessment:** The intellectual framing is well-trodden. Claiming novelty on "multi-tier cognitive cycles" invites immediate pushback from anyone with a cognitive-science or agent-research background.

### 3.3 Commercial / Closed Landscape

- **Durable execution as agent substrate**: Temporal, Restate, and DBOS all market workflow-level durability, deterministic replay, and rollback for AI agents — the "checkpointing + backtracking" value proposition, but battle-tested at scale.
- **Enterprise agent platforms**: Salesforce Agentforce, Microsoft Copilot Studio / Dynamics 365, Google Vertex AI Agent Builder, AWS Bedrock Agents, IBM watsonx Orchestrate, Sierra, Kore.ai (Artemis, May 2026), Aisera, Cognigy.
- **Desktop/OS automation** (the `WindowsOSAdapter` niche): OpenAI Operator/CUA, Anthropic Computer Use, UiPath and Blue Prism embedding AI into RPA. This is the most contested and most capital-intensive segment.

### 3.4 ⚠️ Naming & Trademark Risk

**"Cognition"** is the name of **Cognition AI** — the company behind Devin, one of the most prominent AI software-engineering agents, which also acquired Windsurf. A framework named *Cognition Cycles* in the agent-orchestration space will be:

1. Confused with Cognition AI's products in search and conversation.
2. Effectively un-SEO-able against a heavily funded namesake.
3. Potentially exposed to trademark challenge in an overlapping product category.

**Recommendation:** Treat renaming as a serious, near-term decision. This is cheap to fix now and expensive to fix after any public traction.

---

## 4. Is There a Market? (Cited)

**Yes — the addressable market is real, large, and growing at ~44–46% CAGR.**

| Source | 2025 Base | Forecast | CAGR |
| :--- | :--- | :--- | :--- |
| **MarketsandMarkets** (TC 9168, Apr 2025) | USD **7.84B** (2024: 5.26B) | USD **52.62B** by 2030 | **46.3%** (2025–30) |
| **Precedence Research** (Report 5948, Jul 2026) | USD **7.92B** (2026: 11.55B) | USD **294.66B** by 2035 | **43.57%** (2026–35) |

Segment signals that favor this project's thesis:

- **Multi-agent systems** are the fastest-growing agent-system segment (MarketsandMarkets: **48.5% CAGR**).
- **Coding & software development** agents: **52.4% CAGR** — the fastest agent role.
- **Build-your-own-agent** platforms are the fastest-growing product type — i.e. there *is* demand for frameworks, not just finished agents.
- **North America leads; Asia-Pacific is fastest-growing.**

Signals that work against it:

- MarketsandMarkets flags **high implementation cost** as the top restraint, with **~60% of enterprises** citing governance/compliance concerns. Enterprises buying into this concern will choose a vendor-backed platform (LangGraph Platform, Microsoft, Salesforce) over an unbacked solo framework.
- The framework layer specifically is **consolidating, not fragmenting**: AutoGen → maintenance mode → Microsoft Agent Framework. The window for a new general-purpose orchestration framework to win mindshare has largely closed.

**Conclusion:** The market is for *agents and agent platforms*, and it is enormous. The market for *another general-purpose Python orchestration framework* is close to zero. Monetization must come from a layer above or beside the framework, not the framework itself.

---

## 5. Honest Differentiation Scorecard

| Claimed Differentiator | Verdict |
| :--- | :--- |
| 4-phase deterministic state machine | ❌ Not novel. LangGraph graphs, CrewAI Flows, Soar decision cycle, LIDA cognitive cycle. |
| 4 hierarchical abstraction tiers | ❌ Not novel. LangGraph subgraphs, CrewAI hierarchical process, Soar substates, HTN, CoALA. |
| Disk-backed checkpointing | ❌ Not novel, and **weaker** than shipped alternatives (LangGraph Postgres/SQLite checkpointers, Temporal event sourcing). |
| Automated backtracking | ❌ Not novel. LangGraph time-travel; LATS does full MCTS backtracking. |
| Quantitative self-critique gate (θ=0.70) | ⚠️ **Partially novel in packaging only.** Reflexion (verbal), OpenAI guardrails, LLM-as-judge all exist. The *numeric threshold as a first-class architectural primitive* is a modest, real distinction — but 0.70 is currently arbitrary. |
| Platform adapters (OpenClaw / Hermes / Windows OS) | ⚠️ **The single most defensible asset — and it is unimplemented.** These are proprietary integrations no competitor has. Currently all three are simulated stubs. |

**The honest summary: the differentiation is not in the cycle architecture. It is in the adapters and the ecosystem integration — the parts that aren't built yet.**

---

## 6. Threats

1. **Commoditization** — LangGraph/CrewAI/MAF ship these features today, backed by full-time teams and 19k–43k downstream dependents.
2. **Doc/code credibility gap** — README and PRD describe a production framework; the repo is a scaffold. Any technical evaluator will find this in minutes.
3. **Unsourced market claims** — the existing audit's numbers appear fabricated. In a funding or partnership context this is disqualifying.
4. **Name collision** with Cognition AI.
5. **Zero benchmarks** — no GAIA / SWE-bench / OSWorld / τ-bench numbers means no evidence the architecture actually improves reliability.
6. **Maintenance economics** — competing frameworks have 297–557 contributors. A solo framework cannot keep pace with model/protocol churn (MCP, A2A, provider APIs).

---

## 7. Recommended Repositioning

### Don't compete with LangGraph. Sit on top of it

**Reframe as:** *A reliability & governance layer for long-horizon agents — hierarchical goal decomposition with quantitative verification gates and deterministic rollback, implemented over an existing durable-execution substrate.*

Concrete moves, in priority order:

1. **Fix the credibility gap first.** Rewrite README/PRD to describe what exists ("early-stage reference implementation") and clearly mark what's roadmap. Delete or annotate the unsourced market figures.
2. **Rename.** Avoid the Cognition AI collision while the cost is near zero.
3. **Pick a substrate, don't rebuild one.** Implement `CheckpointManager` over LangGraph checkpointers or Temporal instead of hand-rolled JSON files. Adopt MCP for tools and A2A for inter-agent messaging — both are now table stakes.
4. **Go all-in on the critique gate as the product.** A rigorous, pluggable, *evaluated* verification layer (rubric-based scorers, calibrated thresholds, invariant checks, audit trail) is a genuinely underserved need and maps directly to the ~60%-of-enterprises governance concern. Derive θ empirically instead of hardcoding 0.70.
5. **Build one adapter for real.** The `WindowsOSAdapter` + micro-cycle visual verification story is the most differentiated. One working end-to-end OS-automation demo is worth more than four tiers of abstraction.
6. **Benchmark or don't claim.** Publish OSWorld / SWE-bench / τ-bench results comparing "with backtracking" vs "without." Without numbers, the reliability claim is unfalsifiable and will be dismissed.
7. **Narrow the vertical.** "Agentic desktop automation with verifiable rollback for regulated workflows" is a defensible wedge. "General-purpose agent framework" is not.

### Realistic monetization vectors

- ❌ **Framework licensing** — dead on arrival against MIT-licensed, VC-funded incumbents.
- ✅ **Verification/audit layer** sold into regulated industries (BFSI is the largest enterprise end-user segment).
- ✅ **Proprietary adapters** (OpenClaw/Prism, Hermes) as the commercial moat around an open core.
- ✅ **Design-pattern authority** — publish the architecture as a paper/spec. CoALA earned influence through the paper, not the code.

---

## 8. Sources

- LangGraph — <https://github.com/langchain-ai/langgraph> (39.0k stars, 43K dependents, 556 releases)
- CrewAI — <https://github.com/crewAIInc/crewAI> (56.7k stars, 19K dependents)
- AutoGen (maintenance mode) — <https://github.com/microsoft/autogen> (60.3k stars) → <https://github.com/microsoft/agent-framework>
- OpenAI Agents SDK — <https://github.com/openai/openai-agents-python> (28.4k stars)
- Reflexion (NeurIPS 2023) — <https://github.com/noahshinn/reflexion> · arXiv:2303.11366
- LATS (arXiv:2310.04406) — <https://github.com/lapisrocks/LanguageAgentTreeSearch>
- CoALA: Cognitive Architectures for Language Agents (TMLR) — <https://arxiv.org/abs/2309.02427>
- LIDA cognitive architecture — <https://en.wikipedia.org/wiki/LIDA_(cognitive_architecture)>
- Soar cognitive architecture — <https://en.wikipedia.org/wiki/Soar_(cognitive_architecture)>
- MarketsandMarkets, *AI Agents Market* (TC 9168, Apr 2025) — <https://www.marketsandmarkets.com/Market-Reports/ai-agents-market-15761548.html>
- Precedence Research, *AI Agents Market 2026–2035* (Report 5948, Jul 2026) — <https://www.precedenceresearch.com/ai-agents-market>

*GitHub star/dependent counts retrieved August 6, 2026.*
