"""
Multi-Agent Customer Support Crew runtime orchestration.
Implements CrewAI sequential pipeline per SAD §2.
"""
import os
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process
from backend.models import (
    ClassifierOutput,
    RetrieverOutput, 
    ResponseOutput,
    EscalationOutput
)
from backend.tools import kb_search_tool, ticket_stub_tool
from backend.llm_config import build_crew_llm, resolve_llm_settings


class CustomerSupportCrew:
    """
    Customer Support Crew orchestrator.
    Configures 4 agents with model tiers and sequential task execution.
    """
    
    def __init__(self):
        """Initialize crew with model tier configuration."""
        # Resolve LLM settings and create shared LLM instance
        settings = resolve_llm_settings()
        if settings is None:
            raise RuntimeError(
                "No LLM configured. Set OPENAI_API_KEY "
                "or OLLAMA_API_KEY (+ optional LLM_PROVIDER=ollama)."
            )
        
        self.llm_provider = settings.provider
        self.model_low = settings.model  # Same model for all agents (shared LLM pattern)
        self.model_mid = settings.model
        self.shared_llm = build_crew_llm()
        
        # Load control parameters
        self.max_iter = int(os.getenv("MAX_ITER", "12"))
        self.max_rpm = int(os.getenv("MAX_RPM", "10"))
        self.classifier_confidence_min = float(os.getenv("CLASSIFIER_CONFIDENCE_MIN", "0.55"))
        
        # Create agents
        self.agents = self._create_agents()
        
    def _create_agents(self) -> Dict[str, Agent]:
        """Create the 4 specialized agents with shared LLM."""
        # Use shared LLM for all agents (recruitment assistant pattern)
        agents = {
            "query_classifier": Agent(
                role="Inquiry Classification Specialist",
                goal="Classify customer intent, entities, and urgency for routing",
                backstory=(
                    "You are an expert at understanding customer inquiries and extracting key information. "
                    "You analyze customer messages to identify their intent, extract relevant entities "
                    "(like account, plan, device), assess urgency, and provide a confidence score. "
                    "You work with precision and always structure your output clearly."
                ),
                llm=self.shared_llm,
                allow_delegation=False,
                verbose=True,
                max_iter=self.max_iter
            ),
            
            "knowledge_retriever": Agent(
                role="Knowledge Base Research Specialist",
                goal="Retrieve grounded passages with citations for the classified intent",
                backstory=(
                    "You are a skilled researcher who searches the B-Mobile knowledge base to find "
                    "relevant help articles. You always cite your sources and clearly indicate when "
                    "you cannot find information on a topic. You never fabricate information and "
                    "always work from documented knowledge."
                ),
                llm=self.shared_llm,
                tools=[kb_search_tool],
                allow_delegation=False,
                verbose=True,
                max_iter=self.max_iter
            ),
            
            "response_specialist": Agent(
                role="Customer Response Composer",
                goal="Draft clear, personalized, policy-aligned replies using only grounded evidence",
                backstory=(
                    "You are an experienced customer service writer who crafts helpful, empathetic "
                    "responses. You only write answers based on documented knowledge sources and "
                    "refuse to make up information. When evidence is missing, you clearly state "
                    "that and recommend escalation to a human agent. You write in a friendly, "
                    "professional tone."
                ),
                llm=self.shared_llm,
                allow_delegation=False,
                verbose=True,
                max_iter=self.max_iter
            ),
            
            "escalation_manager": Agent(
                role="Sentiment, Risk & Escalation Coordinator",
                goal="Score text sentiment/risk and decide resolve vs escalate; package context for humans",
                backstory=(
                    "You are a triage specialist who analyzes customer interactions for sentiment "
                    "and risk factors. You make decisions on whether to resolve a case or escalate "
                    "it to a human agent. When escalating, you prepare detailed context packets "
                    "that help human agents handle the case effectively. You use text-only sentiment "
                    "analysis and deterministic rules to ensure consistent decisions."
                ),
                llm=self.shared_llm,
                tools=[ticket_stub_tool],
                allow_delegation=False,
                verbose=True,
                max_iter=self.max_iter
            )
        }
        
        return agents
    
    def _create_tasks(self, message: str, request_human: bool) -> list[Task]:
        """
        Create the 4 sequential tasks with structured outputs.
        
        Args:
            message: Customer message
            request_human: Customer requested human flag
            
        Returns:
            List of Task objects with context dependencies
        """
        # Task 1: Classify inquiry
        classify_task = Task(
            description=(
                f"Analyze the customer message: {message}\n\n"
                "Extract and classify:\n"
                "1. The customer's primary intent (what they want to accomplish)\n"
                "2. Urgency level (low/medium/high) based on language and context\n"
                "3. Key entities mentioned (account, plan, device, billing, etc.)\n"
                "4. Your confidence in the classification (0.0 to 1.0)\n\n"
                f"Consider context:\n- request_human flag: {request_human}\n\n"
                "Be precise and analytical. Your classification guides the entire resolution process."
            ),
            expected_output=(
                "A structured classification with intent, urgency, entities list, and confidence score. "
                "Format: ClassifierOutput with fields intent, urgency, entities, confidence"
            ),
            agent=self.agents["query_classifier"],
            output_pydantic=ClassifierOutput
        )
        
        # Task 2: Retrieve knowledge
        retrieve_task = Task(
            description=(
                "Using the classified intent from the previous step, search the B-Mobile knowledge base "
                "for relevant help articles.\n\n"
                "Use the kb_search tool to find FAQ articles that address the customer's question.\n\n"
                "Requirements:\n"
                "- Search for articles matching the intent and entities\n"
                "- Return passages with similarity scores\n"
                "- Include citations (title and snippet) for each relevant article\n"
                "- Set gap=true if no articles meet the similarity threshold (0.35)\n\n"
                "IMPORTANT: Only return documented knowledge. Never fabricate articles or information."
            ),
            expected_output=(
                "A structured retrieval result with passages, citations, and gap flag. "
                "Format: RetrieverOutput with fields passages (list with title/snippet/score), "
                "citations (list with title/snippet), gap (boolean)"
            ),
            agent=self.agents["knowledge_retriever"],
            output_pydantic=RetrieverOutput,
            context=[classify_task]
        )
        
        # Task 3: Compose response
        compose_task = Task(
            description=(
                "Draft a customer-facing response using ONLY the knowledge base articles from the previous step.\n\n"
                f"Customer message: {message}\n\n"
                "Guidelines:\n"
                "1. If gap=true or no citations available, set refused=true and explain you don't have "
                "   that information in your knowledge base\n"
                "2. If citations are available, compose a helpful, empathetic response that:\n"
                "   - Directly answers the customer's question\n"
                "   - Cites specific sources used\n"
                "   - Is written in a friendly, professional tone\n"
                "   - Stays within B-Mobile policy\n"
                "3. Never invent or assume information not in the provided sources\n"
                "4. Keep responses concise (2-4 paragraphs)\n\n"
                "If refused=true, politely recommend talking to a human agent."
            ),
            expected_output=(
                "A structured response with reply text, sources_used list, and refused flag. "
                "Format: ResponseOutput with fields reply, sources_used (list of citations), refused (boolean)"
            ),
            agent=self.agents["response_specialist"],
            output_pydantic=ResponseOutput,
            context=[classify_task, retrieve_task]
        )
        
        # Task 4: Triage and escalate
        triage_task = Task(
            description=(
                "Make the final decision: resolve or escalate this customer interaction.\n\n"
                "Inputs from previous steps:\n"
                "- Classification: intent, urgency, confidence\n"
                "- Retrieval: gap, citations\n"
                "- Response: reply, refused\n"
                f"- Customer flags: request_human={request_human}\n\n"
                "Escalation Rules (apply ANY that match):\n"
                "1. If request_human=true → ESCALATE with reason_code 'request_human'\n"
                "2. If gap=true or refused=true → ESCALATE with 'retrieval_gap' or 'refused'\n"
                f"3. If confidence < {self.classifier_confidence_min} → ESCALATE with 'low_confidence'\n"
                "4. If risk=high → ESCALATE with 'high_risk_sentiment'\n"
                "5. If sentiment=negative AND (risk=medium/high OR request_human OR gap OR refused OR low confidence) "
                "   → ESCALATE with 'high_risk_sentiment'\n\n"
                "Otherwise: RESOLVE\n\n"
                "Sentiment Analysis (text-only, no biometrics):\n"
                "- Analyze the customer message for positive/neutral/negative tone\n"
                "- Assess risk level (low/medium/high) based on language intensity, frustration indicators\n\n"
                "On ESCALATE:\n"
                "- Create escalation packet with all context\n"
                "- Use ticket_stub tool to generate stub ticket ID\n"
                "- Set packet and stub_ticket_id fields\n"
                "- Include all relevant reason_codes\n\n"
                "On RESOLVE:\n"
                "- Set packet=null and stub_ticket_id=null\n"
                "- Ensure sources_used is populated"
            ),
            expected_output=(
                "A structured escalation decision with decision, sentiment, risk, reason_codes, and optional packet. "
                "Format: EscalationOutput with fields decision (resolve/escalate), sentiment, risk, "
                "reason_codes (list), packet (EscalationPacket or null)"
            ),
            agent=self.agents["escalation_manager"],
            output_pydantic=EscalationOutput,
            context=[classify_task, retrieve_task, compose_task]
        )
        
        return [classify_task, retrieve_task, compose_task, triage_task]
    
    def kickoff(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the crew with given inputs.
        
        Args:
            inputs: Dict with 'message' and 'request_human' keys
            
        Returns:
            Dict with task outputs and metadata
        """
        message = inputs.get("message", "")
        request_human = inputs.get("request_human", False)
        
        # Create tasks for this run
        tasks = self._create_tasks(message, request_human)
        
        # Create crew
        crew = Crew(
            agents=list(self.agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
            max_rpm=self.max_rpm,
            memory=False  # Reproducibility per adapter-crewai
        )
        
        # Execute
        result = crew.kickoff()
        
        return {
            "result": result,
            "tasks": tasks,
            "inputs": inputs
        }
