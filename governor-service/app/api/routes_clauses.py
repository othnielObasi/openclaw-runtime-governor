"""Regulatory Clauses API — browse and manage compliance article definitions.

GET  /compliance/clauses           — list all clauses (any authenticated user)
GET  /compliance/clauses/{framework} — list clauses for a specific framework
PUT  /compliance/clauses/{id}      — update clause text (superadmin only)
POST /compliance/clauses/seed      — re-seed default clauses (superadmin only)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth.dependencies import get_current_user, require_superadmin
from ..database import db_session
from ..models import RegulatoryClause

log = logging.getLogger("governor.clauses")

router = APIRouter(prefix="/compliance/clauses", tags=["compliance"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ClauseOut(BaseModel):
    id: int
    framework: str
    article_id: str
    title: str
    clause_text: str
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None

class ClauseUpdate(BaseModel):
    title: Optional[str] = None
    clause_text: Optional[str] = None

class ClauseCreate(BaseModel):
    framework: str
    article_id: str
    title: str
    clause_text: str

# ---------------------------------------------------------------------------
# Seed data — real regulatory articles
# ---------------------------------------------------------------------------

SEED_CLAUSES: List[dict] = [
    # ── EU AI Act ──────────────────────────────────────────────────────────
    {
        "framework": "eu_ai_act",
        "article_id": "Art.6",
        "title": "Classification Rules for High-Risk AI Systems",
        "clause_text": "An AI system shall be considered high-risk where it is a product, or the safety component of a product, covered by Union harmonisation legislation listed in Annex I, or falls under one of the areas listed in Annex III. Providers must perform conformity assessments before placing such systems on the market.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.9",
        "title": "Risk Management System",
        "clause_text": "A risk management system shall be established, implemented, documented and maintained in relation to high-risk AI systems. It shall consist of a continuous iterative process planned and run throughout the entire lifecycle of the system, requiring regular systematic updating. Risk management measures shall ensure that the residual risk associated with each identified hazard is judged acceptable.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.10",
        "title": "Data and Data Governance",
        "clause_text": "High-risk AI systems which make use of techniques involving the training of AI models with data shall be developed on the basis of training, validation and testing data sets that meet quality criteria. Training, validation and testing data sets shall be subject to data governance and management practices appropriate for the intended purpose of the AI system.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.11",
        "title": "Technical Documentation",
        "clause_text": "The technical documentation of a high-risk AI system shall be drawn up before that system is placed on the market or put into service and shall be kept up-to-date. It shall demonstrate that the system complies with the requirements set out in this Chapter and provide national competent authorities and notified bodies with all necessary information to assess compliance.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.12",
        "title": "Record-Keeping",
        "clause_text": "High-risk AI systems shall technically allow for the automatic recording of events (logs) over the lifetime of the system. The logging capabilities shall ensure a level of traceability of the AI system's functioning throughout its lifecycle that is appropriate to the intended purpose of the system.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.13",
        "title": "Transparency and Provision of Information to Deployers",
        "clause_text": "High-risk AI systems shall be designed and developed in such a way as to ensure that their operation is sufficiently transparent to enable deployers to interpret a system's output and use it appropriately. An appropriate type and degree of transparency shall be ensured, with a view to achieving compliance with the relevant obligations of the provider and deployer.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.14",
        "title": "Human Oversight",
        "clause_text": "High-risk AI systems shall be designed and developed in such a way, including with appropriate human-machine interface tools, that they can be effectively overseen by natural persons during the period in which they are in use. Human oversight shall aim to prevent or minimise the risks to health, safety or fundamental rights.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.15",
        "title": "Accuracy, Robustness and Cybersecurity",
        "clause_text": "High-risk AI systems shall be designed and developed in such a way that they achieve an appropriate level of accuracy, robustness, and cybersecurity, and that they perform consistently in those respects throughout their lifecycle. The levels of accuracy and the relevant accuracy metrics shall be declared in the accompanying instructions of use.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.26",
        "title": "Obligations of Deployers of High-Risk AI Systems",
        "clause_text": "Deployers of high-risk AI systems shall use such systems in accordance with the instructions of use accompanying the systems. Deployers shall assign human oversight to natural persons who have the necessary competence, training and authority. Deployers shall monitor the operation of the high-risk AI system on the basis of the instructions of use and inform the provider of any serious incident or malfunctioning.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.27",
        "title": "Fundamental Rights Impact Assessment",
        "clause_text": "Before deploying a high-risk AI system, deployers that are bodies governed by public law or private entities providing public services shall perform an assessment of the impact on fundamental rights that the use of such system may produce. The assessment shall include a description of the deployer's processes in which the system will be used, the period and frequency of use, and the categories of natural persons and groups likely to be affected.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.42",
        "title": "Presumption of Conformity with Certain Requirements",
        "clause_text": "High-risk AI systems that have been trained and tested on data reflecting the specific geographical, behavioural and functional setting within which they are intended to be used shall be presumed to comply with the relevant requirements laid down in Article 10. Conformity with harmonised standards published in the Official Journal gives rise to a presumption of conformity.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.52",
        "title": "Transparency Obligations for Certain AI Systems",
        "clause_text": "Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural person is informed that they are interacting with an AI system, unless this is obvious from the circumstances and the context of use. This obligation shall not apply to AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences.",
    },
    {
        "framework": "eu_ai_act",
        "article_id": "Art.71",
        "title": "Penalties",
        "clause_text": "Non-compliance with the prohibition of AI practices referred to in Article 5 shall be subject to administrative fines of up to €35 million or 7% of total worldwide annual turnover. Non-compliance with AI system requirements shall be subject to fines of up to €15 million or 3% of turnover. Supply of incorrect information to authorities shall be subject to fines of up to €7.5 million or 1% of turnover.",
    },

    # ── NIST AI Risk Management Framework ──────────────────────────────────
    {
        "framework": "nist_ai_rmf",
        "article_id": "GOVERN-1.1",
        "title": "Legal and Regulatory Requirements",
        "clause_text": "Legal and regulatory requirements involving AI are understood, managed, and documented. Organizations identify applicable laws, regulations, standards, and guidance related to the AI system context, and implement processes to comply with them throughout the AI lifecycle.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "GOVERN-1.2",
        "title": "Trustworthy AI Characteristics",
        "clause_text": "Trustworthy AI characteristics are integrated into organizational policies, processes, procedures, and practices. These include: valid and reliable, safe, secure and resilient, accountable and transparent, explainable and interpretable, privacy-enhanced, and fair with harmful bias managed.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MAP-1.1",
        "title": "Intended Purpose and Context Documented",
        "clause_text": "Intended purposes, potentially beneficial uses, context of use, and assumptions are thoroughly documented. This includes the system's design goals, target deployment environments, user base, and the anticipated impacts on individuals, groups, communities, organizations, and society.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MAP-2.1",
        "title": "Scientific Integrity and TEVV",
        "clause_text": "The AI system is evaluated using Test, Evaluation, Verification, and Validation (TEVV) methodologies to ensure scientific integrity. This includes validating the system's design meets its intended purpose, verifying implementation correctness, and evaluating performance under realistic conditions.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MAP-3.1",
        "title": "Benefits and Costs Assessed",
        "clause_text": "AI system benefits and costs are assessed — including benefits and potential harms to individuals, groups, communities, organizations, and society. Impact assessments consider short-term and long-term effects, direct and indirect consequences, and distributional effects.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MEASURE-1.1",
        "title": "Approaches and Metrics for Measurement",
        "clause_text": "Appropriate methods and metrics are identified and applied to measure the AI system's trustworthy characteristics. Measurement approaches account for context, intended use, and the AI system's design, and they employ quantitative, qualitative, or mixed methods as appropriate.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MEASURE-2.1",
        "title": "AI System Evaluated for Trustworthy Characteristics",
        "clause_text": "The AI system is evaluated for valid and reliable performance, safety, security, resilience, accountability, transparency, explainability, interpretability, privacy, and fairness. Evaluations are conducted regularly through the AI lifecycle and cover the specific deployment context.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MEASURE-2.6",
        "title": "Computational Bias and Fairness",
        "clause_text": "AI system performance or assurance criteria are measured qualitatively or quantitatively and demonstrate the system is fit for purpose. Computational and statistical biases are examined, and pre-production and post-deployment testing validates that the system operates within acceptable bias thresholds.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MANAGE-1.1",
        "title": "AI Risk Treatment Plans",
        "clause_text": "A determination is made as to whether the AI system achieves its intended purpose and stated objectives within acceptable risk thresholds. Risk treatment plans are developed that include risk acceptance, avoidance, transfer, and mitigation strategies prioritized by impact.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MANAGE-2.1",
        "title": "Resources for Risk Management",
        "clause_text": "Resources required to manage AI risks are taken into account — along with viable non-AI alternative systems, approaches, or methods. Allocation of resources considers the cost of risk treatment, monitoring feasibility, and whether the AI system should be decommissioned if risks cannot be mitigated.",
    },
    {
        "framework": "nist_ai_rmf",
        "article_id": "MANAGE-4.1",
        "title": "Post-Deployment Monitoring",
        "clause_text": "Post-deployment AI system monitoring plans are implemented, including mechanisms for capturing and evaluating input from users and other relevant AI actors, appeal and override, decommissioning, incident response, recovery, and change management.",
    },

    # ── OWASP LLM Top 10 (2025) ───────────────────────────────────────────
    {
        "framework": "owasp_llm",
        "article_id": "LLM01",
        "title": "Prompt Injection",
        "clause_text": "A Prompt Injection vulnerability occurs when an attacker manipulates a large language model through crafted inputs, causing the LLM to unknowingly execute the attacker's intentions. This can be done directly by 'jailbreaking' the system prompt or indirectly through manipulated external inputs, potentially leading to data exfiltration, social engineering, and other issues.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM02",
        "title": "Insecure Output Handling",
        "clause_text": "Insecure Output Handling refers to insufficient validation, sanitization, and handling of the outputs generated by large language models before they are passed downstream to other components and systems. Since LLM-generated content can be controlled by prompt input, this behavior is similar to providing users indirect access to additional functionality.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM03",
        "title": "Training Data Poisoning",
        "clause_text": "Training Data Poisoning refers to manipulation of pre-training, fine-tuning, or embedding data to introduce vulnerabilities, backdoors, or biases that could compromise the model's security, effectiveness, or ethical behavior. Poisoned information may be surfaced to users or create other risks like performance degradation, downstream software exploitation, and reputational damage.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM04",
        "title": "Model Denial of Service",
        "clause_text": "An attacker interacts with an LLM in a method that consumes an exceptionally high amount of resources, which results in a decline in the quality of service for them and other users, as well as potentially incurring high resource costs. Resource-intensive operations, such as generating large volumes of tasks in tools or triggering recursive context expansion, are attack vectors.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM05",
        "title": "Supply Chain Vulnerabilities",
        "clause_text": "The supply chain in LLMs can be vulnerable, impacting the integrity of training data, ML models, and deployment platforms. These vulnerabilities can lead to biased outcomes, security breaches, or complete system failures. Traditionally focused on software components, AI extends this with pre-trained models, training data, and plugin/tool integrations.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM06",
        "title": "Sensitive Information Disclosure",
        "clause_text": "LLM applications may reveal sensitive information, proprietary algorithms, or other confidential details through their output. This can result in unauthorized access to sensitive data, intellectual property, privacy violations, and other security breaches. Consumers of LLM applications should be aware of how to safely interact with LLMs and identify the risks.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM07",
        "title": "Insecure Plugin Design",
        "clause_text": "LLM plugins can have insecure inputs and insufficient access control. This lack of application control makes them easier to exploit and can result in consequences ranging from remote code execution to data exfiltration. Plugins that allow free-form text as input without validation are especially vulnerable to prompt injection and tool misuse.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM08",
        "title": "Excessive Agency",
        "clause_text": "An LLM-based system is often granted a degree of agency by its developer — the ability to call functions, interface with other systems, and undertake actions in response to a prompt. Excessive Agency is the vulnerability that enables damaging actions to be performed in response to unexpected, ambiguous, or manipulated LLM outputs without sufficient guardrails.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM09",
        "title": "Overreliance",
        "clause_text": "Overreliance occurs when users or systems depend on LLMs for decision-making or content generation without sufficient oversight. As LLM-generated content can be authoritative-sounding, it may lead to propagation of incorrect information, misjudgements, or transfer of decision accountability. Without proper validation, LLM outputs may undermine safety and security.",
    },
    {
        "framework": "owasp_llm",
        "article_id": "LLM10",
        "title": "Model Theft",
        "clause_text": "Model Theft refers to the unauthorized access, copying, or exfiltration of proprietary LLM models. This includes compromising model weights and parameters, replicating capabilities through side-channel attacks, or extracting model behavior through systematic API querying. Impact includes economic losses, compromised competitive advantage, and unauthorized access to sensitive information.",
    },
]


# ---------------------------------------------------------------------------
# Seed function — called at startup to populate missing clauses
# ---------------------------------------------------------------------------

def seed_regulatory_clauses() -> int:
    """Insert any missing regulatory clauses. Returns count of newly inserted rows."""
    inserted = 0
    with db_session() as session:
        for clause_data in SEED_CLAUSES:
            exists = session.execute(
                select(RegulatoryClause).where(
                    RegulatoryClause.framework == clause_data["framework"],
                    RegulatoryClause.article_id == clause_data["article_id"],
                )
            ).scalar_one_or_none()
            if not exists:
                session.add(RegulatoryClause(**clause_data))
                inserted += 1
    if inserted:
        log.info("Seeded %d regulatory clauses", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=List[ClauseOut])
def list_clauses(current_user=Depends(get_current_user)):
    """List all regulatory clauses across all frameworks."""
    with db_session() as session:
        rows = session.execute(
            select(RegulatoryClause).order_by(RegulatoryClause.framework, RegulatoryClause.article_id)
        ).scalars().all()
        return [_to_out(r) for r in rows]


@router.get("/{framework}", response_model=List[ClauseOut])
def list_clauses_by_framework(framework: str, current_user=Depends(get_current_user)):
    """List clauses for a specific framework (eu_ai_act, nist_ai_rmf, owasp_llm)."""
    with db_session() as session:
        rows = session.execute(
            select(RegulatoryClause)
            .where(RegulatoryClause.framework == framework)
            .order_by(RegulatoryClause.article_id)
        ).scalars().all()
        return [_to_out(r) for r in rows]


@router.put("/{clause_id}", response_model=ClauseOut)
def update_clause(clause_id: int, body: ClauseUpdate, admin=Depends(require_superadmin)):
    """Update a clause's title or text (superadmin only)."""
    with db_session() as session:
        clause = session.get(RegulatoryClause, clause_id)
        if not clause:
            raise HTTPException(status_code=404, detail="Clause not found")
        if body.title is not None:
            clause.title = body.title
        if body.clause_text is not None:
            clause.clause_text = body.clause_text
        clause.updated_by = admin.username
        session.flush()
        return _to_out(clause)


@router.post("/seed", response_model=dict)
def reseed_clauses(admin=Depends(require_superadmin)):
    """Re-seed missing default clauses (superadmin only)."""
    count = seed_regulatory_clauses()
    return {"seeded": count}


@router.post("", response_model=ClauseOut)
def create_clause(body: ClauseCreate, admin=Depends(require_superadmin)):
    """Create a new custom regulatory clause (superadmin only)."""
    with db_session() as session:
        clause = RegulatoryClause(
            framework=body.framework,
            article_id=body.article_id,
            title=body.title,
            clause_text=body.clause_text,
            updated_by=admin.username,
        )
        session.add(clause)
        session.flush()
        return _to_out(clause)


def _to_out(r: RegulatoryClause) -> ClauseOut:
    return ClauseOut(
        id=r.id,
        framework=r.framework,
        article_id=r.article_id,
        title=r.title,
        clause_text=r.clause_text,
        updated_by=r.updated_by,
        updated_at=r.updated_at.isoformat() if r.updated_at else None,
    )
