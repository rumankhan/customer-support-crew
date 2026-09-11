"""
Multi-Agent Customer Support Crew runtime orchestration.
Implements CrewAI sequential pipeline per SAD §2.
Loads agent and task definitions from YAML per CrewAI adapter rules.
"""
import os
import yaml
from typing import Dict, Any, Callable, Optional
from pathlib import Path
from crewai import Agent, Task, Crew, Process
from backend.models import (
    ClassifierOutput,
    RetrieverOutput, 
    ResponseOutput,
    EscalationOutput
)
from backend.tools import (
    kb_search_tool,
    ticket_stub_tool,
    account_lookup_tool,
    order_lookup_tool,
)
from backend.llm_config import build_crew_llm, resolve_llm_settings

_LAST_CREW_TRACE_URL: Optional[str] = None
_TRACE_CAPTURE_INSTALLED = False
_CREWAI_TRACE_PREFIX = "https://app.crewai.com/"


def allowed_crew_trace_url(url: Optional[str]) -> Optional[str]:
    """Return a CrewAI AMP dashboard URL, or None if missing/unsafe."""
    if not url or not isinstance(url, str):
        return None
    cleaned = url.strip()
    if cleaned.startswith(_CREWAI_TRACE_PREFIX):
        return cleaned
    return None


def last_crew_trace_url() -> Optional[str]:
    return allowed_crew_trace_url(_LAST_CREW_TRACE_URL)


def _remember_crew_trace_url(url: Optional[str]) -> None:
    global _LAST_CREW_TRACE_URL
    _LAST_CREW_TRACE_URL = allowed_crew_trace_url(url)


def _install_trace_url_capture() -> None:
    """Hook CrewAI AMP finalization so we can persist the dashboard URL."""
    global _TRACE_CAPTURE_INSTALLED
    if _TRACE_CAPTURE_INSTALLED:
        return
    try:
        from crewai.events.listeners.tracing.trace_listener import (
            TraceCollectionListener,
        )
        from crewai.utilities.constants import CREWAI_BASE_URL
    except ImportError:
        return
    listener = TraceCollectionListener._instance
    if listener is None:
        return
    batch_manager = listener.batch_manager
    original = batch_manager._finalize_backend_batch

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        batch_id = batch_manager.trace_batch_id
        ephemeral = batch_manager.is_current_batch_ephemeral
        result = original(*args, **kwargs)
        url = getattr(batch_manager, "ephemeral_trace_url", None)
        if not url and batch_id:
            kind = "ephemeral_trace_batches" if ephemeral else "trace_batches"
            url = f"{CREWAI_BASE_URL}/crewai_plus/{kind}/{batch_id}"
        _remember_crew_trace_url(url)
        return result

    batch_manager._finalize_backend_batch = wrapped
    _TRACE_CAPTURE_INSTALLED = True


class CustomerSupportCrew:
    """
    Customer Support Crew orchestrator.
    Configures 4 agents with model tiers and sequential task execution.
    """
    
    def __init__(self):
        """Initialize crew with model tier configuration and load YAML configs."""
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
        # CrewAI AMP traces (app.crewai.com). Default on; set CREWAI_TRACING_ENABLED=false to disable.
        self.tracing_enabled = os.getenv("CREWAI_TRACING_ENABLED", "true").lower() == "true"
        
        # Load YAML configurations
        self.config_dir = Path(__file__).parent / "config"
        self.agents_config = self._load_yaml("agents.yaml")
        self.tasks_config = self._load_yaml("tasks.yaml")
        
        # Create agents from YAML
        self.agents = self._create_agents()
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """Load YAML configuration file."""
        config_path = self.config_dir / filename
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}. "
                "Expected YAML configs in backend/config/ per SAD §2 and CrewAI adapter rules."
            )
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
        
    def _create_agents(self) -> Dict[str, Agent]:
        """Create the 4 specialized agents from YAML configuration."""
        # Tool mapping for agent tool assignment
        tool_map = {
            "kb_search": kb_search_tool,
            "ticket_stub": ticket_stub_tool,
            "account_lookup": account_lookup_tool,
            "order_lookup": order_lookup_tool,
        }
        
        agents = {}
        for agent_id, agent_config in self.agents_config.items():
            # Resolve tools from config
            agent_tools = []
            if "tools" in agent_config:
                agent_tools = [tool_map[tool_name] for tool_name in agent_config["tools"]]
            
            # Create agent with YAML config
            agents[agent_id] = Agent(
                role=agent_config["role"],
                goal=agent_config["goal"],
                backstory=agent_config["backstory"],
                llm=self.shared_llm,
                tools=agent_tools,
                allow_delegation=agent_config.get("allow_delegation", False),
                verbose=agent_config.get("verbose", True),
                max_iter=self.max_iter
            )
        
        return agents
    
    def _create_tasks(self, message: str, request_human: bool) -> list[Task]:
        """
        Create the 4 sequential tasks from YAML configuration with dynamic value injection.
        
        Args:
            message: Customer message
            request_human: Customer requested human flag
            
        Returns:
            List of Task objects with context dependencies
        """
        # Pydantic model mapping
        model_map = {
            "ClassifierOutput": ClassifierOutput,
            "RetrieverOutput": RetrieverOutput,
            "ResponseOutput": ResponseOutput,
            "EscalationOutput": EscalationOutput
        }
        
        # Build tasks with context dependencies
        tasks = {}
        task_order = ["classify_inquiry", "retrieve_knowledge", "compose_response", "triage_and_escalate"]
        
        for task_id in task_order:
            task_config = self.tasks_config[task_id]
            
            # Inject dynamic values into description
            description = task_config["description"].format(
                message=message,
                request_human=request_human,
                classifier_confidence_min=self.classifier_confidence_min
            )
            
            # Resolve context dependencies
            context_tasks = []
            if "context" in task_config:
                context_tasks = [tasks[ctx_id] for ctx_id in task_config["context"]]
            
            # Create task
            tasks[task_id] = Task(
                description=description,
                expected_output=task_config["expected_output"],
                agent=self.agents[task_config["agent"]],
                output_pydantic=model_map[task_config["output_pydantic"]],
                context=context_tasks
            )
        
        return list(tasks.values())
    
    def kickoff(
        self,
        inputs: Dict[str, Any],
        progress_callback: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the crew with given inputs.

        Args:
            inputs: Dict with 'message' and 'request_human' keys
            progress_callback: Optional SSE progress hook (agent, status, summary)

        Returns:
            Dict with task outputs and metadata
        """
        message = inputs.get("message", "")
        request_human = inputs.get("request_human", False)

        task_agent_ids = [
            self.tasks_config["classify_inquiry"]["agent"],
            self.tasks_config["retrieve_knowledge"]["agent"],
            self.tasks_config["compose_response"]["agent"],
            self.tasks_config["triage_and_escalate"]["agent"],
        ]

        completed_index = {"value": 0}

        def emit(agent: str, status: str, summary: str = "") -> None:
            if progress_callback:
                progress_callback(
                    {
                        "agent": agent,
                        "status": status,
                        "summary": summary[:200] if summary else "",
                    }
                )

        def on_task_complete(output: Any) -> None:
            idx = completed_index["value"]
            if idx < len(task_agent_ids):
                agent_id = task_agent_ids[idx]
                summary = str(output)[:200] if output is not None else ""
                emit(agent_id, "completed", summary)
                completed_index["value"] = idx + 1
                if idx + 1 < len(task_agent_ids):
                    emit(task_agent_ids[idx + 1], "running")

        if progress_callback and task_agent_ids:
            emit(task_agent_ids[0], "running")

        tasks = self._create_tasks(message, request_human)

        crew = Crew(
            agents=list(self.agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
            max_rpm=self.max_rpm,
            memory=False,
            tracing=self.tracing_enabled,
            task_callback=on_task_complete if progress_callback else None,
        )

        global _LAST_CREW_TRACE_URL
        _LAST_CREW_TRACE_URL = None
        _install_trace_url_capture()
        result = crew.kickoff()
        crew_trace_url = last_crew_trace_url()

        return {
            "result": result,
            "tasks": tasks,
            "inputs": inputs,
            "crew_trace_url": crew_trace_url,
        }
